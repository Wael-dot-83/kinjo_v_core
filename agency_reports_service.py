"""Dynamic, privacy-safe services for official agency reports."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from agency_reports_registry import AGENCY_REPORT_REGISTRY, SENSITIVE_FIELD_DENYLIST
from config import settings

_JORDAN_TZ = timezone(timedelta(hours=3))


def _min_cell_size() -> int:
    """Statistical disclosure threshold: category counts below this are
    suppressed. Configurable via AGENCY_REPORT_MIN_CELL_SIZE; safe default 5.
    A value <= 1 disables suppression."""
    try:
        return max(0, int(os.getenv("AGENCY_REPORT_MIN_CELL_SIZE", "5")))
    except (TypeError, ValueError):
        return 5


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


# Arabic labels for the raw summary/column keys emitted by the report
# generators, so the UI never shows machine field names (e.g. "eligible_children").
_FIELD_LABELS: dict[str, str] = {
    # summary fields
    "admission_year": "سنة القبول",
    "cutoff_date": "تاريخ القطع (مواليد قبل)",
    "eligible_children": "الأطفال المؤهلون",
    "total_children": "إجمالي الأطفال",
    "total_kindergartens": "إجمالي الحضانات",
    "active_kindergartens": "الحضانات النشطة",
    "managers": "المدراء",
    "supervisors": "المشرفون",
    "total_staff": "إجمالي الكوادر",
    "training_records": "سجلات التدريب",
    "completed": "المكتملة",
    "completion_rate_pct": "نسبة الإكمال %",
    "message_count": "عدد الرسائل",
    "incident_count": "عدد الحوادث",
    "areas": "عدد المناطق",
    "children": "الأطفال",
    "enrolled_children": "الأطفال المسجلون",
    "total_institutions": "إجمالي المؤسسات",
    "active_institutions": "المؤسسات النشطة",
    "total_capacity": "الطاقة الاستيعابية",
    "total_enrolled": "العدد الفعلي للمسجلين",
    "occupancy_rate_pct": "نسبة الإشغال %",
    "total_records": "إجمالي السجلات",
    "total_supervisors": "إجمالي المشرفين",
    "children_missing_dob": "أطفال بدون تاريخ ميلاد",
    "trend_years": "سنوات القياس",

    # table columns
    "governorate": "المحافظة",
    "city": "المدينة/اللواء",
    "district": "اللواء",
    "gender": "الجنس",
    "count": "العدد",
    "status": "الحالة",
    "role": "الدور",
    "severity": "درجة الخطورة",
    "thread_type": "نوع المحادثة",
    "children_per_kindergarten": "أطفال لكل حضانة",
    "age_group": "الفئة العمرية",
    "enrolled_total": "إجمالي المسجلين (0-60)",
    "enrolled_0_11m": "0-11 شهر",
    "enrolled_12_23m": "12-23 شهر",
    "enrolled_24_35m": "24-35 شهر",
    "enrolled_36_47m": "36-47 شهر",
    "enrolled_48_60m": "48-60 شهر",
    "occupancy_rate": "نسبة الإشغال",
    "enrolled": "الأطفال المسجلين",
    "children_per_supervisor": "أطفال لكل مشرف",
    "missing_dob": "بدون تاريخ ميلاد",
    "year": "السنة",
    "new_kindergartens": "حضانات جديدة",
    
    # vaccination_due_children
    "vaccine": "المطعوم",
    "due_age": "العمر المستحق",
    "vaccines_in_schedule": "عدد المطاعيم في الجدول",
    "children_considered": "الأطفال المشمولون",
    "vaccine_doses_due": "إجمالي الجرعات المستحقة",
}


def _label_map(keys) -> dict[str, str]:
    return {k: _FIELD_LABELS.get(k, k) for k in keys}


class AgencyReportsService:
    """Registry-driven report generator.

    All report payloads are aggregated-only by default. Sensitive fields are
    blocked centrally before the payload is returned or exported.
    """

    def __init__(self, db: Session):
        self.db = db
        # Per-request memo for expected-child-day computation, which several
        # indicators (attendance, daily reports, incident rate) share.
        self._expected_cache: dict[Any, tuple[int, dict[int, int]]] = {}

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

        # vaccination_due_children becomes available once a national immunization
        # schedule has been uploaded (status in the registry is a static placeholder).
        if agency_code == "moh" and report_code == "vaccination_due_children":
            import immunization_service
            if immunization_service.schedule_count(self.db) > 0:
                payload = self._vaccination_due_children(agency_code, agency, report_code, report, filters)
                self._assert_privacy(payload)
                return payload
            payload = self._unavailable_payload(
                agency_code, agency, report_code, report, filters,
            )
            payload["summary"]["message_ar"] = (
                "لم يتم رفع جدول المطاعيم الوطني بعد. حمّل قالب Excel، عبّئ المطاعيم "
                "والأعمار المستحقة، ثم ارفعه لتوليد التقرير."
            )
            payload["unavailable_indicators"] = [{
                "code": report_code, "status": "awaiting_schedule_upload",
                "message_ar": payload["summary"]["message_ar"],
            }]
            self._assert_privacy(payload)
            return payload

        if report.get("status") != "ready":
            payload = self._unavailable_payload(agency_code, agency, report_code, report, filters)
            self._assert_privacy(payload)
            return payload

        if agency_code == "moe" and report_code == "kg2_eligibility":
            payload = self._kg2_eligibility(agency_code, agency, report_code, report, filters)
        elif agency_code == "dos":
            if report_code == "children_demographics":
                payload = self._dos_children_demographics(agency_code, agency, report_code, report, filters)
            elif report_code == "enrollment_participation_0_60":
                payload = self._dos_enrollment_participation(agency_code, agency, report_code, report, filters)
            elif report_code == "institutions_active_licensed":
                payload = self._dos_institutions_active(agency_code, agency, report_code, report, filters)
            elif report_code == "capacity_occupancy_overcrowding":
                payload = self._dos_capacity_occupancy(agency_code, agency, report_code, report, filters)
            elif report_code == "monthly_attendance_absence":
                payload = self._dos_monthly_attendance(agency_code, agency, report_code, report, filters)
            elif report_code == "supervisors_child_ratio":
                payload = self._dos_supervisors_child_ratio(agency_code, agency, report_code, report, filters)
            elif report_code == "incidents_safety_1000_child_days":
                payload = self._dos_incidents_safety(agency_code, agency, report_code, report, filters)
            elif report_code == "geographic_service_gaps":
                payload = self._service_access_gaps(agency_code, agency, report_code, report, filters)
            elif report_code == "data_quality_completeness":
                payload = self._dos_data_quality(agency_code, agency, report_code, report, filters)
            elif report_code == "annual_quarterly_trends":
                payload = self._dos_annual_trends(agency_code, agency, report_code, report, filters)
            else:
                payload = self._unavailable_payload(agency_code, agency, report_code, report, filters, status="not_available")
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
        cleaned = {k: v for k, v in filters.items() if v not in (None, "", "null", "undefined")}
        # Normalize governorate aliases so a filter value like "العاصمة" (official
        # admin name) or "Amman" matches the value stored on records ("عمان").
        # Without this, selecting "العاصمة" returned zero rows for the capital.
        gov = cleaned.get("governorate")
        if isinstance(gov, str):
            aliases = settings.JORDAN_GOVERNORATE_ALIASES
            cleaned["governorate"] = aliases.get(gov) or aliases.get(gov.lower(), gov)
        return cleaned

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

    def _vaccination_due_children(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        """Age-eligibility report: count children whose age has reached each
        vaccine's scheduled age in the uploaded national immunization schedule.

        Aggregated only. 'Due' means age-eligible — the system holds no record of
        which vaccines a child already received, so this is not per-child overdue.
        """
        import immunization_service

        schedule = immunization_service.get_schedule(self.db)
        today = datetime.now(_JORDAN_TZ).date()

        # One pass over the (filtered) child population; bucket per vaccine in Python
        # to avoid one query per vaccine.
        q = (
            self.db.query(
                models.ParentProfile.home_governorate.label("gov"),
                models.Child.gender.label("gender"),
                models.Child.date_of_birth.label("dob"),
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        gender_filter = filters.get("gender")
        if gender_filter:
            try:
                q = q.filter(models.Child.gender == models.Gender(str(gender_filter).upper()))
            except ValueError:
                pass  # unknown gender value → ignore filter rather than 500

        children = q.all()
        children_considered = len(children)

        # counts keyed by (vaccine_label, governorate, gender_ar)
        detail: dict[tuple[str, str, str], int] = defaultdict(int)
        per_vaccine: dict[str, int] = defaultdict(int)
        vaccine_order: list[str] = []
        vaccine_seen: set[str] = set()

        for row in schedule:
            label = f"{row.vaccine_name} ({row.age_value} {immunization_service.unit_label_ar(row.age_unit)})"
            if label not in vaccine_seen:
                vaccine_seen.add(label)
                vaccine_order.append(label)
            for child in children:
                age_days = (today - child.dob).days
                if age_days >= row.due_age_days:
                    gov = child.gov or "غير محدد"
                    gender_ar = _gender_ar(child.gender)
                    detail[(label, gov, gender_ar)] += 1
                    per_vaccine[label] += 1

        breakdowns = [
            {"vaccine": vac, "governorate": gov, "gender": gender_ar, "count": cnt}
            for (vac, gov, gender_ar), cnt in sorted(detail.items(), key=lambda kv: (-kv[1], kv[0][0]))
            if cnt > 0
        ]
        chart_series = [
            {"label": vac, "value": per_vaccine.get(vac, 0)}
            for vac in vaccine_order if per_vaccine.get(vac, 0) > 0
        ]
        doses_due = sum(per_vaccine.values())

        summary = {
            "vaccines_in_schedule": len(schedule),
            "children_considered": children_considered,
            "vaccine_doses_due": doses_due,
        }
        payload = self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns)
        payload["chart"] = {
            "type": "bar",
            "title_ar": "الأطفال المستحقون لكل مطعوم",
            "series": chart_series,
        }
        payload["exports"] = {"csv": True, "json": True}
        payload["metadata"]["limitations"] = [
            "التقرير يعتمد على العمر فقط (استحقاق عمري) ولا يعكس سجل التطعيم الفعلي لكل طفل.",
        ]
        return payload

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

    def _dos_children_demographics(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
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

    def _dos_enrollment_participation(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        today = datetime.now(_JORDAN_TZ).date()
        date_60m_ago = today - timedelta(days=60*30)
        q = (
            self.db.query(models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.date_of_birth)
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
            .filter(
                models.Child.deleted_at.is_(None),
                models.ParentProfile.deleted_at.is_(None),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                models.Child.date_of_birth >= date_60m_ago,
                models.Child.date_of_birth <= today
            )
        )
        q = self._apply_parent_geo_filters(q, filters)
        if filters.get("gender"):
            q = q.filter(models.Child.gender == models.Gender(filters["gender"]))
        
        rows = q.all()
        
        detail = defaultdict(lambda: {"total": 0, "0_11": 0, "12_23": 0, "24_35": 0, "36_47": 0, "48_60": 0})
        for r in rows:
            gov = r.home_governorate or "غير محدد"
            city = r.home_district or "غير محدد"
            dob = r.date_of_birth
            age_months = (today - dob).days // 30
            key = (gov, city)
            detail[key]["total"] += 1
            if age_months < 12:
                detail[key]["0_11"] += 1
            elif age_months < 24:
                detail[key]["12_23"] += 1
            elif age_months < 36:
                detail[key]["24_35"] += 1
            elif age_months < 48:
                detail[key]["36_47"] += 1
            else:
                detail[key]["48_60"] += 1

        breakdowns = [
            {
                "governorate": k[0], "city": k[1], 
                "enrolled_total": v["total"],
                "enrolled_0_11m": v["0_11"],
                "enrolled_12_23m": v["12_23"],
                "enrolled_24_35m": v["24_35"],
                "enrolled_36_47m": v["36_47"],
                "enrolled_48_60m": v["48_60"],
            }
            for k, v in detail.items()
        ]
        breakdowns.sort(key=lambda x: x["enrolled_total"], reverse=True)
        total = sum(r["enrolled_total"] for r in breakdowns)

        # Meaningful chart: pie chart for age distribution
        total_by_age = {
            "0-11 شهر": sum(b["enrolled_0_11m"] for b in breakdowns),
            "12-23 شهر": sum(b["enrolled_12_23m"] for b in breakdowns),
            "24-35 شهر": sum(b["enrolled_24_35m"] for b in breakdowns),
            "36-47 شهر": sum(b["enrolled_36_47m"] for b in breakdowns),
            "48-60 شهر": sum(b["enrolled_48_60m"] for b in breakdowns),
        }
        chart_series = [{"label": k, "value": v} for k, v in total_by_age.items() if v > 0]
        
        chart = {
            "type": "pie",
            "title_ar": "التوزيع العمري للأطفال المسجلين (0-60 شهراً)",
            "series": chart_series
        }

        return self._payload(agency_code, agency, report_code, report, filters, {"enrolled_children": total}, breakdowns, chart=chart)

    def _dos_institutions_active(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
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
        return self._payload(agency_code, agency, report_code, report, filters, {"total_institutions": total, "active_institutions": active}, breakdowns)

    def _dos_capacity_occupancy(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.sum(models.Class.capacity_total).label("capacity"),
                func.sum(models.Class.enrolled_children_count).label("enrolled")
            )
            .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
            .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE, models.Class.is_active == True, models.Class.deleted_at.is_(None))
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "total_capacity": _safe_int(r.capacity),
                "total_enrolled": _safe_int(r.enrolled),
                "occupancy_rate": _safe_pct(r.enrolled, r.capacity)
            }
            for r in rows
        ]
        total_cap = sum(r["total_capacity"] for r in breakdowns)
        total_enr = sum(r["total_enrolled"] for r in breakdowns)
        return self._payload(agency_code, agency, report_code, report, filters, {"total_capacity": total_cap, "total_enrolled": total_enr, "occupancy_rate_pct": _safe_pct(total_enr, total_cap)}, breakdowns)

    def _dos_monthly_attendance(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.AttendanceLog.status,
                func.count(models.AttendanceLog.id).label("count")
            )
            .join(models.Kindergarten, models.Kindergarten.id == models.AttendanceLog.kindergarten_id)
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district, models.AttendanceLog.status).all()
        breakdowns = [
            {"governorate": r.governorate or "غير محدد", "city": r.district or "غير محدد", "status": _enum_value(r.status), "count": _safe_int(r.count)}
            for r in rows
        ]
        total_attendance = sum(r["count"] for r in breakdowns)
        return self._payload(agency_code, agency, report_code, report, filters, {"total_records": total_attendance}, breakdowns)

    def _dos_supervisors_child_ratio(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.count(models.Class.supervisor_id).label("supervisors"),
                func.sum(models.Class.enrolled_children_count).label("enrolled")
            )
            .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
            .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE, models.Class.is_active == True, models.Class.deleted_at.is_(None))
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "supervisors": _safe_int(r.supervisors),
                "enrolled": _safe_int(r.enrolled),
                "children_per_supervisor": round(_safe_int(r.enrolled) / max(_safe_int(r.supervisors), 1), 2)
            }
            for r in rows
        ]
        total_sup = sum(r["supervisors"] for r in breakdowns)
        total_enr = sum(r["enrolled"] for r in breakdowns)
        return self._payload(agency_code, agency, report_code, report, filters, {"total_supervisors": total_sup, "total_enrolled": total_enr}, breakdowns)

    def _dos_incidents_safety(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
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

    def _dos_data_quality(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(models.ParentProfile.home_governorate, models.ParentProfile.home_district, func.count(models.Child.id).label("count"))
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.Child.date_of_birth.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        rows = q.group_by(models.ParentProfile.home_governorate, models.ParentProfile.home_district).all()
        breakdowns = [{"governorate": r.home_governorate or "غير محدد", "city": r.home_district or "غير محدد", "missing_dob": _safe_int(r.count)} for r in rows]
        return self._payload(agency_code, agency, report_code, report, filters, {"children_missing_dob": sum(r["missing_dob"] for r in breakdowns)}, breakdowns)

    def _dos_annual_trends(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        q = (
            self.db.query(func.extract('year', models.Kindergarten.created_at).label("year"), func.count(models.Kindergarten.id).label("count"))
            .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        )
        rows = q.group_by(func.extract('year', models.Kindergarten.created_at)).all()
        breakdowns = [{"year": str(int(r.year)) if r.year else "غير محدد", "new_kindergartens": _safe_int(r.count)} for r in rows]
        return self._payload(agency_code, agency, report_code, report, filters, {"trend_years": len(breakdowns)}, breakdowns)

    def _payload(self, agency_code: str, agency: dict[str, Any], report_code: str, report: dict[str, Any], filters: dict[str, Any], summary: dict[str, Any], breakdowns: list[dict[str, Any]], chart: dict[str, Any] | None = None) -> dict[str, Any]:
        table = {"caption_ar": report.get("title_ar"), "rows": breakdowns}
        
        if chart is None and breakdowns:
            keys = list(breakdowns[0].keys())
            label_col = keys[0] if keys else ""
            val_col = keys[-1] if keys else ""
            if label_col and val_col:
                series = [{"label": str(b.get(label_col, "")), "value": b.get(val_col, 0)} for b in breakdowns[:15]]
                chart = {"type": "bar", "title_ar": report.get("title_ar"), "series": series}

        payload = {
            "metadata": self._metadata(agency_code, agency, report_code, report, filters),
            "summary": summary,
            "summary_labels": _label_map(summary.keys()),
            "column_labels": _label_map(breakdowns[0].keys() if breakdowns else []),
            "breakdowns": breakdowns,
            "tables": [table],
            "unavailable_indicators": [],
            "exports": {"csv": "csv" in report.get("exports", []), "json": "json" in report.get("exports", [])},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
        }
        if chart:
            payload["chart"] = chart
        return payload

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

    # ------------------------------------------------------------------
    # Custom Reports (التقارير المخصصة)
    # ------------------------------------------------------------------
    def custom_report_schema(self) -> dict[str, Any]:
        from agency_reports_registry import custom_report_schema
        return custom_report_schema()

    def custom_report(self, scope: dict[str, Any] | None) -> dict[str, Any]:
        """Build an aggregated custom report from a validated scope.

        Every indicator is computed from real data. Indicators whose data is
        not structurally available are never fabricated — they are reported in
        ``data_quality.notes`` instead.
        """
        from agency_reports_registry import custom_report_schema

        scope = scope or {}
        schema = custom_report_schema()
        agencies = {a["code"]: a for a in schema["agencies"]}
        levels = {lvl["code"]: lvl for lvl in schema["levels"]}
        periods = {p["code"]: p for p in schema["periods"]}
        ind_status: dict[str, str] = {}
        ind_name: dict[str, str] = {}
        for domain in schema["domains"]:
            for ind in domain["indicators"]:
                ind_status[ind["code"]] = ind["status"]
                ind_name[ind["code"]] = ind["name_ar"]

        agency = scope.get("agency")
        level = scope.get("level") or "national"
        period = scope.get("period") or "month"
        indicators = scope.get("indicators") or []

        if agency not in agencies:
            raise AgencyReportError(400, "الجهة المستفيدة غير صالحة / Invalid agency")
        if level not in levels:
            raise AgencyReportError(400, "مستوى التقرير غير صالح / Invalid report level")
        if period not in periods:
            raise AgencyReportError(400, "الفترة الزمنية غير صالحة / Invalid period")
        if not isinstance(indicators, list) or not indicators:
            raise AgencyReportError(400, "اختر مؤشرًا واحدًا على الأقل / Select at least one indicator")
        unknown = [i for i in indicators if i not in ind_status]
        if unknown:
            raise AgencyReportError(400, "مؤشرات غير معروفة / Unknown indicators: " + ", ".join(map(str, unknown)))

        start_date, end_date = self._resolve_custom_period(period, periods, scope)
        filters = self._clean_custom_geo(scope)

        kpis: list[dict[str, Any]] = []
        charts: list[dict[str, Any]] = []
        table: list[dict[str, Any]] = []
        notes: list[str] = []
        quality_notes: list[str] = []

        for code in indicators:
            if ind_status.get(code) != "ready":
                quality_notes.append(f"{ind_name.get(code, code)}: يتطلب بيانات منظمة غير متوفرة حاليًا.")
                continue
            try:
                result = self._custom_indicator(code, filters, start_date, end_date)
            except AgencyReportError:
                raise
            except Exception:  # noqa: BLE001 - a single broken indicator must not 500 the whole report
                quality_notes.append(f"{ind_name.get(code, code)}: تعذّر احتساب هذا المؤشر.")
                continue
            if result.get("kpi"):
                kpi = result["kpi"]
                kpis.append(kpi)
                # An unavailable (None) value must be reflected in data quality,
                # not silently presented as a real figure — this also downgrades
                # the overall status from "sufficient" to "limited".
                if kpi.get("value") is None:
                    quality_notes.append(
                        f"{ind_name.get(code, code)}: غير متاح ضمن النطاق المحدد (لا يوجد مقام صالح للاحتساب)."
                    )
            if result.get("chart"):
                charts.append(result["chart"])
            table.extend(result.get("rows", []))
            if result.get("note"):
                notes.append(result["note"])

        if kpis and not quality_notes:
            status = "sufficient"
        elif kpis:
            status = "limited"
        else:
            status = "incomplete"

        scope_out = {
            "agency": agency,
            "agency_name_ar": agencies[agency]["name_ar"],
            "level": level,
            "level_name_ar": levels[level]["name_ar"],
            "governorate": filters.get("governorate"),
            "city": filters.get("city"),
            "kindergarten_id": filters.get("kindergarten_id"),
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        # Statistical disclosure control: blank identifying small category counts
        # before the payload leaves the service (applies to JSON and CSV alike).
        suppressed_cells = self._apply_small_cell_suppression(charts, table)
        if suppressed_cells:
            quality_notes.append(
                f"تم حجب {suppressed_cells} خلية بأعداد صغيرة لحماية الخصوصية (الحد الأدنى {_min_cell_size()})."
            )
        payload = {
            "title": "تقرير مخصص",
            "generated_at": _now_iso(),
            "scope": scope_out,
            "kpis": kpis,
            "table": table,
            "charts": charts,
            "summary_ar": self._custom_summary_ar(scope_out, kpis, status),
            "decision_notes_ar": notes,
            "data_quality": {"status": status, "notes": quality_notes, "suppressed_cells": suppressed_cells},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
            "excluded_sensitive_fields": sorted(SENSITIVE_FIELD_DENYLIST),
        }
        self._assert_privacy(payload)
        return payload

    def _resolve_custom_period(self, period: str, periods: dict[str, Any], scope: dict[str, Any]) -> tuple[date, date]:
        today = datetime.now(_JORDAN_TZ).date()
        if period == "custom":
            raw_start = scope.get("start_date")
            raw_end = scope.get("end_date")
            if not raw_start or not raw_end:
                raise AgencyReportError(400, "حدد تاريخ البداية والنهاية / Provide start_date and end_date")
            try:
                start = date.fromisoformat(str(raw_start))
                end = date.fromisoformat(str(raw_end))
            except (TypeError, ValueError):
                raise AgencyReportError(400, "صيغة التاريخ غير صحيحة / Invalid date format (YYYY-MM-DD)")
            if start > end:
                raise AgencyReportError(400, "تاريخ البداية يجب أن يسبق تاريخ النهاية / start_date must be <= end_date")
            return start, end
        days = periods[period].get("days") or 30
        return today - timedelta(days=days), today

    def _clean_custom_geo(self, scope: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        gov = scope.get("governorate")
        city = scope.get("city")
        kg = scope.get("kindergarten_id")
        if gov not in (None, "", "null"):
            out["governorate"] = str(gov)
        if city not in (None, "", "null"):
            out["city"] = str(city)
        if kg not in (None, "", "null"):
            try:
                out["kindergarten_id"] = int(kg)
            except (TypeError, ValueError):
                raise AgencyReportError(400, "معرف الحضانة غير صالح / Invalid kindergarten_id")
        return out

    def _custom_kg_ids(self, filters: dict[str, Any]) -> list[int] | None:
        """KG ids matching the geo scope, or None for national (no restriction)."""
        if not (filters.get("governorate") or filters.get("city") or filters.get("kindergarten_id")):
            return None
        q = self.db.query(models.Kindergarten.id).filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)
        if filters.get("governorate"):
            q = q.filter(models.Kindergarten.governorate == filters["governorate"])
        if filters.get("city"):
            q = q.filter(models.Kindergarten.district == filters["city"])
        if filters.get("kindergarten_id"):
            q = q.filter(models.Kindergarten.id == filters["kindergarten_id"])
        return [r[0] for r in q.all()]

    @staticmethod
    def _kpi(code: str, label_ar: str, value: Any, unit_ar: str = "") -> dict[str, Any]:
        return {"code": code, "label_ar": label_ar, "value": value, "unit_ar": unit_ar}

    def _custom_indicator(self, code: str, filters: dict[str, Any], start: date, end: date) -> dict[str, Any]:
        kg_ids = self._custom_kg_ids(filters)
        m = self._custom_dispatch()
        fn = m.get(code)
        if not fn:
            return {}
        return fn(kg_ids, start, end)

    def _custom_dispatch(self) -> dict[str, Any]:
        return {
            "children_count": self._ind_children_count,
            "gender_distribution": self._ind_gender_distribution,
            "age_distribution_6mo": self._ind_age_distribution,
            "enrollment_status": self._ind_enrollment_status,
            "kindergarten_count": self._ind_kindergarten_count,
            "kindergarten_status": self._ind_kindergarten_status,
            "occupancy_rate": self._ind_occupancy_rate,
            "attendance_rate": self._ind_attendance_rate,
            "absence_requests": self._ind_absence_requests,
            "daily_report_completion": self._ind_daily_report_completion,
            "late_reports": self._ind_late_reports,
            "critical_incidents": self._ind_critical_incidents,
            "incidents_by_severity": self._ind_incidents_by_severity,
            "staff_count": self._ind_staff_count,
            "unassigned_classes": self._ind_unassigned_classes,
            "unassigned_children": self._ind_unassigned_children,
            "data_quality_score": self._ind_data_quality_score,
            "service_access_ratio": self._ind_service_access_ratio,
        }

    # -- children / enrollment ----------------------------------------
    def _enrolled_child_ids_subq(self, kg_ids: list[int] | None):
        q = self.db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
        if kg_ids is not None:
            q = q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        return q

    def _child_base_query(self, kg_ids: list[int] | None):
        q = self.db.query(models.Child).filter(models.Child.deleted_at.is_(None))
        if kg_ids is not None:
            q = q.filter(models.Child.id.in_(self._enrolled_child_ids_subq(kg_ids)))
        return q

    def _ind_children_count(self, kg_ids, start, end):
        total = self._child_base_query(kg_ids).count()
        return {
            "kpi": self._kpi("children_count", "عدد الأطفال", total, "طفل"),
            "rows": [{"المؤشر": "عدد الأطفال", "القيمة": total}],
            "note": f"إجمالي عدد الأطفال ضمن النطاق: {total}.",
        }

    def _ind_gender_distribution(self, kg_ids, start, end):
        q = self.db.query(models.Child.gender, func.count(models.Child.id)).filter(models.Child.deleted_at.is_(None))
        if kg_ids is not None:
            q = q.filter(models.Child.id.in_(self._enrolled_child_ids_subq(kg_ids)))
        rows = q.group_by(models.Child.gender).all()
        series = [{"label": _gender_ar(g), "value": _safe_int(c)} for g, c in rows]
        total = sum(s["value"] for s in series)
        males = next((s["value"] for s in series if s["label"] == "ذكر"), 0)
        return {
            "kpi": self._kpi("gender_distribution", "نسبة الذكور", _safe_pct(males, total), "%"),
            "chart": {"type": "pie", "title_ar": "التوزيع حسب الجنس", "series": series},
            "rows": [{"المؤشر": "التوزيع حسب الجنس", "الفئة": s["label"], "القيمة": s["value"]} for s in series],
        }

    def _ind_age_distribution(self, kg_ids, start, end):
        # Age is computed as of the reporting period end, using full year/month/day
        # boundaries (not a year+month approximation). Children with a missing or
        # invalid date of birth stay visible as a data-quality category rather
        # than being silently dropped from the distribution.
        ref = end
        buckets: dict[str, int] = defaultdict(int)
        unknown = 0
        for (dob,) in self._child_base_query(kg_ids).with_entities(models.Child.date_of_birth).all():
            if not dob:
                unknown += 1
                continue
            months = (ref.year - dob.year) * 12 + (ref.month - dob.month)
            if ref.day < dob.day:
                months -= 1
            months = max(months, 0)
            low = (months // 6) * 6
            buckets[f"{low}-{low + 6} شهر"] += 1
        series = [{"label": k, "value": v} for k, v in sorted(buckets.items(), key=lambda kv: int(kv[0].split("-")[0]))]
        band_count = len(series)
        if unknown:
            series.append({"label": "غير معروف", "value": unknown})
        return {
            "kpi": self._kpi("age_distribution_6mo", "عدد الفئات العمرية (كل 6 أشهر)", band_count, "فئة"),
            "chart": {"type": "bar", "title_ar": "التوزيع العمري كل 6 أشهر", "series": series},
            "rows": [{"المؤشر": "التوزيع العمري", "الفئة": s["label"], "القيمة": s["value"]} for s in series],
            "note": (f"يوجد {unknown} طفل بدون تاريخ ميلاد صالح ضمن النطاق." if unknown else None),
        }

    def _ind_enrollment_status(self, kg_ids, start, end):
        q = self.db.query(models.EnrollmentApplication.status, func.count(models.EnrollmentApplication.id))
        if kg_ids is not None:
            q = q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        rows = q.group_by(models.EnrollmentApplication.status).all()
        series = [{"label": _enum_value(s), "value": _safe_int(c)} for s, c in rows]
        active = next((s["value"] for s in series if s["label"] == "ACTIVE"), 0)
        return {
            "kpi": self._kpi("enrollment_status", "التسجيلات النشطة", active, "تسجيل"),
            "chart": {"type": "bar", "title_ar": "حالة التسجيل", "series": series},
            "rows": [{"المؤشر": "حالة التسجيل", "الفئة": s["label"], "القيمة": s["value"]} for s in series],
        }

    # -- kindergartens / capacity -------------------------------------
    def _kg_query(self, kg_ids: list[int] | None):
        q = self.db.query(models.Kindergarten).filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)
        if kg_ids is not None:
            q = q.filter(models.Kindergarten.id.in_(kg_ids))
        return q

    def _ind_kindergarten_count(self, kg_ids, start, end):
        total = self._kg_query(kg_ids).count()
        return {"kpi": self._kpi("kindergarten_count", "عدد الحضانات", total, "حضانة"),
                "rows": [{"المؤشر": "عدد الحضانات", "القيمة": total}]}

    def _ind_kindergarten_status(self, kg_ids, start, end):
        q = self.db.query(models.Kindergarten.status, func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status != models.KindergartenStatus.DELETED)
        if kg_ids is not None:
            q = q.filter(models.Kindergarten.id.in_(kg_ids))
        rows = q.group_by(models.Kindergarten.status).all()
        series = [{"label": _enum_value(s), "value": _safe_int(c)} for s, c in rows]
        active = next((s["value"] for s in series if s["label"] == "ACTIVE"), 0)
        return {
            "kpi": self._kpi("kindergarten_status", "الحضانات النشطة", active, "حضانة"),
            "chart": {"type": "pie", "title_ar": "حالة الحضانات", "series": series},
            "rows": [{"المؤشر": "حالة الحضانة", "الفئة": s["label"], "القيمة": s["value"]} for s in series],
        }

    def _ind_occupancy_rate(self, kg_ids, start, end):
        cap_q = self.db.query(func.coalesce(func.sum(models.Class.capacity_total), 0)).filter(
            models.Class.is_active.is_(True), models.Class.deleted_at.is_(None))
        enr_q = self.db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
        if kg_ids is not None:
            cap_q = cap_q.filter(models.Class.kindergarten_id.in_(kg_ids))
            enr_q = enr_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        capacity = _safe_int(cap_q.scalar())
        enrolled = _safe_int(enr_q.scalar())
        # Missing/zero capacity must read as "unavailable" (None), never a
        # misleading 0% that looks like a real, empty nursery network.
        pct = _safe_pct(enrolled, capacity) if capacity else None
        note = None
        if capacity == 0:
            note = "لا توجد سعة صفية مسجّلة ضمن النطاق لاحتساب نسبة الإشغال."
        return {
            "kpi": self._kpi("occupancy_rate", "نسبة الإشغال", pct, "%"),
            "rows": [{"المؤشر": "نسبة الإشغال", "المسجلون": enrolled, "السعة": capacity, "النسبة %": (pct if pct is not None else "—")}],
            "note": note,
        }

    # -- attendance ----------------------------------------------------
    # -- expected child-days (aggregate; mirrors kpi_service semantics) -----
    # These compute production-grade denominators across a set of nurseries in a
    # few batched queries rather than "all existing rows". Working days respect
    # the Jordan school week (Sun–Thu) plus explicit OperatingCalendar overrides,
    # exactly as KPIService._list_working_days does; enrolment date ranges are
    # honoured via overlap. Attendance is PRESENT+LATE physical child-days.
    def _resolve_kg_ids(self, kg_ids: list[int] | None) -> list[int]:
        if kg_ids is not None:
            return kg_ids
        return [r[0] for r in self.db.query(models.Kindergarten.id).filter(
            models.Kindergarten.status != models.KindergartenStatus.DELETED).all()]

    def _working_days_by_kg(self, kg_ids: list[int], start: date, end: date) -> dict[int, set]:
        if start > end or not kg_ids:
            return {kid: set() for kid in kg_ids}
        overrides: dict[int, dict] = defaultdict(dict)
        for kid, d, is_open in self.db.query(
            models.OperatingCalendar.kindergarten_id,
            models.OperatingCalendar.date,
            models.OperatingCalendar.is_open,
        ).filter(
            models.OperatingCalendar.kindergarten_id.in_(kg_ids),
            models.OperatingCalendar.date >= start,
            models.OperatingCalendar.date <= end,
        ).all():
            overrides[kid][d] = bool(is_open)
        # Default working days (Sun–Thu) are shared; only nurseries with explicit
        # calendar rows diverge from the default.
        all_days = []
        cursor = start
        while cursor <= end:
            all_days.append(cursor)
            cursor += timedelta(days=1)
        default_days = frozenset(d for d in all_days if d.weekday() not in (4, 5))
        result: dict[int, set] = {}
        for kid in kg_ids:
            kg_overrides = overrides.get(kid)
            if not kg_overrides:
                result[kid] = default_days
                continue
            days = set(default_days)
            for d, is_open in kg_overrides.items():
                if is_open:
                    days.add(d)
                else:
                    days.discard(d)
            result[kid] = days
        return result

    def _expected_child_days(self, kg_ids: list[int] | None, start: date, end: date) -> tuple[int, dict[int, int]]:
        """Return (total_expected_child_days, expected_days_per_child) across the scope."""
        resolved = self._resolve_kg_ids(kg_ids)
        cache_key = (tuple(sorted(resolved)), start, end)
        if cache_key in self._expected_cache:
            return self._expected_cache[cache_key]
        if not resolved:
            self._expected_cache[cache_key] = (0, {})
            return 0, {}
        working = self._working_days_by_kg(resolved, start, end)
        rows = self.db.query(
            models.EnrollmentApplication.child_id,
            models.EnrollmentApplication.kindergarten_id,
            models.EnrollmentApplication.enrollment_start_date,
            models.EnrollmentApplication.enrollment_end_date,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(resolved),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= start),
            or_(models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= end),
        ).all()
        expected_by_child: dict[int, int] = defaultdict(int)
        total = 0
        for child_id, kid, e_start, e_end in rows:
            days = working.get(kid)
            if not days:
                continue
            eff_start = max(start, e_start or start)
            eff_end = min(end, e_end or end)
            if eff_start > eff_end:
                continue
            cnt = sum(1 for d in days if eff_start <= d <= eff_end)
            if cnt:
                expected_by_child[int(child_id)] += cnt
                total += cnt
        out = (total, dict(expected_by_child))
        self._expected_cache[cache_key] = out
        return out

    def _attended_child_days(self, child_ids: list[int], start: date, end: date) -> int:
        if not child_ids:
            return 0
        return _safe_int(self.db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date >= start,
            models.AttendanceLog.date <= end,
            models.AttendanceLog.status.in_([models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE]),
        ).scalar())

    # -- attendance ----------------------------------------------------
    def _ind_attendance_rate(self, kg_ids, start, end):
        expected, expected_by_child = self._expected_child_days(kg_ids, start, end)
        attended = self._attended_child_days(list(expected_by_child.keys()), start, end)
        # Denominator is expected child-days on working days, not "all rows".
        pct = _safe_pct(attended, expected) if expected else None
        return {
            "kpi": self._kpi("attendance_rate", "نسبة الحضور", pct, "%"),
            "rows": [{"المؤشر": "نسبة الحضور", "أيام الحضور المتوقعة": expected, "أيام حضور فعلية": attended, "النسبة %": (pct if pct is not None else "—")}],
            "note": ("لا توجد أيام حضور متوقعة ضمن النطاق (لا يوجد تسجيل نشط أو أيام دوام)." if not expected else None),
        }

    def _ind_absence_requests(self, kg_ids, start, end):
        # Count absence requests that OVERLAP the period (start <= period_end and
        # end >= period_start), not only those whose start falls inside it — an
        # absence spanning into the period must still be counted.
        q = self.db.query(func.count(models.AbsenceRequest.id)).filter(
            models.AbsenceRequest.start_date <= end, models.AbsenceRequest.end_date >= start)
        if kg_ids is not None:
            q = q.filter(models.AbsenceRequest.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {"kpi": self._kpi("absence_requests", "طلبات الغياب", total, "طلب"),
                "rows": [{"المؤشر": "طلبات الغياب", "القيمة": total}]}

    # -- daily reports -------------------------------------------------
    def _ind_daily_report_completion(self, kg_ids, start, end):
        # Denominator is expected child-days (eligible active-enrolment days on
        # working days), NOT the count of existing report rows — missing reports
        # must lower completion rather than disappear from the denominator.
        expected, expected_by_child = self._expected_child_days(kg_ids, start, end)
        child_ids = list(expected_by_child.keys())
        completed = 0
        if child_ids:
            completed = _safe_int(self.db.query(func.count(models.DailyReport.id)).filter(
                models.DailyReport.child_id.in_(child_ids),
                models.DailyReport.date >= start, models.DailyReport.date <= end,
                models.DailyReport.status.in_([
                    models.DailyReportStatus.APPROVED,
                    models.DailyReportStatus.SENT_TO_PARENT,
                ]),
            ).scalar())
        pct = _safe_pct(completed, expected) if expected else None
        return {
            "kpi": self._kpi("daily_report_completion", "معدل إنجاز التقارير اليومية", pct, "%"),
            "rows": [{"المؤشر": "إنجاز التقارير اليومية", "التقارير المتوقعة": expected, "المكتملة": completed, "النسبة %": (pct if pct is not None else "—")}],
            "note": ("لا توجد تقارير متوقعة ضمن النطاق (لا يوجد تسجيل نشط أو أيام دوام)." if not expected else None),
        }

    def _ind_late_reports(self, kg_ids, start, end):
        q = self.db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= start, models.DailyReport.date <= end,
            models.DailyReport.submitted_at.isnot(None),
            func.date(models.DailyReport.submitted_at) > models.DailyReport.date)
        if kg_ids is not None:
            q = q.filter(models.DailyReport.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {"kpi": self._kpi("late_reports", "التقارير المتأخرة", total, "تقرير"),
                "rows": [{"المؤشر": "التقارير المتأخرة", "القيمة": total}]}

    # -- safety / incidents -------------------------------------------
    def _ind_critical_incidents(self, kg_ids, start, end):
        q = self.db.query(func.count(models.Incident.id)).filter(
            models.Incident.deleted_at.is_(None) if hasattr(models.Incident, "deleted_at") else True,
            func.date(models.Incident.occurred_at) >= start, func.date(models.Incident.occurred_at) <= end,
            models.Incident.severity_level == models.SeverityLevel.CRITICAL)
        if kg_ids is not None:
            q = q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {"kpi": self._kpi("critical_incidents", "الحوادث الحرجة", total, "حادثة"),
                "rows": [{"المؤشر": "الحوادث الحرجة", "القيمة": total}]}

    def _ind_incidents_by_severity(self, kg_ids, start, end):
        q = self.db.query(models.Incident.severity_level, func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= start, func.date(models.Incident.occurred_at) <= end)
        if kg_ids is not None:
            q = q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        rows = q.group_by(models.Incident.severity_level).all()
        series = [{"label": _enum_value(s), "value": _safe_int(c)} for s, c in rows]
        total = sum(s["value"] for s in series)
        # Exposure-adjusted incident rate per 1,000 attended child-days — the
        # comparable measure. Unavailable (not 0) when there is no attendance.
        _, expected_by_child = self._expected_child_days(kg_ids, start, end)
        attended = self._attended_child_days(list(expected_by_child.keys()), start, end)
        rate = round(total / attended * 1000, 3) if attended else None
        table = [{"المؤشر": "الحوادث حسب الخطورة", "الفئة": s["label"], "القيمة": s["value"]} for s in series]
        table.append({
            "المؤشر": "معدل الحوادث لكل 1000 يوم حضور",
            "أيام الحضور": attended,
            "المعدل": (rate if rate is not None else "—"),
        })
        return {
            "kpi": self._kpi("incidents_by_severity", "إجمالي الحوادث", total, "حادثة"),
            "chart": {"type": "bar", "title_ar": "الحوادث حسب الخطورة", "series": series},
            "rows": table,
            "note": ("لا توجد أيام حضور لاحتساب معدل الحوادث لكل 1000 يوم." if not attended else
                     f"معدل الحوادث: {rate} لكل 1000 يوم حضور."),
        }

    # -- staff / governance -------------------------------------------
    def _ind_staff_count(self, kg_ids, start, end):
        q = self.db.query(models.User.role, func.count(models.User.id)).filter(
            models.User.deleted_at.is_(None),
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]))
        if kg_ids is not None:
            q = q.filter(models.User.kindergarten_id.in_(kg_ids))
        rows = dict((_enum_value(r), _safe_int(c)) for r, c in q.group_by(models.User.role).all())
        managers = rows.get("MANAGER", 0)
        supervisors = rows.get("SUPERVISOR", 0)
        return {
            "kpi": self._kpi("staff_count", "عدد الموظفين", managers + supervisors, "موظف"),
            "rows": [{"المؤشر": "عدد الموظفين", "المدراء": managers, "المشرفون": supervisors, "الإجمالي": managers + supervisors}],
        }

    def _ind_unassigned_classes(self, kg_ids, start, end):
        assigned = self.db.query(models.SupervisorAssignment.class_id).filter(
            models.SupervisorAssignment.deleted_at.is_(None))
        q = self.db.query(func.count(models.Class.id)).filter(
            models.Class.is_active.is_(True), models.Class.deleted_at.is_(None),
            ~models.Class.id.in_(assigned))
        if kg_ids is not None:
            q = q.filter(models.Class.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {"kpi": self._kpi("unassigned_classes", "الفصول غير المسندة لمشرف", total, "صف"),
                "rows": [{"المؤشر": "الفصول غير المسندة لمشرف", "القيمة": total}]}

    def _ind_unassigned_children(self, kg_ids, start, end):
        q = self.db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.class_id.is_(None))
        if kg_ids is not None:
            q = q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {"kpi": self._kpi("unassigned_children", "الأطفال غير المسجلين في صف", total, "طفل"),
                "rows": [{"المؤشر": "الأطفال غير المسجلين في صف", "القيمة": total}]}

    def _ind_data_quality_score(self, kg_ids, start, end):
        # Reporting participation: share of active nurseries with >=1 daily report
        # in the 7-day window ENDING on the report end date. The window is exactly
        # seven inclusive calendar dates (end-6 .. end), anchored to the selected
        # period end rather than "now".
        window_end = end
        window_start = end - timedelta(days=6)
        kg_q = self.db.query(models.Kindergarten.id).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        if kg_ids is not None:
            kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_ids))
        active_ids = [r[0] for r in kg_q.all()]
        total = len(active_ids)
        reported = 0
        if active_ids:
            reported = self.db.query(func.count(func.distinct(models.DailyReport.kindergarten_id))).filter(
                models.DailyReport.kindergarten_id.in_(active_ids),
                models.DailyReport.date >= window_start, models.DailyReport.date <= window_end).scalar() or 0
        # No active nurseries in scope -> participation is unavailable, not 0%.
        pct = _safe_pct(reported, total) if total else None
        return {
            "kpi": self._kpi("data_quality_score", "مؤشر جودة البيانات", pct, "%"),
            "rows": [{"المؤشر": f"المشاركة في الإبلاغ ({window_start} → {window_end})", "النشطة": total, "المُبلِّغة": reported, "النسبة %": (pct if pct is not None else "—")}],
            "note": ("لا توجد حضانات نشطة ضمن النطاق لاحتساب المشاركة في الإبلاغ." if total == 0 else None),
        }

    def _ind_service_access_ratio(self, kg_ids, start, end):
        children = self._child_base_query(kg_ids).count()
        kg_q = self.db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        if kg_ids is not None:
            kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_ids))
        active_kgs = _safe_int(kg_q.scalar())
        ratio = round(children / active_kgs, 2) if active_kgs else 0.0
        return {
            "kpi": self._kpi("service_access_ratio", "أطفال لكل حضانة نشطة", ratio, "طفل/حضانة"),
            "rows": [{"المؤشر": "أطفال لكل حضانة نشطة", "الأطفال": children, "الحضانات النشطة": active_kgs, "النسبة": ratio}],
            "note": ("لا توجد حضانات نشطة ضمن النطاق." if active_kgs == 0 else None),
        }

    SUPPRESSION_MARKER = "محجوب"

    def _apply_small_cell_suppression(self, charts: list, table: list) -> int:
        """Suppress identifying small category counts (statistical disclosure
        control). Counts in (0, threshold) are blanked: chart points become a gap
        (None, never 0) and table breakdown cells show "محجوب". Returns the number
        of suppressed table cells. Headline KPI totals/rates are not suppressed;
        complementary suppression is a documented follow-up."""
        threshold = _min_cell_size()
        if threshold <= 1:
            return 0

        def _small(v: Any) -> bool:
            return isinstance(v, int) and not isinstance(v, bool) and 0 < v < threshold

        for chart in charts:
            for point in chart.get("series", []):
                if _small(point.get("value")):
                    point["value"] = None
                    point["suppressed"] = True

        suppressed = 0
        for row in table:
            if "الفئة" in row and _small(row.get("القيمة")):
                row["القيمة"] = self.SUPPRESSION_MARKER
                suppressed += 1
        return suppressed

    def _custom_summary_ar(self, scope: dict[str, Any], kpis: list[dict[str, Any]], status: str) -> str:
        parts = [f"تقرير مخصص للجهة: {scope['agency_name_ar']}، على مستوى {scope['level_name_ar']}"]
        if scope.get("governorate"):
            parts.append(f"محافظة {scope['governorate']}")
        if scope.get("city"):
            parts.append(f"لواء/مدينة {scope['city']}")
        parts.append(f"للفترة من {scope['start_date']} إلى {scope['end_date']}")
        head = "، ".join(parts) + "."
        if not kpis:
            return head + " لا توجد مؤشرات محسوبة ضمن هذا النطاق."
        def _fmt(k: dict[str, Any]) -> str:
            if k.get("value") is None:
                return f"{k['label_ar']}: غير متاح"
            return f"{k['label_ar']}: {k['value']}{(' ' + k['unit_ar']) if k.get('unit_ar') else ''}"
        highlights = "؛ ".join(_fmt(k) for k in kpis[:6])
        status_ar = {"sufficient": "البيانات كافية", "limited": "البيانات محدودة", "incomplete": "البيانات غير مكتملة"}.get(status, status)
        return f"{head} أبرز المؤشرات: {highlights}. حالة البيانات: {status_ar}."
