"""Dynamic, privacy-safe services for official agency reports."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from agency_reports_registry import AGENCY_REPORT_REGISTRY, SENSITIVE_FIELD_DENYLIST

_JORDAN_TZ = timezone(timedelta(hours=3))


def _now_iso() -> str:
    return datetime.now(_JORDAN_TZ).isoformat()


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))


def _gender_ar(value: Any) -> str:
    raw = _enum_value(value)
    return {"MALE": "ذكر", "FEMALE": "أنثى"}.get(raw or "", "غير محدد")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den) * 100.0), 2) if den else 0.0


class AgencyReportError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AgencyReportsService:
    """Registry-driven report generator.

    All report payloads are aggregated-only by default. Sensitive fields are
    blocked centrally before the payload is returned or exported.
    """

    def __init__(self, db: Session):
        self.db = db

    def catalog(self) -> dict[str, Any]:
        agencies = []
        for code, agency in AGENCY_REPORT_REGISTRY.items():
            reports = []
            for report_code, report in agency["reports"].items():
                reports.append({
                    "agency_code": code,
                    "report_code": report_code,
                    "title_ar": report.get("title_ar"),
                    "title_en": report.get("title_en"),
                    "description_ar": report.get("description_ar"),
                    "status": report.get("status", "ready"),
                    "privacy_level": report.get("privacy_level", "aggregated_only"),
                    "filters": report.get("filters", []),
                    "exports": report.get("exports", []),
                    "data_sources": report.get("data_sources", []),
                    "reason_ar": report.get("reason_ar"),
                })
            agencies.append({
                "code": code,
                "name_ar": agency["name_ar"],
                "name_en": agency.get("name_en"),
                "description_ar": agency.get("description_ar"),
                "icon": agency.get("icon", "bi-bank"),
                "report_count": len(reports),
                "ready_report_count": sum(1 for r in reports if r["status"] == "ready"),
                "requires_data_count": sum(1 for r in reports if r["status"] != "ready"),
                "reports": reports,
            })
        return {"generated_at": _now_iso(), "agencies": agencies}

    def summary(self) -> dict[str, Any]:
        catalog = self.catalog()["agencies"]
        total_reports = sum(a["report_count"] for a in catalog)
        ready_reports = sum(a["ready_report_count"] for a in catalog)
        requires_data = sum(a["requires_data_count"] for a in catalog)
        return {
            "generated_at": _now_iso(),
            "agency_count": len(catalog),
            "report_count": total_reports,
            "ready_report_count": ready_reports,
            "requires_data_count": requires_data,
            "privacy_level": "aggregated_only",
            "data_quality_status": "partial" if requires_data else "sufficient",
            "agencies": [
                {
                    "code": a["code"],
                    "name_ar": a["name_ar"],
                    "name_en": a["name_en"],
                    "icon": a["icon"],
                    "report_count": a["report_count"],
                    "ready_report_count": a["ready_report_count"],
                    "requires_data_count": a["requires_data_count"],
                }
                for a in catalog
            ],
        }

    def reports_for_agency(self, agency_code: str) -> dict[str, Any]:
        agency = self._agency(agency_code)
        return {
            "agency_code": agency_code,
            "agency_name_ar": agency["name_ar"],
            "agency_name_en": agency.get("name_en"),
            "description_ar": agency.get("description_ar"),
            "reports": self.catalog()["agencies"][[a["code"] for a in self.catalog()["agencies"]].index(agency_code)]["reports"],
        }

    def generate_report(self, agency_code: str, report_code: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        agency = self._agency(agency_code)
        report = self._report(agency_code, report_code)
        filters = self._clean_filters(filters or {})

        if report.get("status") != "ready":
            payload = self._unavailable_payload(agency_code, agency, report_code, report, filters)
            self._assert_privacy(payload)
            return payload

        if agency_code == "moe" and report_code == "kg2_eligibility":
            payload = self._kg2_eligibility(agency_code, agency, report_code, report, filters)
        elif agency_code == "dos" and report_code == "children_statistical_profile":
            payload = self._children_profile(agency_code, agency, report_code, report, filters)
        elif agency_code == "ncfa" and report_code == "child_family_profile":
            payload = self._children_profile(agency_code, agency, report_code, report, filters)
        elif agency_code == "ncfa" and report_code == "family_communication_counts":
            payload = self._family_communication_counts(agency_code, agency, report_code, report, filters)
        elif agency_code == "mol" and report_code == "workforce_summary":
            payload = self._workforce_summary(agency_code, agency, report_code, report, filters)
        elif agency_code == "mol" and report_code == "training_compliance":
            payload = self._training_compliance(agency_code, agency, report_code, report, filters)
        elif agency_code == "mosd" and report_code == "kindergarten_registry":
            payload = self._kindergarten_registry(agency_code, agency, report_code, report, filters)
        elif agency_code == "mosd" and report_code == "child_safety_protection":
            payload = self._child_safety(agency_code, agency, report_code, report, filters)
        elif agency_code == "mopic" and report_code == "service_access_gaps":
            payload = self._service_access_gaps(agency_code, agency, report_code, report, filters)
        else:
            payload = self._unavailable_payload(agency_code, agency, report_code, report, filters, status="not_available")

        self._assert_privacy(payload)
        return payload

    def _agency(self, code: str) -> dict[str, Any]:
        agency = AGENCY_REPORT_REGISTRY.get(code)
        if not agency:
            raise AgencyReportError(404, "Agency not found")
        return agency

    def _report(self, agency_code: str, report_code: str) -> dict[str, Any]:
        report = self._agency(agency_code)["reports"].get(report_code)
        if not report:
            raise AgencyReportError(404, "Report not found")
        return report

    def _metadata(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any], status: str = "ready") -> dict[str, Any]:
        return {
            "agency_code": agency_code,
            "agency_name_ar": agency["name_ar"],
            "agency_name_en": agency.get("name_en"),
            "report_code": report_code,
            "report_title_ar": report.get("title_ar"),
            "report_title_en": report.get("title_en"),
            "generated_at": _now_iso(),
            "filters": filters,
            "aggregation_level": filters.get("aggregation_level", "governorate"),
            "geography_basis": filters.get("geography_basis") or report.get("default_geography_basis", "parent_residence"),
            "privacy_level": report.get("privacy_level", "aggregated_only"),
            "data_quality_status": "sufficient" if status == "ready" else status,
            "data_sources": report.get("data_sources", []),
            "excluded_sensitive_fields": sorted(SENSITIVE_FIELD_DENYLIST),
            "limitations": [],
            "accessibility_status": "wcag_2_1_aa_review_required",
        }

    def _clean_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in filters.items() if v not in (None, "", "null", "undefined")}

    def _unavailable_payload(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any], status: str | None = None) -> dict[str, Any]:
        status = status or report.get("status", "requires_structured_data")
        return {
            "metadata": self._metadata(agency_code, agency, report_code, report, filters, status=status),
            "summary": {"status": status, "message_ar": report.get("reason_ar") or "هذا التقرير غير متاح حاليًا."},
            "breakdowns": [],
            "charts": [],
            "tables": [],
            "unavailable_indicators": [{"code": report_code, "status": status, "message_ar": report.get("reason_ar")}],
            "exports": {"csv": False, "json": True},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
        }

    def _apply_parent_geo_filters(self, q, filters: dict[str, Any]):
        if filters.get("governorate"):
            q = q.filter(models.ParentProfile.home_governorate == filters["governorate"])
        if filters.get("city"):
            q = q.filter(models.ParentProfile.home_district == filters["city"])
        return q

    def _apply_kindergarten_geo_filters(self, q, filters: dict[str, Any]):
        if filters.get("governorate"):
            q = q.filter(models.Kindergarten.governorate == filters["governorate"])
        if filters.get("city"):
            q = q.filter(models.Kindergarten.district == filters["city"])
        if filters.get("kindergarten_id"):
            q = q.filter(models.Kindergarten.id == int(filters["kindergarten_id"]))
        return q

    def _kg2_eligibility(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        admission_year = int(filters.get("admission_year") or date.today().year)
        cutoff = date(admission_year - 5, 12, 31)
        q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.Child.gender,
                func.count(func.distinct(models.Child.id)).label("count"),
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
            .filter(models.Child.date_of_birth <= cutoff)
        )
        q = self._apply_parent_geo_filters(q, filters)
        if filters.get("gender"):
            q = q.filter(models.Child.gender == models.Gender(filters["gender"]))
        rows = q.group_by(models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.gender).all()
        breakdowns = [
            {
                "governorate": r.home_governorate or "غير محدد",
                "city": r.home_district or "غير محدد",
                "gender": _gender_ar(r.gender),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)
        return self._payload(agency_code, agency, report_code, report, filters, {
            "admission_year": admission_year,
            "cutoff_date": date(admission_year, 12, 31).isoformat(),
            "eligible_children": total,
        }, breakdowns)

    def _children_profile(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.gender, func.count(models.Child.id).label("count"))
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        if filters.get("gender"):
            q = q.filter(models.Child.gender == models.Gender(filters["gender"]))
        rows = q.group_by(models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.gender).all()
        breakdowns = [
            {"governorate": r.home_governorate or "غير محدد", "city": r.home_district or "غير محدد", "gender": _gender_ar(r.gender), "count": _safe_int(r.count)}
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)
        return self._payload(agency_code, agency, report_code, report, filters, {"total_children": total}, breakdowns)

    def _kindergarten_registry(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = self.db.query(models.Kindergarten.governorate, models.Kindergarten.district, models.Kindergarten.status, func.count(models.Kindergarten.id).label("count"))
        q = self._apply_kindergarten_geo_filters(q, filters)
        if filters.get("status"):
            q = q.filter(models.Kindergarten.status == models.KindergartenStatus(filters["status"]))
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district, models.Kindergarten.status).all()
        breakdowns = [
            {"governorate": r.governorate or "غير محدد", "city": r.district or "غير محدد", "status": _enum_value(r.status), "count": _safe_int(r.count)}
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)
        active = sum(r["count"] for r in breakdowns if r.get("status") == "ACTIVE")
        return self._payload(agency_code, agency, report_code, report, filters, {"total_kindergartens": total, "active_kindergartens": active}, breakdowns)

    def _workforce_summary(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(models.Kindergarten.governorate, models.Kindergarten.district, models.User.role, func.count(models.User.id).label("count"))
            .join(models.Kindergarten, models.Kindergarten.id == models.User.kindergarten_id)
            .filter(models.User.deleted_at.is_(None), models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]))
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district, models.User.role).all()
        breakdowns = [
            {"governorate": r.governorate or "غير محدد", "city": r.district or "غير محدد", "role": _enum_value(r.role), "count": _safe_int(r.count)}
            for r in rows
        ]
        supervisors = sum(r["count"] for r in breakdowns if r.get("role") == "SUPERVISOR")
        managers = sum(r["count"] for r in breakdowns if r.get("role") == "MANAGER")
        return self._payload(agency_code, agency, report_code, report, filters, {"managers": managers, "supervisors": supervisors, "total_staff": managers + supervisors}, breakdowns)

    def _training_compliance(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        total = self.db.query(func.count(models.StaffTrainingCompletion.id)).scalar() or 0
        completed = self.db.query(func.count(models.StaffTrainingCompletion.id)).filter(models.StaffTrainingCompletion.status == models.TrainingStatus.COMPLETED).scalar() or 0
        breakdowns = [{"status": "COMPLETED", "count": _safe_int(completed)}, {"status": "TOTAL", "count": _safe_int(total)}]
        return self._payload(agency_code, agency, report_code, report, filters, {"training_records": _safe_int(total), "completed": _safe_int(completed), "completion_rate_pct": _safe_pct(completed, total)}, breakdowns)

    def _family_communication_counts(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = self.db.query(models.Message.thread_type, func.count(models.Message.id).label("count"))
        if filters.get("kindergarten_id"):
            q = q.filter(models.Message.kindergarten_id == int(filters["kindergarten_id"]))
        rows = q.group_by(models.Message.thread_type).all()
        breakdowns = [{"thread_type": _enum_value(r.thread_type), "count": _safe_int(r.count)} for r in rows]
        return self._payload(agency_code, agency, report_code, report, filters, {"message_count": sum(r["count"] for r in breakdowns)}, breakdowns)

    def _child_safety(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(models.Kindergarten.governorate, models.Kindergarten.district, models.Incident.severity_level, func.count(models.Incident.id).label("count"))
            .join(models.Kindergarten, models.Kindergarten.id == models.Incident.kindergarten_id)
            .filter(models.Incident.deleted_at.is_(None))
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        if filters.get("severity"):
            q = q.filter(models.Incident.severity_level == models.SeverityLevel(filters["severity"]))
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district, models.Incident.severity_level).all()
        breakdowns = [{"governorate": r.governorate or "غير محدد", "city": r.district or "غير محدد", "severity": _enum_value(r.severity_level), "count": _safe_int(r.count)} for r in rows]
        return self._payload(agency_code, agency, report_code, report, filters, {"incident_count": sum(r["count"] for r in breakdowns)}, breakdowns)

    def _service_access_gaps(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        child_rows = (
            self.db.query(models.ParentProfile.home_governorate, models.ParentProfile.home_district, func.count(models.Child.id).label("children"))
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
            .group_by(models.ParentProfile.home_governorate, models.ParentProfile.home_district)
            .all()
        )
        kg_rows = (
            self.db.query(models.Kindergarten.governorate, models.Kindergarten.district, func.count(models.Kindergarten.id).label("kindergartens"))
            .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
            .group_by(models.Kindergarten.governorate, models.Kindergarten.district)
            .all()
        )
        kg_index = {(r.governorate, r.district): _safe_int(r.kindergartens) for r in kg_rows}
        breakdowns = []
        for r in child_rows:
            key = (r.home_governorate, r.home_district)
            children = _safe_int(r.children)
            kgs = kg_index.get(key, 0)
            breakdowns.append({"governorate": r.home_governorate or "غير محدد", "city": r.home_district or "غير محدد", "children": children, "active_kindergartens": kgs, "children_per_kindergarten": round(children / max(kgs, 1), 2)})
        return self._payload(agency_code, agency, report_code, report, filters, {"areas": len(breakdowns), "children": sum(r["children"] for r in breakdowns), "active_kindergartens": sum(r["active_kindergartens"] for r in breakdowns)}, sorted(breakdowns, key=lambda x: x["children_per_kindergarten"], reverse=True))

    def _payload(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any], summary: dict[str, Any], breakdowns: list[dict[str, Any]]) -> dict[str, Any]:
        table = {"caption_ar": report.get("title_ar"), "rows": breakdowns}
        return {
            "metadata": self._metadata(agency_code, agency, report_code, report, filters),
            "summary": summary,
            "breakdowns": breakdowns,
            "charts": [{"type": "bar", "title_ar": report.get("title_ar"), "data": breakdowns[:20]}],
            "tables": [table],
            "unavailable_indicators": [],
            "exports": {"csv": "csv" in report.get("exports", []), "json": "json" in report.get("exports", [])},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
        }

    def _assert_privacy(self, payload: Any) -> None:
        text_keys: list[str] = []
        def visit(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    lowered = str(key).lower()
                    if lowered in SENSITIVE_FIELD_DENYLIST and lowered not in {"excluded_sensitive_fields"}:
                        text_keys.append(path + str(key))
                    visit(value, f"{path}{key}.")
            elif isinstance(obj, list):
                for item in obj:
                    visit(item, path)
        visit(payload)
        if text_keys:
            raise AgencyReportError(500, f"Sensitive fields blocked from official agency report: {', '.join(text_keys)}")
