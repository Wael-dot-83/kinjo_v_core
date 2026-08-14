"""NCFA (National Council for Family Affairs) report service.

Implements the two official NCFA reports:
  - ``child_family_profile`` — demographic profile of registered children
  - ``family_communication_counts`` — message volume by thread type

These were extracted from the monolithic ``agency_reports_service.py`` to
isolate NCFA-specific logic, making it independently testable and optimizable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services.agency_reports.base import (
    AbstractAgencyReportService,
    _coerce_enum,
    _gender_ar,
    _safe_int,
    _safe_pct,
    _thread_type_ar,
    _age_months,
    _now_iso,
    _JORDAN_TZ,
)


class NCFAAgencyReportService(AbstractAgencyReportService):
    """Report service for the National Council for Family Affairs."""

    agency_code = "ncfa"

    def list_reports(self) -> list[dict[str, Any]]:
        from agency_reports_registry import AGENCY_REPORT_REGISTRY
        agency = AGENCY_REPORT_REGISTRY.get(self.agency_code, {})
        reports = []
        for code, report in agency.get("reports", {}).items():
            entry = dict(report)
            entry["report_code"] = code
            entry["agency_code"] = self.agency_code
            entry["generated_at"] = _now_iso()
            reports.append(entry)
        return reports

    def compute_report(
        self, report_code: str, filters: dict[str, Any]
    ) -> dict[str, Any]:
        filters = self._clean_filters(filters or {})
        report = self._report(report_code)

        if report.get("status") != "ready":
            payload = self._unavailable_payload(report_code, report, filters)
            self._assert_privacy(payload)
            return payload

        if report_code == "child_family_profile":
            payload = self._child_family_profile(report_code, report, filters)
        elif report_code == "family_communication_counts":
            payload = self._family_communication_counts(report_code, report, filters)
        else:
            payload = self._unavailable_payload(
                report_code, report, filters, status="not_available"
            )

        self._assert_privacy(payload)
        return payload

    # ------------------------------------------------------------------
    # Report: child_family_profile
    # ------------------------------------------------------------------

    def _child_family_profile(
        self,
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Demographic profile of registered children: distribution by
        governorate, district, gender, and age group."""
        today = datetime.now(_JORDAN_TZ).date()
        q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.Child.gender,
                models.Child.date_of_birth,
                func.count(models.Child.id).label("count"),
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        _gender = _coerce_enum(models.Gender, filters.get("gender"))
        if _gender is not None:
            q = q.filter(models.Child.gender == _gender)
        rows = q.group_by(
            models.ParentProfile.home_governorate,
            models.ParentProfile.home_district,
            models.Child.gender,
            models.Child.date_of_birth,
        ).all()

        # Build breakdowns with age-group bucketing
        age_group_filter = filters.get("age_group")
        breakdowns: list[dict[str, Any]] = []
        gender_counts: dict[str, int] = {}
        age_group_counts: dict[str, int] = {}
        for r in rows:
            gov = r.home_governorate or "غير محدد"
            city = r.home_district or "غير محدد"
            gender_ar = _gender_ar(r.gender)
            count = _safe_int(r.count)

            # Compute age group
            age_group = "غير محدد"
            if r.date_of_birth:
                months = _age_months(r.date_of_birth, today)
                if months < 24:
                    age_group = "0-23 شهر"
                elif months < 48:
                    age_group = "24-47 شهر"
                elif months < 60:
                    age_group = "48-59 شهر"
                else:
                    age_group = "60+ شهر"

            if age_group_filter and age_group != age_group_filter:
                continue

            breakdowns.append({
                "governorate": gov,
                "city": city,
                "gender": gender_ar,
                "age_group": age_group,
                "count": count,
            })
            gender_counts[gender_ar] = gender_counts.get(gender_ar, 0) + count
            age_group_counts[age_group] = age_group_counts.get(age_group, 0) + count

        total = sum(r["count"] for r in breakdowns)
        males = gender_counts.get("ذكر", 0)
        females = gender_counts.get("أنثى", 0)

        # Build summary with KPIs
        summary = {
            "total_children": total,
            "male_count": males,
            "female_count": females,
            "male_pct": _safe_pct(males, total) if total else 0.0,
            "female_pct": _safe_pct(females, total) if total else 0.0,
        }

        payload = self._payload(report_code, report, filters, summary, breakdowns)

        # Add a gender distribution chart
        if total:
            gender_series = [
                {"label": "ذكر", "value": males},
                {"label": "أنثى", "value": females},
            ]
            other = sum(v for k, v in gender_counts.items() if k not in ("ذكر", "أنثى"))
            if other:
                gender_series.append({"label": "غير محدد", "value": other})
            payload["chart"] = {
                "type": "pie",
                "title_ar": "التوزيع حسب الجنس",
                "title_en": "Distribution by Gender",
                "series": gender_series,
            }

            # Age-group distribution chart
            age_series = [
                {"label": ag, "value": cnt}
                for ag, cnt in sorted(age_group_counts.items(), key=lambda x: x[0])
                if cnt > 0
            ]
            if age_series:
                payload["license_chart"] = {
                    "type": "bar",
                    "title_ar": "التوزيع حسب الفئة العمرية",
                    "title_en": "Distribution by Age Group",
                    "series": age_series,
                }

        return payload

    # ------------------------------------------------------------------
    # Report: family_communication_counts
    # ------------------------------------------------------------------

    def _family_communication_counts(
        self,
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Count of messages between kindergarten and family, broken down by
        thread type and optionally filtered by period and kindergarten."""
        from services.agency_reports.base import _resolve_dos_period
        from utils.time_utils import jordan_date_range_filter

        start, end = _resolve_dos_period(filters)
        q = self.db.query(models.Message.thread_type, func.count(models.Message.id).label("count"))

        # Apply period filter
        q = q.filter(*jordan_date_range_filter(models.Message.created_at, start, end))

        # Apply kindergarten filter
        if filters.get("kindergarten_id"):
            q = q.filter(models.Message.kindergarten_id == int(filters["kindergarten_id"]))

        # Apply governorate filter via kindergarten join
        if filters.get("governorate") or filters.get("city"):
            q = q.join(models.Kindergarten, models.Kindergarten.id == models.Message.kindergarten_id)
            q = self._apply_kindergarten_geo_filters(q, filters)

        rows = q.group_by(models.Message.thread_type).all()
        breakdowns = [
            {"thread_type": _thread_type_ar(r.thread_type), "count": _safe_int(r.count)}
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)

        summary = {
            "message_count": total,
            "thread_types": len(breakdowns),
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        }

        payload = self._payload(report_code, report, filters, summary, breakdowns)

        # Add chart
        if breakdowns:
            payload["chart"] = {
                "type": "bar",
                "title_ar": "الرسائل حسب نوع المحادثة",
                "title_en": "Messages by Thread Type",
                "series": [
                    {"label": b["thread_type"], "value": b["count"]}
                    for b in sorted(breakdowns, key=lambda x: x["count"], reverse=True)
                ],
            }

        return payload
