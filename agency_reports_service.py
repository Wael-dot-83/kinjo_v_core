"""Dynamic, privacy-safe services for official agency reports."""

from __future__ import annotations

import calendar
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

import models
from agency_reports_registry import AGENCY_REPORT_REGISTRY, SENSITIVE_FIELD_DENYLIST
from config import settings
from services.jordan_locations import governorate_filter

_JORDAN_TZ = timezone(timedelta(hours=3))


def _age_months(dob: date, ref: date) -> int:
    """Full calendar months between dob and ref."""
    return (ref.year - dob.year) * 12 + (ref.month - dob.month) - (1 if ref.day < dob.day else 0)


def _date_plus_months(d: date, months: int) -> date:
    """Add (positive) or subtract (negative) calendar months, clamping day."""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _min_cell_size() -> int:
    """Statistical disclosure threshold: category counts below this are
    suppressed. Configurable via settings.AGENCY_REPORT_MIN_CELL_SIZE (loaded
    from .env by pydantic); safe default 5. A value <= 1 disables suppression.

    Reads settings, not os.getenv: the app never calls load_dotenv(), so os.environ
    does not contain .env values and os.getenv would always fall back to the default."""
    try:
        return max(0, int(settings.AGENCY_REPORT_MIN_CELL_SIZE))
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


_ENROLLMENT_STATUS_AR = {
    "DRAFT": "مسودة",
    "SUBMITTED": "مُقدَّم",
    "PENDING_REVIEW": "قيد المراجعة",
    "ACCEPTED": "مقبول",
    "REJECTED": "مرفوض",
    "WITHDRAWN": "منسحب",
    "WAITLISTED": "قائمة الانتظار",
    "ACTIVE": "نشط",
}


def _enrollment_status_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _ENROLLMENT_STATUS_AR.get(raw or "", raw or "غير محدد")


_KINDERGARTEN_STATUS_AR = {
    "DRAFT": "مسودة",
    "ACTIVE": "نشطة",
    "FROZEN": "مجمّدة",
    "INACTIVE": "غير نشطة",
    "DELETED": "محذوفة",
}


def _kindergarten_status_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _KINDERGARTEN_STATUS_AR.get(raw or "", raw or "غير محدد")


_SEVERITY_AR = {
    "LOW": "منخفضة",
    "MEDIUM": "متوسطة",
    "HIGH": "عالية",
    "CRITICAL": "حرجة",
}

_QUARTER_AR = {
    "Q1": "الربع الأول",
    "Q2": "الربع الثاني",
    "Q3": "الربع الثالث",
    "Q4": "الربع الرابع",
}

_SEVERITY_COLOR = {
    "LOW": "#22c55e",
    "MEDIUM": "#f59e0b",
    "HIGH": "#f97316",
    "CRITICAL": "#dc2626",
    "UNKNOWN": "#64748b",
}


def _severity_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _SEVERITY_AR.get(raw or "", raw or "غير محدد")


def _quarter_ar(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return _QUARTER_AR.get(raw, raw or "غير محدد")


_ROLE_AR = {
    "ADMIN": "مدير النظام",
    "MANAGER": "مدير حضانة",
    "SUPERVISOR": "مشرفة",
    "PARENT": "ولي أمر",
}


def _role_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _ROLE_AR.get(raw or "", raw or "غير محدد")


_TRAINING_STATUS_AR = {
    "PENDING": "قيد الانتظار",
    "COMPLETED": "مكتمل",
    "OVERDUE": "متأخر",
}


def _training_status_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _TRAINING_STATUS_AR.get(raw or "", raw or "غير محدد")


_THREAD_TYPE_AR = {
    "DIRECT": "مباشرة",
    "ANNOUNCEMENT": "إعلان",
    "CLASS": "رسائل الصف",
    "BROADCAST": "بث عام",
}


def _thread_type_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _THREAD_TYPE_AR.get(raw or "", raw or "غير محدد")


_ATTENDANCE_STATUS_AR = {
    "PRESENT": "حاضر",
    "ABSENT": "غائب",
    "LATE": "متأخر",
    "EXCUSED": "غياب بعذر",
}


def _attendance_status_ar(value: Any) -> str:
    raw = _enum_value(value)
    return _ATTENDANCE_STATUS_AR.get(raw or "", raw or "غير محدد")


def _coerce_enum(enum_cls: type, value: Any):
    """Case-insensitively coerce a filter string to an enum member, or None when
    the value is empty or invalid. Guards report queries so a malformed filter
    value (e.g. lowercase "male") is ignored rather than raising ValueError and
    500-ing the whole report."""
    if value in (None, "", "null", "undefined"):
        return None
    try:
        return enum_cls(str(value).upper())
    except ValueError:
        return None


_DOS_PERIOD_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "half_year": 180,
    "year": 365,
}


def _resolve_dos_period(filters: dict[str, Any]) -> tuple[date, date]:
    """Resolve the ``period``/``date_from``/``date_to`` filter pair to an
    inclusive (start_date, end_date) range. Falls back to the last 30 days
    when no usable period is supplied so time-series reports never return
    the entire history silently."""
    today = datetime.now(_JORDAN_TZ).date()
    raw_period = filters.get("period")
    raw_start = filters.get("date_from")
    raw_end = filters.get("date_to")
    if raw_period == "custom" and raw_start and raw_end:
        try:
            return date.fromisoformat(str(raw_start)), date.fromisoformat(str(raw_end))
        except (TypeError, ValueError):
            pass
    if raw_period and raw_period != "custom" and _DOS_PERIOD_DAYS.get(raw_period):
        days = _DOS_PERIOD_DAYS[raw_period]
        return today - timedelta(days=days), today
    if raw_start and raw_end:
        try:
            return date.fromisoformat(str(raw_start)), date.fromisoformat(str(raw_end))
        except (TypeError, ValueError):
            pass
    return today - timedelta(days=30), today


_SOURCE_AR = {
    "Child": "سجل الأطفال",
    "ParentProfile": "ملفات أولياء الأمور",
    "EnrollmentApplication": "سجلات التسجيل",
    "Kindergarten": "سجل الحضانات",
    "Class": "سجل الصفوف",
    "Incident": "سجل الحوادث والسلامة",
    "AttendanceLog": "سجل الحضور والغياب",
    "DailyReport": "التقارير اليومية",
    "User": "سجل الكوادر (المستخدمين)",
    "AbsenceRequest": "طلبات الغياب",
    "StaffTrainingCompletion": "سجل إتمام التدريب",
    "Message": "سجل المراسلات",
    "NationalImmunizationSchedule": "الجدول الوطني للمطاعيم",
    "ChildVaccinationRecord": "سجل مطاعيم الطفل",
    "AbsenceReasonCategory": "تصنيف أسباب الغياب",
    "OperatingCalendar": "التقويم التشغيلي",
    "SupervisorAssignment": "سجل إسناد الإشراف",
    "StaffTraining": "برامج التدريب",
}

_GEO_BASIS_AR = {
    "parent_residence": "حسب سكن ولي الأمر",
    "kindergarten_location": "حسب موقع الحضانة",
}

# Factual methodology definitions, written to match what each report actually
# computes (not the broad title) so figures are interpreted without assumptions.
_REPORT_DEFINITIONS = {
    "children_demographics": "توزيع الأطفال المسجّلين حسب المحافظة واللواء والجنس، اعتمادًا على سكن ولي الأمر.",
    "enrollment_participation_0_60": "أعداد الأطفال (0–60 شهرًا) ذوي التسجيل النشط، موزّعين حسب الموقع والفئة العمرية (بخطوات 12 شهرًا).",
    "institutions_active_licensed": "عدد مؤسسات الطفولة المبكرة حسب حالتها التشغيلية والموقع الجغرافي.",
    "capacity_occupancy_overcrowding": "الطاقة الاستيعابية الصفّية مقابل عدد المسجّلين النشطين ونسبة الإشغال، لكل موقع.",
    "monthly_attendance_absence": "توزيع سجلات الحضور والغياب حسب الحالة (حاضر/غائب/متأخر/غياب بعذر) والموقع.",
    "supervisors_child_ratio": "عدد المشرفات مقابل الأطفال المسجّلين ومعدّل الأطفال لكل مشرفة، لكل موقع.",
    "incidents_safety_1000_child_days": "حوادث السلامة المسجّلة حسب درجة الخطورة والموقع، مع معدّل الحوادث لكل 1000 يوم حضور طفل.",
    "geographic_service_gaps": "توزيع الأطفال مقابل الحضانات النشطة ومعدّل الأطفال لكل حضانة، لإبراز الفجوات الجغرافية في الخدمة.",
    "data_quality_completeness": "مؤشر اكتمال البيانات: عدد الأطفال بدون تاريخ ميلاد مسجّل، موزّعين حسب الموقع.",
    "annual_quarterly_trends": "عدد الحضانات النشطة موزّعة حسب سنة الإنشاء، لإبراز الاتجاه الزمني.",
    "kindergarten_registry": "الحضانات المسجّلة حسب حالتها التشغيلية والموقع الجغرافي.",
    "child_safety_protection": "حوادث السلامة وحماية الطفل المسجّلة حسب درجة الخطورة والموقع الجغرافي.",
    "workforce_summary": "عدد الكوادر (المدراء والمشرفات) العاملين في الحضانات حسب الدور والموقع الجغرافي.",
    "training_compliance": "عدد سجلات التدريب المكتملة مقابل إجمالي السجلات ونسبة الإكمال.",
    "family_communication_counts": "عدد الرسائل موزّعة حسب نوع المحادثة.",
}


def _sources_ar(models_list: list[str]) -> str:
    """Human-readable Arabic data-source attribution from the registry model names."""
    names = [_SOURCE_AR.get(m, m) for m in (models_list or [])]
    return "، ".join(dict.fromkeys(names)) if names else "منصة KinJo"


def _is_rate_key(key: Any) -> bool:
    """A column that is a rate/ratio/percentage — which must never be summed in a
    totals row (you total counts, not rates: standard statistical practice)."""
    kl = str(key).lower()
    ks = str(key)
    return (
        "rate" in kl
        or "ratio" in kl
        or "pct" in kl
        or "percent" in kl
        or "per_" in kl
        or "_per_" in kl
        or "نسبة" in ks
        or "معدل" in ks
        or "لكل" in ks
    )


_GEO_KEYS = {"governorate", "city", "district", "year"}


def _build_chart(breakdowns: list[dict[str, Any]], value_col: str | None, title: str | None) -> dict[str, Any] | None:
    """Build a meaningful, aggregated chart from a multi-dimensional breakdown.

    The raw breakdown has one row per (governorate, city, category), so plotting it
    directly produces duplicate/garbled labels (البلقاء twice, إربد×roles). Instead,
    aggregate the value by the single most informative dimension:
    - a category column (status/severity/role/gender/…) when it has ≥2 distinct
      values → a true distribution (e.g. staff by role, incidents by severity);
    - otherwise the governorate → a geographic distribution.
    Bars are sorted by value (largest first) and capped so the chart stays readable.
    """
    if not breakdowns or not value_col:
        return None
    keys = list(breakdowns[0].keys())

    def _num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # A categorical dimension: a text column that is not geography/share/rate.
    cat_col = None
    for k in keys:
        if k in _GEO_KEYS or k == "النسبة %" or _is_rate_key(k):
            continue
        vals = [b.get(k) for b in breakdowns]
        if any(isinstance(v, str) for v in vals) and not any(_num(v) for v in vals):
            cat_col = k
            break

    if cat_col and len({b.get(cat_col) for b in breakdowns}) >= 2:
        group_col = cat_col
    elif "governorate" in keys:
        group_col = "governorate"
    else:
        group_col = keys[0]

    agg: dict[str, float] = {}
    for b in breakdowns:
        g = str(b.get(group_col, "") or "غير محدد")
        v = b.get(value_col, 0)
        agg[g] = agg.get(g, 0) + (v if _num(v) else 0)
    series = [{"label": g, "value": v} for g, v in agg.items()]
    series.sort(key=lambda s: s["value"], reverse=True)
    return {"type": "bar", "title_ar": title, "series": series[:15], "group_by": group_col}


def _finalize_breakdowns(breakdowns: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    """Professionalize a breakdown table in place: add a share-of-total column to
    count breakdowns and build a totals row (المجموع). Returns
    (value_col_for_chart, total_row).

    - Counts are summed; rate/ratio columns show '—' in the total (never summed).
    - Share (النسبة %) is added only when a plain 'count' column exists.
    - The chart value column is 'count' when present (robust to the added share
      column), else the last column (prior behaviour) — so charts do not change.
    """
    if not breakdowns:
        return None, None
    keys = list(breakdowns[0].keys())

    def _num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    numeric = {k for k in keys if any(_num(b.get(k)) for b in breakdowns)}

    if "count" in keys:
        total = sum(_safe_int(b.get("count")) for b in breakdowns)
        for b in breakdowns:
            b["النسبة %"] = round(_safe_int(b.get("count")) / total * 100, 1) if total else 0.0
        value_col = "count"
    else:
        # A summable value for the chart: last numeric column that is not a rate
        # (rates can't be aggregated across rows), else the last column.
        non_rate_numeric = [k for k in keys if k in numeric and not _is_rate_key(k)]
        value_col = non_rate_numeric[-1] if non_rate_numeric else (keys[-1] if keys else None)

    label_col = keys[0]
    total_row: dict[str, Any] = {}
    for k in breakdowns[0].keys():  # includes the just-added share column
        if k == label_col:
            total_row[k] = "المجموع"
        elif k == "النسبة %":
            total_row[k] = 100.0
        elif _is_rate_key(k):
            total_row[k] = "—"
        elif k in numeric:
            total_row[k] = sum(_safe_int(b.get(k)) for b in breakdowns)
        else:
            total_row[k] = ""
    return value_col, total_row


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
    "eligible_child_days": "أيام الأطفال المؤهلة",
    "incident_rate_per_1000_child_days": "معدل الحوادث لكل 1000 يوم طفل",
    "areas": "عدد المناطق",
    "children": "الأطفال",
    "enrolled_children": "الأطفال المسجلون",
    "total_institutions": "إجمالي المؤسسات",
    "active_institutions": "المؤسسات النشطة",
    "licensed_institutions": "المؤسسات المرخّصة (سارية)",
    "active_and_licensed": "نشطة ومرخّصة",
    "expired_licenses": "تراخيص منتهية",
    "missing_license_data": "بدون بيانات ترخيص",
    "total_capacity": "الطاقة الاستيعابية",
    "total_enrolled": "العدد الفعلي للمسجلين",
    "occupancy_rate_pct": "نسبة الإشغال %",
    "occupancy_rate": "نسبة الإشغال %",
    "overcrowded_kindergartens": "الحضانات المكتظة",
    "overcrowding_rate_pct": "نسبة الاكتظاظ %",
    "total_records": "إجمالي السجلات",
    "present_records": "سجلات الحضور",
    "absent_records": "سجلات الغياب",
    "attendance_rate_pct": "نسبة الحضور %",
    "absence_rate_pct": "نسبة الغياب %",
    "total_supervisors": "إجمالي المشرفين",
    "children_missing_dob": "أطفال بدون تاريخ ميلاد",
    "data_quality_note_ar": "ملاحظة جودة البيانات",
    "trend_years": "سنوات القياس",
    "period_start": "بداية الفترة",
    "period_end": "نهاية الفترة",
    "total_kindergartens": "إجمالي الحضانات",
    "total_enrolled_children": "إجمالي الأطفال المسجلين",
    "period": "الفترة",
    "quarter": "الربع",
    "enrolled_children": "الأطفال المسجلون",
    # table columns
    "النسبة %": "النسبة %",
    "governorate": "المحافظة",
    "city": "المدينة/اللواء",
    "district": "اللواء",
    "area": "المنطقة/الحي",
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
    "national_ratio": "المعدل الوطني للأطفال لكل حضانة",
    "unserved_districts_count": "عدد الألوية المحرومة",
    "unserved_children_count": "الأطفال غير المخدومين في المناطق المحرومة",
    "is_unserved_zone": "منطقة محرومة",
    "status_ar": "حالة الخدمة",
    "available_expansion_capacity": "سعة التوسع المتاحة",
    "is_overcrowded": "حالة الاكتظاظ",
    "investment_priority_score": "مؤشر أولوية الاستثمار التنموي",
    "priority_level_ar": "درجة الأولوية",
    "priority_rank": "الترتيب التنموي",
    "governorates_count": "عدد المحافظات المشمولة",
    "top_priority_governorate": "المحافظة الأعلى أولوية",
    "average_investment_priority_score": "متوسط درجة الأولوية الوطني",
    "active_kindergartens": "الحضانات النشطة",
    "available_expansion_capacity": "سعة التوسع المتاحة",
    # vaccination_due_children
    "vaccine": "المطعوم",
    "due_age": "العمر المستحق",
    "vaccines_in_schedule": "عدد المطاعيم في الجدول",
    "children_considered": "الأطفال المشمولون",
    "vaccine_doses_due": "إجمالي الجرعات المستحقة",
    # kg2_eligibility
    "ineligible_children": "الأطفال غير المؤهلين",
    "unevaluatable_records": "سجلات تعذر تقييمها",
    "eligibility_rate": "نسبة المؤهلين %",
    "data_completeness_rate": "نسبة اكتمال البيانات %",
    "highest_governorate": "أعلى محافظة",
    "total_evaluated": "إجمالي السجلات المشمولة",
    "last_eligible_birth_date": "آخر تاريخ ميلاد مؤهل",
    "required_age": "العمر المطلوب",
}


def _label_map(keys) -> dict[str, str]:
    return {k: _FIELD_LABELS.get(k, k) for k in keys}


from utils.time_utils import jordan_date_range_filter

from utils.time_utils import jordan_date_range_filter

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
        generated_at = _now_iso()
        agencies = []
        for code, agency in AGENCY_REPORT_REGISTRY.items():
            reports = []
            for report_code, report in agency["reports"].items():
                reports.append(
                    {
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
                        "data_sources_ar": [_SOURCE_AR.get(s, s) for s in report.get("data_sources", [])],
                        "reason_ar": report.get("reason_ar"),
                        "generated_at": generated_at,
                    }
                )
            agencies.append(
                {
                    "code": code,
                    "name_ar": agency["name_ar"],
                    "name_en": agency.get("name_en"),
                    "description_ar": agency.get("description_ar"),
                    "icon": agency.get("icon", "bi-bank"),
                    "report_count": len(reports),
                    "ready_report_count": sum(1 for r in reports if r["status"] == "ready"),
                    "requires_data_count": sum(1 for r in reports if r["status"] != "ready"),
                    "reports": reports,
                    "generated_at": generated_at,
                }
            )
        return {"generated_at": generated_at, "agencies": agencies}

    def summary(self) -> dict[str, Any]:
        catalog_data = self.catalog()
        catalog = catalog_data["agencies"]
        total_reports = sum(a["report_count"] for a in catalog)
        ready_reports = sum(a["ready_report_count"] for a in catalog)
        requires_data = sum(a["requires_data_count"] for a in catalog)
        return {
            "generated_at": catalog_data["generated_at"],
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
        catalog = self.catalog()
        agency = self._agency(agency_code)
        agency_entry = next((a for a in catalog["agencies"] if a["code"] == agency_code), None)
        reports = []
        if agency_entry:
            for report in agency_entry["reports"]:
                report_copy = dict(report)
                report_copy.setdefault("generated_at", catalog.get("generated_at"))
                reports.append(report_copy)
        return {
            "agency_code": agency_code,
            "agency_name_ar": agency["name_ar"],
            "agency_name_en": agency.get("name_en"),
            "description_ar": agency.get("description_ar"),
            "generated_at": catalog.get("generated_at"),
            "reports": reports,
        }

    def generate_report(
        self, agency_code: str, report_code: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
                agency_code,
                agency,
                report_code,
                report,
                filters,
            )
            payload["summary"]["message_ar"] = (
                "لم يتم رفع جدول المطاعيم الوطني بعد. حمّل قالب Excel، عبّئ المطاعيم "
                "والأعمار المستحقة، ثم ارفعه لتوليد التقرير."
            )
            payload["unavailable_indicators"] = [
                {
                    "code": report_code,
                    "status": "awaiting_schedule_upload",
                    "message_ar": payload["summary"]["message_ar"],
                }
            ]
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
                payload = self._unavailable_payload(
                    agency_code, agency, report_code, report, filters, status="not_available"
                )
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
        elif agency_code == "mopic" and report_code == "regional_capacity_readiness":
            payload = self._mopic_capacity_readiness(agency_code, agency, report_code, report, filters)
        elif agency_code == "mopic" and report_code == "development_investment_priorities":
            payload = self._mopic_investment_priorities(agency_code, agency, report_code, report, filters)
        else:
            payload = self._unavailable_payload(
                agency_code, agency, report_code, report, filters, status="not_available"
            )

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

    def _metadata(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        status: str = "ready",
    ) -> dict[str, Any]:
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
            "geography_basis": filters.get("geography_basis")
            or report.get("default_geography_basis", "parent_residence"),
            "privacy_level": report.get("privacy_level", "aggregated_only"),
            "data_quality_status": "sufficient" if status == "ready" else status,
            "data_sources": report.get("data_sources", []),
            # Human-readable provenance (standardized official-statistics practice):
            # source, geography basis, definition, units, and a missing-data legend,
            # so a reader can trust and interpret the figures without assumptions.
            "data_source_ar": _sources_ar(report.get("data_sources", [])),
            "geography_basis_ar": _GEO_BASIS_AR.get(
                filters.get("geography_basis") or report.get("default_geography_basis", ""), ""
            ),
            "definition_ar": report.get("description_ar") or _REPORT_DEFINITIONS.get(report_code),
            "units_note_ar": "الأعداد بالأرقام المطلقة، والنسب بالنسبة المئوية (%).",
            "symbols_note_ar": "«—» تعني غير متوفر أو لا ينطبق · «0» تعني لا يوجد (صفر فعلي).",
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

    def _unavailable_payload(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        status: str | None = None,
    ) -> dict[str, Any]:
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
            gov_values = self._governorate_filter_values(filters["governorate"])
            q = q.filter(models.ParentProfile.home_governorate.in_(gov_values))
        if filters.get("city"):
            q = q.filter(models.ParentProfile.home_district == filters["city"])
        return q

    def _apply_kindergarten_geo_filters(self, q, filters: dict[str, Any]):
        if filters.get("governorate"):
            gov_values = self._governorate_filter_values(filters["governorate"])
            q = q.filter(models.Kindergarten.governorate.in_(gov_values))
        if filters.get("city"):
            q = q.filter(models.Kindergarten.district == filters["city"])
        if filters.get("kindergarten_id"):
            q = q.filter(models.Kindergarten.id == int(filters["kindergarten_id"]))
        return q

    def _governorate_filter_values(self, value: Any) -> list[str]:
        """Return canonical + alias variants for robust geo filtering.

        This keeps chart/table drill-down stable even when display labels use one
        governorate form (e.g., "العاصمة") while stored records use another
        alias (e.g., "عمان").
        """
        if not isinstance(value, str) or not value.strip():
            return [str(value)] if value is not None else []

        gov = value.strip()
        aliases = settings.JORDAN_GOVERNORATE_ALIASES
        variants: set[str] = {gov}

        mapped = aliases.get(gov) or aliases.get(gov.lower())
        if isinstance(mapped, str) and mapped.strip():
            variants.add(mapped.strip())

        gov_l = gov.lower()
        for alias_key, canonical in aliases.items():
            if not isinstance(alias_key, str) or not isinstance(canonical, str):
                continue
            if canonical.strip().lower() == gov_l:
                variants.add(alias_key.strip())

        return [v for v in variants if v]

    def _kg2_eligibility(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        admission_year = int(filters.get("admission_year") or datetime.now(_JORDAN_TZ).year)
        required_age = settings.MOE_KG2_REQUIRED_AGE
        cutoff_month = settings.MOE_KG2_CUTOFF_MONTH
        cutoff_day = settings.MOE_KG2_CUTOFF_DAY

        cutoff_date = date(admission_year, cutoff_month, cutoff_day)
        latest_eligible_birth_date = date(admission_year - required_age, cutoff_month, cutoff_day)

        aliases = settings.JORDAN_GOVERNORATE_ALIASES
        def _normalize_gov(name: Any) -> str:
            if not name:
                return "غير محدد"
            s = str(name).strip()
            return aliases.get(s) or aliases.get(s.lower(), s)

        q = (
            self.db.query(
                models.Child.id,
                models.Child.date_of_birth,
                models.Child.gender,
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.ParentProfile.home_area,
            )
            .outerjoin(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        _gender = _coerce_enum(models.Gender, filters.get("gender"))
        if _gender is not None:
            q = q.filter(models.Child.gender == _gender)

        children = q.all()

        eligible_count = 0
        ineligible_count = 0
        unevaluatable_count = 0

        city_filter = filters.get("city")
        gov_filter = filters.get("governorate")
        if city_filter:
            group_dim = "area"
        elif gov_filter:
            group_dim = "district"
        else:
            group_dim = "governorate"

        breakdown_data = {}

        for c in children:
            is_eligible = False
            is_ineligible = False
            is_unevaluatable = False

            if c.date_of_birth is None or not c.home_governorate:
                is_unevaluatable = True
                unevaluatable_count += 1
            elif c.date_of_birth <= latest_eligible_birth_date:
                is_eligible = True
                eligible_count += 1
            else:
                is_ineligible = True
                ineligible_count += 1

            if group_dim == "area":
                key = c.home_area or "غير محدد"
            elif group_dim == "district":
                key = c.home_district or "غير محدد"
            else:
                key = _normalize_gov(c.home_governorate)

            if key not in breakdown_data:
                breakdown_data[key] = {
                    "eligible": 0,
                    "ineligible": 0,
                    "unevaluatable": 0,
                    "male": 0,
                    "female": 0,
                    "unspecified_gender": 0,
                }

            if is_eligible:
                breakdown_data[key]["eligible"] += 1
            elif is_ineligible:
                breakdown_data[key]["ineligible"] += 1
            else:
                breakdown_data[key]["unevaluatable"] += 1

            if is_eligible:
                g_str = str(c.gender).lower() if c.gender else ""
                if "male" in g_str:
                    breakdown_data[key]["male"] += 1
                elif "female" in g_str:
                    breakdown_data[key]["female"] += 1
                else:
                    breakdown_data[key]["unspecified_gender"] += 1

        total_evaluated = eligible_count + ineligible_count + unevaluatable_count
        eval_denominator = eligible_count + ineligible_count
        eligibility_rate = (eligible_count / eval_denominator * 100) if eval_denominator > 0 else 0.0
        completeness_rate = (eval_denominator / total_evaluated * 100) if total_evaluated > 0 else 0.0

        # Find highest governorate based on eligible children
        gov_eligible_counts = {}
        for c in children:
            if c.home_governorate and c.date_of_birth and c.date_of_birth <= latest_eligible_birth_date:
                g = _normalize_gov(c.home_governorate)
                gov_eligible_counts[g] = gov_eligible_counts.get(g, 0) + 1
        
        highest_gov = "غير محدد"
        if gov_eligible_counts:
            highest_gov = max(gov_eligible_counts, key=gov_eligible_counts.get)

        # Build dynamic Arabic interpretation text
        if total_evaluated == 0:
            interpretation_ar = "لا توجد سجلات أطفال ضمن النطاق والفلاتر المحددة، لذلك لا يمكن حساب عدد الأطفال المؤهلين."
        elif eval_denominator == 0:
            interpretation_ar = "تعذر حساب الأهلية بسبب نقص أو عدم صلاحية البيانات المطلوبة للأطفال المتوفرين، مثل تاريخ الميلاد أو تاريخ الحسم."
        elif eligible_count == 0:
            interpretation_ar = "لم يتم العثور على أطفال يحققون شرط العمر ضمن الفلاتر المحددة، بعد تنفيذ الحساب بنجاح على البيانات المتاحة."
        else:
            interpretation_ar = (
                f"أظهرت البيانات وجود {eligible_count:,} طفلاً مؤهلاً للقبول في سنة {admission_year} وفق تاريخ الحسم المحدد، "
                f"من أصل {eval_denominator:,} أطفال أمكن تقييم أعمارهم. "
                f"وقد تركزت أعلى أعداد الأطفال المؤهلين في محافظة {highest_gov}. "
                f"في حين تعذر تقييم أهلية {unevaluatable_count:,} طفلاً بسبب غياب تاريخ الميلاد أو نقص البيانات الجغرافية الأساسية، "
                f"وهو ما يمثل {100.0 - completeness_rate:.1f}% من السجلات. لذلك يجب التعامل مع الإجمالي بوصفه حداً أدنى مبنياً على السجلات المكتملة."
            )

        # Decision implications matrix
        decision_implications = [
            {
                "observation": "ارتفاع عدد المؤهلين في منطقة محددة",
                "evidence": f"وجود {eligible_count:,} طفلاً مؤهلاً يتركز الجزء الأكبر منهم في {highest_gov}",
                "implication": "طلب متوقع مرتفع قد يسبب ضغطاً على الغرف الصفية المتوفرة",
                "action": "مقارنة عدد الأطفال المؤهلين بالطاقة الاستيعابية للمدارس والحضانات القائمة في تلك المناطق"
            },
            {
                "observation": "وجود سجلات غير قابلة للتقييم",
                "evidence": f"تعذر تقييم {unevaluatable_count:,} سجلاً بنسبة خطأ {100.0 - completeness_rate:.1f}%",
                "implication": "مستوى الثقة في التقديرات الإجمالية محدود وقد يعرض أرقاماً أقل من الواقع",
                "action": "توجيه مدراء المديريات لاستكمال تواريخ الميلاد المفقودة وعناوين أولياء الأمور الجغرافية"
            }
        ]

        breakdowns = []
        for key, counts in breakdown_data.items():
            total_grp = counts["eligible"] + counts["ineligible"] + counts["unevaluatable"]
            eval_grp = counts["eligible"] + counts["ineligible"]
            rate_grp = (counts["eligible"] / eval_grp * 100) if eval_grp > 0 else 0.0
            comp_grp = (eval_grp / total_grp * 100) if total_grp > 0 else 0.0

            breakdowns.append({
                group_dim: key,
                "total_children": total_grp,
                "eligible_children": counts["eligible"],
                "ineligible_children": counts["ineligible"],
                "unevaluatable_records": counts["unevaluatable"],
                "eligibility_rate": round(rate_grp, 1),
                "data_completeness_rate": round(comp_grp, 1),
                "male": counts["male"],
                "female": counts["female"],
                "unspecified_gender": counts["unspecified_gender"],
            })

        chart_series = []
        for key, counts in breakdown_data.items():
            chart_series.append({
                "label": key,
                "value": counts["eligible"],
            })
        chart_series.sort(key=lambda s: s["value"], reverse=True)

        if group_dim == "governorate":
            chart_title_ar = "توزيع الأطفال المؤهلين حسب المحافظة"
            x_label = "المحافظة"
        elif group_dim == "district":
            chart_title_ar = "توزيع الأطفال المؤهلين حسب اللواء"
            x_label = "اللواء"
        else:
            chart_title_ar = "توزيع الأطفال المؤهلين حسب المنطقة"
            x_label = "المنطقة"

        chart = {
            "type": "bar",
            "title_ar": chart_title_ar,
            "x_axis_title_ar": x_label,
            "y_axis_title_ar": "عدد الأطفال المؤهلين",
            "series": chart_series[:15],
            "group_by": group_dim,
            "show_share_pct": True,
        }

        gender_eligible_counts = {"ذكور": 0, "إناث": 0, "غير محدد": 0}
        for c in children:
            if c.date_of_birth and c.date_of_birth <= latest_eligible_birth_date and c.home_governorate:
                g_str = str(c.gender).lower() if c.gender else ""
                if "male" in g_str:
                    gender_eligible_counts["ذكور"] += 1
                elif "female" in g_str:
                    gender_eligible_counts["إناث"] += 1
                else:
                    gender_eligible_counts["غير محدد"] += 1

        gender_series = [
            {"label": "ذكور", "value": gender_eligible_counts["ذكور"]},
            {"label": "إناث", "value": gender_eligible_counts["إناث"]},
        ]
        if gender_eligible_counts["غير محدد"] > 0:
            gender_series.append({"label": "غير محدد", "value": gender_eligible_counts["غير محدد"]})

        license_chart = {
            "type": "pie",
            "title_ar": "توزيع الأطفال المؤهلين حسب الجنس",
            "series": gender_series,
        }

        payload = self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {
                "admission_year": admission_year,
                "cutoff_date": cutoff_date.isoformat(),
                "required_age": required_age,
                "last_eligible_birth_date": latest_eligible_birth_date.isoformat(),
                "eligible_children": eligible_count,
                "ineligible_children": ineligible_count,
                "unevaluatable_records": unevaluatable_count,
                "total_evaluated": total_evaluated,
                "eligibility_rate": round(eligibility_rate, 1),
                "data_completeness_rate": round(completeness_rate, 1),
                "highest_governorate": highest_gov,
                "interpretation_ar": interpretation_ar,
                "decision_implications": decision_implications,
            },
            breakdowns,
            chart=chart,
        )
        payload["license_chart"] = license_chart
        return payload

    def _children_profile(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.Child.gender,
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
            models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.gender
        ).all()
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
        return self._payload(agency_code, agency, report_code, report, filters, {"total_children": total}, breakdowns)

    def _vaccination_due_children(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
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
        _gender = _coerce_enum(models.Gender, filters.get("gender"))
        if _gender is not None:
            q = q.filter(models.Child.gender == _gender)

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
            {"label": vac, "value": per_vaccine.get(vac, 0)} for vac in vaccine_order if per_vaccine.get(vac, 0) > 0
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

    def _kindergarten_registry(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = self.db.query(
            models.Kindergarten.governorate,
            models.Kindergarten.district,
            models.Kindergarten.status,
            func.count(models.Kindergarten.id).label("count"),
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        _kg_status = _coerce_enum(models.KindergartenStatus, filters.get("status"))
        if _kg_status is not None:
            q = q.filter(models.Kindergarten.status == _kg_status)
        rows = q.group_by(
            models.Kindergarten.governorate, models.Kindergarten.district, models.Kindergarten.status
        ).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "status": _kindergarten_status_ar(r.status),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)
        active = sum(_safe_int(r.count) for r in rows if _enum_value(r.status) == "ACTIVE")

        gov_filter = filters.get("governorate")
        if gov_filter:
            group_dim = "district"
        else:
            group_dim = "governorate"

        geo_counts = {}
        for r in rows:
            key = r.district if gov_filter else r.governorate
            key = key or "غير محدد"
            geo_counts[key] = geo_counts.get(key, 0) + _safe_int(r.count)
        
        chart_series = [{"label": k, "value": v} for k, v in geo_counts.items()]
        chart_series.sort(key=lambda s: s["value"], reverse=True)

        chart_title = "توزيع الحضانات حسب اللواء" if gov_filter else "توزيع الحضانات حسب المحافظة"
        chart = {
            "type": "bar",
            "title_ar": chart_title,
            "x_axis_title_ar": "اللواء" if gov_filter else "المحافظة",
            "y_axis_title_ar": "عدد الحضانات",
            "series": chart_series[:15],
            "group_by": group_dim,
            "show_share_pct": True,
        }

        status_colors = {
            "نشطة": "#16a34a",
            "غير نشطة": "#dc2626",
            "مسودة": "#64748b",
            "مجمّدة": "#d97706",
            "غير محدد": "#cbd5e1",
        }
        status_counts = {}
        for r in rows:
            lbl = _kindergarten_status_ar(r.status)
            status_counts[lbl] = status_counts.get(lbl, 0) + _safe_int(r.count)

        status_series = []
        for lbl, v in status_counts.items():
            status_series.append({
                "label": lbl,
                "value": v,
                "color": status_colors.get(lbl, "#cbd5e1"),
            })
        status_series.sort(key=lambda s: s["value"], reverse=True)

        license_chart = {
            "type": "pie",
            "title_ar": "توزيع الحضانات حسب الحالة التشغيلية",
            "series": status_series,
        }

        payload = self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {"total_kindergartens": total, "active_kindergartens": active},
            breakdowns,
            chart=chart,
        )
        payload["license_chart"] = license_chart
        return payload

    def _workforce_summary(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.User.role,
                func.count(models.User.id).label("count"),
            )
            .join(models.Kindergarten, models.Kindergarten.id == models.User.kindergarten_id)
            .filter(
                models.User.deleted_at.is_(None),
                models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district, models.User.role).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "role": _role_ar(r.role),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        # Aggregate from the raw enum, not the localized display label.
        supervisors = sum(_safe_int(r.count) for r in rows if _enum_value(r.role) == "SUPERVISOR")
        managers = sum(_safe_int(r.count) for r in rows if _enum_value(r.role) == "MANAGER")
        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {"managers": managers, "supervisors": supervisors, "total_staff": managers + supervisors},
            breakdowns,
        )

    def _training_compliance(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        total = self.db.query(func.count(models.StaffTrainingCompletion.id)).scalar() or 0
        completed = (
            self.db.query(func.count(models.StaffTrainingCompletion.id))
            .filter(models.StaffTrainingCompletion.status == models.TrainingStatus.COMPLETED)
            .scalar()
            or 0
        )
        breakdowns = [
            {"status": "مكتمل", "count": _safe_int(completed)},
            {"status": "الإجمالي", "count": _safe_int(total)},
        ]
        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {
                "training_records": _safe_int(total),
                "completed": _safe_int(completed),
                "completion_rate_pct": _safe_pct(completed, total),
            },
            breakdowns,
        )

    def _family_communication_counts(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = self.db.query(models.Message.thread_type, func.count(models.Message.id).label("count"))
        if filters.get("kindergarten_id"):
            q = q.filter(models.Message.kindergarten_id == int(filters["kindergarten_id"]))
        rows = q.group_by(models.Message.thread_type).all()
        breakdowns = [{"thread_type": _thread_type_ar(r.thread_type), "count": _safe_int(r.count)} for r in rows]
        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {"message_count": sum(r["count"] for r in breakdowns)},
            breakdowns,
        )

    def _child_safety(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        start, end = _resolve_dos_period(filters)
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.Incident.severity_level,
                func.count(models.Incident.id).label("count"),
            )
            .join(models.Kindergarten, models.Kindergarten.id == models.Incident.kindergarten_id)
            .filter(
                models.Incident.deleted_at.is_(None),
                *jordan_date_range_filter(models.Incident.occurred_at, start, end),
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        _severity = _coerce_enum(models.SeverityLevel, filters.get("severity"))
        if _severity is not None:
            q = q.filter(models.Incident.severity_level == _severity)
        rows = q.group_by(
            models.Kindergarten.governorate, models.Kindergarten.district, models.Incident.severity_level
        ).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "severity": _severity_ar(r.severity_level),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)

        chart = None
        if breakdowns:
            severity_counts: dict[str, int] = {}
            for r in rows:
                label = _severity_ar(_enum_value(r.severity_level))
                severity_counts[label] = severity_counts.get(label, 0) + _safe_int(r.count)
            severity_series = [{"label": label, "value": severity_counts.get(label, 0)} for label in severity_counts]
            chart = {
                "type": "bar",
                "title_ar": "الحوادث حسب درجة الخطورة",
                "series": severity_series,
            }

        summary = {"incident_count": total}
        if not total:
            summary["data_quality_note_ar"] = "لا توجد حوادث مسجّلة ضمن الفترة المحددة."

        return self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns, chart=chart)

    def _service_access_gaps(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        aliases = settings.JORDAN_GOVERNORATE_ALIASES

        def _normalize_gov(name: Any) -> str:
            if not name:
                return name or "غير محدد"
            s = str(name)
            return aliases.get(s) or aliases.get(s.lower(), s)

        # 1. Determine dynamic grouping dimension, titles, and query paths based on geo filters
        if filters.get("city"):
            group_dim = "area"
            y_axis_title = "المنطقة / الحي"
            chart_title = f"فجوة الوصول للخدمة في {filters['city']}: الأطفال لكل حضانة حسب المنطقة"

            child_rows = (
                self.db.query(
                    models.ParentProfile.home_governorate,
                    models.ParentProfile.home_district,
                    models.ParentProfile.home_area,
                    func.count(models.Child.id).label("children"),
                )
                .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
                .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
            )
            child_rows = self._apply_parent_geo_filters(child_rows, filters)
            child_rows = child_rows.group_by(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.ParentProfile.home_area,
            ).all()

            child_index = {}
            for r in child_rows:
                key = (_normalize_gov(r.home_governorate), r.home_district or "غير محدد", r.home_area or "غير محدد")
                child_index[key] = child_index.get(key, 0) + _safe_int(r.children)

            kg_rows = self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.Kindergarten.area,
                func.count(models.Kindergarten.id).label("kindergartens"),
            ).filter(
                models.Kindergarten.deleted_at.is_(None),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            )
            kg_rows = self._apply_kindergarten_geo_filters(kg_rows, filters)
            kg_rows = kg_rows.group_by(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.Kindergarten.area,
            ).all()

            kg_index = {}
            for r in kg_rows:
                key = (_normalize_gov(r.governorate), r.district or "غير محدد", r.area or "غير محدد")
                kg_index[key] = kg_index.get(key, 0) + _safe_int(r.kindergartens)

            all_keys = set(child_index.keys()) | set(kg_index.keys())
            breakdowns = []
            unserved_districts_count = 0
            unserved_children_count = 0

            for gov, dist, area in all_keys:
                children = child_index.get((gov, dist, area), 0)
                kgs = kg_index.get((gov, dist, area), 0)
                ratio = round(children / kgs, 2) if kgs > 0 else None
                is_unserved = bool(kgs == 0 and children > 0)
                if is_unserved:
                    unserved_districts_count += 1
                    unserved_children_count += children

                breakdowns.append(
                    {
                        "governorate": gov,
                        "city": dist,
                        "area": area,
                        "children": children,
                        "active_kindergartens": kgs,
                        "children_per_kindergarten": ratio,
                        "is_unserved_zone": is_unserved,
                        "status_ar": "محرومة من الخدمة" if is_unserved else ("خدمة متاحة" if kgs > 0 else "بدون أطفال مسجلين"),
                    }
                )
        else:
            if filters.get("governorate"):
                group_dim = "city"
                y_axis_title = "اللواء"
                chart_title = f"فجوة الوصول للخدمة في محافظة {filters['governorate']}: الأطفال لكل حضانة نشطة حسب اللواء"
            else:
                group_dim = "governorate"
                y_axis_title = "المحافظة"
                chart_title = "فجوة الوصول للخدمة: أطفال لكل حضانة نشطة حسب المحافظة"

            child_rows = (
                self.db.query(
                    models.ParentProfile.home_governorate,
                    models.ParentProfile.home_district,
                    func.count(models.Child.id).label("children"),
                )
                .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
                .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
            )
            child_rows = self._apply_parent_geo_filters(child_rows, filters)
            child_rows = child_rows.group_by(
                models.ParentProfile.home_governorate, models.ParentProfile.home_district
            ).all()

            child_index = {}
            for r in child_rows:
                key = (_normalize_gov(r.home_governorate), r.home_district or "غير محدد")
                child_index[key] = child_index.get(key, 0) + _safe_int(r.children)

            kg_rows = self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.count(models.Kindergarten.id).label("kindergartens"),
            ).filter(
                models.Kindergarten.deleted_at.is_(None),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            )
            kg_rows = self._apply_kindergarten_geo_filters(kg_rows, filters)
            kg_rows = kg_rows.group_by(models.Kindergarten.governorate, models.Kindergarten.district).all()

            kg_index = {}
            for r in kg_rows:
                key = (_normalize_gov(r.governorate), r.district or "غير محدد")
                kg_index[key] = kg_index.get(key, 0) + _safe_int(r.kindergartens)

            all_keys = set(child_index.keys()) | set(kg_index.keys())
            breakdowns = []
            unserved_districts_count = 0
            unserved_children_count = 0

            for gov, dist in all_keys:
                children = child_index.get((gov, dist), 0)
                kgs = kg_index.get((gov, dist), 0)
                ratio = round(children / kgs, 2) if kgs > 0 else None
                is_unserved = bool(kgs == 0 and children > 0)
                if is_unserved:
                    unserved_districts_count += 1
                    unserved_children_count += children

                breakdowns.append(
                    {
                        "governorate": gov,
                        "city": dist,
                        "children": children,
                        "active_kindergartens": kgs,
                        "children_per_kindergarten": ratio,
                        "is_unserved_zone": is_unserved,
                        "status_ar": "محرومة من الخدمة" if is_unserved else ("خدمة متاحة" if kgs > 0 else "بدون أطفال مسجلين"),
                    }
                )

        total_children = sum(r["children"] for r in breakdowns)
        total_kgs = sum(r["active_kindergartens"] for r in breakdowns)
        overall_ratio = round(total_children / total_kgs, 2) if total_kgs > 0 else None

        # 4. Chart building — dynamic grouping dimension
        chart = None
        if breakdowns:
            group_children: dict[str, int] = {}
            group_kgs: dict[str, int] = {}
            group_unserved: dict[str, bool] = {}

            for b in breakdowns:
                label = b[group_dim]
                group_children[label] = group_children.get(label, 0) + b["children"]
                group_kgs[label] = group_kgs.get(label, 0) + b["active_kindergartens"]
                if b["is_unserved_zone"]:
                    group_unserved[label] = True

            chart_series = []
            for label, c_cnt in group_children.items():
                k_cnt = group_kgs.get(label, 0)
                val = round(c_cnt / k_cnt, 2) if k_cnt > 0 else None
                chart_series.append(
                    {
                        "label": label,
                        "value": val,
                        "children": c_cnt,
                        "kindergartens": k_cnt,
                        "is_unserved": group_unserved.get(label, False),
                    }
                )

            chart_series.sort(
                key=lambda s: (s["is_unserved"], s["value"] if s["value"] is not None else -1),
                reverse=True,
            )

            ratios = [float(s["value"]) for s in chart_series if isinstance(s.get("value"), (int, float))]
            max_ratio = max(ratios) if ratios else 0.0

            for s in chart_series:
                v = s.get("value")
                if s.get("is_unserved"):
                    s["color"] = "#dc2626"  # Critical red for unserved
                elif not isinstance(v, (int, float)) or max_ratio <= 0:
                    s["color"] = "#64748b"
                elif float(v) >= max_ratio * 0.75:
                    s["color"] = "#dc2626"  # High pressure red
                elif float(v) >= max_ratio * 0.45:
                    s["color"] = "#f59e0b"  # Medium pressure orange
                else:
                    s["color"] = "#22c55e"  # Lower pressure green

            chart = {
                "type": "bar",
                "title_ar": chart_title,
                "series": chart_series,
                "group_by": group_dim,
                "value_suffix": " طفل/حضانة",
                "x_axis_title_ar": "الأطفال لكل حضانة نشطة",
                "y_axis_title_ar": y_axis_title,
            }

        summary = {
            "areas": len(breakdowns),
            "children": total_children,
            "active_kindergartens": total_kgs,
            "national_ratio": overall_ratio,
            "unserved_districts_count": unserved_districts_count,
            "unserved_children_count": unserved_children_count,
            "data_quality_note_ar": (
                "تم حساب نسبة الأطفال لكل حضانة على أساس سكن ولي الأمر مقابل الحضانات النشطة في نفس المنطقة الجغرافية. "
                "تمت إضافة إشارة خاصة للمناطق المحرومة (أطفال مسجلون مع 0 حضانة نشطة) لدعم قرارات التخطيط والاستثمار التنموي."
            ),
        }

        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            summary,
            sorted(
                breakdowns,
                key=lambda x: (x["is_unserved_zone"], x["children_per_kindergarten"] if x["children_per_kindergarten"] is not None else -1),
                reverse=True,
            ),
            chart=chart,
        )

    def _mopic_capacity_readiness(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        aliases = settings.JORDAN_GOVERNORATE_ALIASES

        def _normalize_gov(name: Any) -> str:
            if not name:
                return name or "غير محدد"
            s = str(name)
            return aliases.get(s) or aliases.get(s.lower(), s)

        # Query Capacity & Enrolled Children from Kindergarten & Class
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.count(models.Kindergarten.id.distinct()).label("active_kindergartens"),
                func.coalesce(func.sum(models.Class.capacity_total), 0).label("capacity"),
                func.coalesce(func.sum(models.Class.enrolled_children_count), 0).label("enrolled"),
            )
            .outerjoin(
                models.Class,
                and_(
                    models.Class.kindergarten_id == models.Kindergarten.id,
                    models.Class.deleted_at.is_(None),
                ),
            )
            .filter(
                models.Kindergarten.deleted_at.is_(None),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district).all()

        breakdowns = []
        total_capacity = 0
        total_enrolled = 0
        total_kgs = 0
        overcrowded_count = 0

        for r in rows:
            gov = _normalize_gov(r.governorate)
            dist = r.district or "غير محدد"
            kgs = _safe_int(r.active_kindergartens)
            cap = _safe_int(r.capacity)
            enr = _safe_int(r.enrolled)
            occ_rate = round((enr / cap) * 100, 1) if cap > 0 else 0.0
            avail_cap = max(0, cap - enr)
            is_overcrowded = bool(enr > cap and cap > 0)
            if is_overcrowded:
                overcrowded_count += 1

            total_capacity += cap
            total_enrolled += enr
            total_kgs += kgs

            breakdowns.append(
                {
                    "governorate": gov,
                    "city": dist,
                    "active_kindergartens": kgs,
                    "capacity": cap,
                    "enrolled": enr,
                    "occupancy_rate_pct": occ_rate,
                    "available_expansion_capacity": avail_cap,
                    "is_overcrowded": is_overcrowded,
                    "status_ar": "اكتظاظ متجاوز للسعة" if is_overcrowded else ("جاهزية عالية" if occ_rate < 85 else "إشغال مرتفع"),
                }
            )

        overall_occ_rate = round((total_enrolled / total_capacity) * 100, 1) if total_capacity > 0 else 0.0
        total_available = max(0, total_capacity - total_enrolled)

        chart = None
        if breakdowns:
            group_dim = "city" if (filters.get("governorate") or filters.get("city")) else "governorate"
            group_cap: dict[str, int] = {}
            group_enr: dict[str, int] = {}

            for b in breakdowns:
                lbl = b[group_dim]
                group_cap[lbl] = group_cap.get(lbl, 0) + b["capacity"]
                group_enr[lbl] = group_enr.get(lbl, 0) + b["enrolled"]

            chart_series = []
            for lbl, c_val in group_cap.items():
                e_val = group_enr.get(lbl, 0)
                rate = round((e_val / c_val) * 100, 1) if c_val > 0 else 0.0
                chart_series.append(
                    {
                        "label": lbl,
                        "value": rate,
                        "capacity": c_val,
                        "enrolled": e_val,
                        "color": "#dc2626" if rate >= 90 else ("#f59e0b" if rate >= 70 else "#22c55e"),
                    }
                )

            chart_series.sort(key=lambda s: s["value"], reverse=True)

            chart = {
                "type": "bar",
                "title_ar": "معدلات إشغال السعة الاستيعابية حسب المنطقة (%)",
                "series": chart_series,
                "group_by": group_dim,
                "value_suffix": "%",
                "x_axis_title_ar": "نسبة الإشغال (%)",
                "y_axis_title_ar": "اللواء / المحافظة" if group_dim == "city" else "المحافظة",
            }

        summary = {
            "active_kindergartens": total_kgs,
            "total_capacity": total_capacity,
            "total_enrolled": total_enrolled,
            "overall_occupancy_rate_pct": overall_occ_rate,
            "total_available_expansion_capacity": total_available,
            "overcrowded_districts_count": overcrowded_count,
            "data_quality_note_ar": "تستند السعة الاستيعابية إلى الطاقة الاستيعابية المرخصة المحددة للشُعب الصفية في الحضانات النشطة.",
        }

        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            summary,
            sorted(breakdowns, key=lambda x: x["occupancy_rate_pct"], reverse=True),
            chart=chart,
        )

    def _mopic_investment_priorities(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        aliases = settings.JORDAN_GOVERNORATE_ALIASES

        def _normalize_gov(name: Any) -> str:
            if not name:
                return name or "غير محدد"
            s = str(name)
            return aliases.get(s) or aliases.get(s.lower(), s)

        # 1. Children per governorate
        child_q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                func.count(models.Child.id).label("children"),
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.ParentProfile.deleted_at.is_(None))
        )
        child_q = self._apply_parent_geo_filters(child_q, filters)
        child_rows = child_q.group_by(models.ParentProfile.home_governorate).all()

        child_map = {_normalize_gov(r.home_governorate): _safe_int(r.children) for r in child_rows}

        # 2. Kindergartens & Capacity per governorate
        kg_q = (
            self.db.query(
                models.Kindergarten.governorate,
                func.count(models.Kindergarten.id.distinct()).label("active_kindergartens"),
                func.coalesce(func.sum(models.Class.capacity_total), 0).label("capacity"),
                func.coalesce(func.sum(models.Class.enrolled_children_count), 0).label("enrolled"),
            )
            .outerjoin(
                models.Class,
                and_(
                    models.Class.kindergarten_id == models.Kindergarten.id,
                    models.Class.deleted_at.is_(None),
                ),
            )
            .filter(
                models.Kindergarten.deleted_at.is_(None),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            )
        )
        kg_q = self._apply_kindergarten_geo_filters(kg_q, filters)
        kg_rows = kg_q.group_by(models.Kindergarten.governorate).all()

        kg_map = {
            _normalize_gov(r.governorate): {
                "kgs": _safe_int(r.active_kindergartens),
                "cap": _safe_int(r.capacity),
                "enr": _safe_int(r.enrolled),
            }
            for r in kg_rows
        }

        all_govs = set(child_map.keys()) | set(kg_map.keys())
        breakdowns = []
        scores = []

        for gov in all_govs:
            c_cnt = child_map.get(gov, 0)
            k_data = kg_map.get(gov, {"kgs": 0, "cap": 0, "enr": 0})
            kgs = k_data["kgs"]
            cap = k_data["cap"]
            enr = k_data["enr"]

            occ_rate = round((enr / cap) * 100, 1) if cap > 0 else 100.0
            unserved_factor = 100.0 if kgs == 0 and c_cnt > 0 else (round((c_cnt / (kgs * 25)) * 100, 1) if kgs > 0 else 0.0)
            unserved_factor = min(100.0, max(0.0, unserved_factor))
            score = round(0.6 * unserved_factor + 0.4 * min(100.0, occ_rate), 1)

            scores.append(score)
            breakdowns.append(
                {
                    "governorate": gov,
                    "children": c_cnt,
                    "active_kindergartens": kgs,
                    "capacity": cap,
                    "enrolled": enr,
                    "occupancy_rate_pct": occ_rate,
                    "investment_priority_score": score,
                    "priority_level_ar": "أولوية تنموية قصوى" if score >= 75 else ("أولوية متوسطة" if score >= 45 else "أولوية عادية"),
                }
            )

        breakdowns.sort(key=lambda b: b["investment_priority_score"], reverse=True)
        for rank, b in enumerate(breakdowns, start=1):
            b["priority_rank"] = rank

        chart = None
        if breakdowns:
            chart_series = [
                {
                    "label": b["governorate"],
                    "value": b["investment_priority_score"],
                    "color": "#dc2626" if b["investment_priority_score"] >= 75 else ("#f59e0b" if b["investment_priority_score"] >= 45 else "#22c55e"),
                }
                for b in breakdowns
            ]
            chart = {
                "type": "bar",
                "title_ar": "مؤشر أولويات الاستثمار التنموي حسب المحافظة (من 100)",
                "series": chart_series,
                "group_by": "governorate",
                "value_suffix": " درجة",
                "x_axis_title_ar": "درجة الأولوية التنموية",
                "y_axis_title_ar": "المحافظة",
            }

        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        top_priority_gov = breakdowns[0]["governorate"] if breakdowns else "غير محدد"

        summary = {
            "governorates_count": len(breakdowns),
            "top_priority_governorate": top_priority_gov,
            "average_investment_priority_score": avg_score,
            "data_quality_note_ar": "تم احتساب مؤشر الأولوية بدمج عجز السعة ونسبة الأطفال غير المخدومين لمساعدة وزارة التخطيط على توجيه المخصصات.",
        }

        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            summary,
            breakdowns,
            chart=chart,
        )

    def _dos_children_demographics(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                models.Child.gender,
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
            models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.gender
        ).all()
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
        return self._payload(agency_code, agency, report_code, report, filters, {"total_children": total}, breakdowns)

    def _dos_enrollment_participation(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        today = datetime.now(_JORDAN_TZ).date()
        date_60m_ago = _date_plus_months(today, -60)
        q = (
            self.db.query(
                models.ParentProfile.home_governorate, models.ParentProfile.home_district, models.Child.date_of_birth
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
            .filter(
                models.Child.deleted_at.is_(None),
                models.ParentProfile.deleted_at.is_(None),
                models.EnrollmentApplication.is_active == True,
                models.EnrollmentApplication.deleted_at.is_(None),
                models.Child.date_of_birth >= date_60m_ago,
                models.Child.date_of_birth <= today,
            )
        )
        q = self._apply_parent_geo_filters(q, filters)
        _gender = _coerce_enum(models.Gender, filters.get("gender"))
        if _gender is not None:
            q = q.filter(models.Child.gender == _gender)

        rows = q.all()

        detail = defaultdict(lambda: {"total": 0, "0_11": 0, "12_23": 0, "24_35": 0, "36_47": 0, "48_60": 0})
        for r in rows:
            gov = r.home_governorate or "غير محدد"
            city = r.home_district or "غير محدد"
            dob = r.date_of_birth
            age_months = _age_months(dob, today)
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
            elif age_months <= 60:
                detail[key]["48_60"] += 1

        breakdowns = [
            {
                "governorate": k[0],
                "city": k[1],
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

        # Meaningful chart: pie chart for age distribution (omit when empty).
        total_by_age = {
            "0-11 شهر": sum(b["enrolled_0_11m"] for b in breakdowns),
            "12-23 شهر": sum(b["enrolled_12_23m"] for b in breakdowns),
            "24-35 شهر": sum(b["enrolled_24_35m"] for b in breakdowns),
            "36-47 شهر": sum(b["enrolled_36_47m"] for b in breakdowns),
            "48-60 شهر": sum(b["enrolled_48_60m"] for b in breakdowns),
        }
        chart_series = [{"label": k, "value": v} for k, v in total_by_age.items() if v > 0]
        chart = None
        if chart_series:
            chart = {"type": "pie", "title_ar": "التوزيع العمري للأطفال المسجلين (0-60 شهراً)", "series": chart_series}

        return self._payload(
            agency_code, agency, report_code, report, filters, {"enrolled_children": total}, breakdowns, chart=chart
        )

    def _dos_institutions_active(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = self.db.query(
            models.Kindergarten.governorate,
            models.Kindergarten.district,
            models.Kindergarten.status,
            func.count(models.Kindergarten.id).label("count"),
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        _kg_status = _coerce_enum(models.KindergartenStatus, filters.get("status"))
        if _kg_status is not None:
            q = q.filter(models.Kindergarten.status == _kg_status)
        rows = q.group_by(
            models.Kindergarten.governorate, models.Kindergarten.district, models.Kindergarten.status
        ).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "status": _kindergarten_status_ar(r.status),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total = sum(r["count"] for r in breakdowns)
        # Aggregate from the raw enum, not the localized display label.
        active = sum(_safe_int(r.count) for r in rows if _enum_value(r.status) == "ACTIVE")

        # Licensing (the "المرخّصة" half of the title): computed from the real
        # license_valid_until field over the same filtered population. A license
        # is "licensed/valid" when it has not expired; "expired" when a past
        # expiry date exists; "missing" when there is no license record at all —
        # missing is never silently folded into unlicensed=valid or into zero.
        today = datetime.now(_JORDAN_TZ).date()
        _active = models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        _valid = models.Kindergarten.license_valid_until >= today
        lic_q = self.db.query(
            func.sum(case((_valid, 1), else_=0)).label("licensed"),
            func.sum(case((and_(_active, _valid), 1), else_=0)).label("active_licensed"),
            func.sum(case((models.Kindergarten.license_valid_until < today, 1), else_=0)).label("expired"),
            func.sum(case((models.Kindergarten.license_valid_until.is_(None), 1), else_=0)).label("missing"),
        )
        lic_q = self._apply_kindergarten_geo_filters(lic_q, filters)
        if _kg_status is not None:
            lic_q = lic_q.filter(models.Kindergarten.status == _kg_status)
        lic = lic_q.one()

        summary = {
            "total_institutions": total,
            "active_institutions": active,
            "licensed_institutions": _safe_int(lic.licensed),
            "active_and_licensed": _safe_int(lic.active_licensed),
            "expired_licenses": _safe_int(lic.expired),
            "missing_license_data": _safe_int(lic.missing),
        }

        # Explicit chart: status distribution (matches table categories).
        status_counts: dict[str, int] = {}
        for r in rows:
            label = _kindergarten_status_ar(_enum_value(r.status))
            status_counts[label] = status_counts.get(label, 0) + _safe_int(r.count)
        status_series = [{"label": label, "value": status_counts.get(label, 0)} for label in status_counts]
        status_chart = {
            "type": "pie",
            "title_ar": "توزيع الحضانات حسب الحالة التشغيلية",
            "series": status_series,
        }

        # Second explicit chart: license status distribution.
        # Use MUTUALLY EXCLUSIVE slices so the pie chart is statistically valid
        # (no double-counting). The summary above still exposes the broader
        # "licensed_institutions" total for context.
        active_licensed = _safe_int(lic.active_licensed)
        licensed_but_not_active = _safe_int(lic.licensed) - active_licensed
        expired = _safe_int(lic.expired)
        missing = _safe_int(lic.missing)
        lic_series = [
            {"label": "نشطة ومرخّصة", "value": active_licensed},
            {"label": "مرخصة لكن غير نشطة", "value": max(0, licensed_but_not_active)},
            {"label": "تراخيص منتهية", "value": expired},
            {"label": "بدون بيانات ترخيص", "value": missing},
        ]
        lic_chart = {
            "type": "pie",
            "title_ar": "توزيع الحضانات حسب حالة الترخيص",
            "series": lic_series,
        }

        payload = self._payload(
            agency_code, agency, report_code, report, filters, summary, breakdowns, chart=status_chart
        )
        payload["license_chart"] = lic_chart
        return payload

    def _dos_capacity_occupancy(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        # Roll up capacity/enrolment PER kindergarten first, so overcrowding
        # (enrolled > capacity) is judged per institution — not lost inside a
        # governorate-wide sum where a full KG can mask an over-full one.
        q = (
            self.db.query(
                models.Kindergarten.id,
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.sum(models.Class.capacity_total).label("capacity"),
                func.sum(models.Class.enrolled_children_count).label("enrolled"),
            )
            .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
            .filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                models.Class.is_active == True,
                models.Class.deleted_at.is_(None),
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.id, models.Kindergarten.governorate, models.Kindergarten.district).all()

        agg: dict[tuple[str, str], dict[str, int]] = {}
        overcrowded_total = 0
        kgs_with_capacity = 0
        for r in rows:
            cap, enr = _safe_int(r.capacity), _safe_int(r.enrolled)
            key = (r.governorate or "غير محدد", r.district or "غير محدد")
            a = agg.setdefault(key, {"capacity": 0, "enrolled": 0, "overcrowded": 0})
            a["capacity"] += cap
            a["enrolled"] += enr
            if cap > 0:
                kgs_with_capacity += 1
                if enr > cap:
                    a["overcrowded"] += 1
                    overcrowded_total += 1

        breakdowns = [
            {
                "governorate": g,
                "city": d,
                "total_capacity": v["capacity"],
                "total_enrolled": v["enrolled"],
                # Missing capacity is undefined occupancy (rendered "—"), never a
                # misleading 0%.
                "occupancy_rate": _safe_pct(v["enrolled"], v["capacity"]) if v["capacity"] else None,
                "overcrowded_kindergartens": v["overcrowded"],
            }
            for (g, d), v in agg.items()
        ]
        total_cap = sum(r["total_capacity"] for r in breakdowns)
        total_enr = sum(r["total_enrolled"] for r in breakdowns)
        summary = {
            "total_capacity": total_cap,
            "total_enrolled": total_enr,
            "occupancy_rate_pct": _safe_pct(total_enr, total_cap) if total_cap else None,
            "overcrowded_kindergartens": overcrowded_total,
            "overcrowding_rate_pct": _safe_pct(overcrowded_total, kgs_with_capacity) if kgs_with_capacity else None,
        }

        # Explicit chart: occupancy rate per governorate (statistically correct
        # aggregate: ratio of summed children to summed capacity, not average of
        # institution-level percentages).
        chart = None
        if breakdowns:
            gov_cap: dict[str, int] = {}
            gov_enr: dict[str, int] = {}
            for b in breakdowns:
                gov = b["governorate"]
                gov_cap[gov] = gov_cap.get(gov, 0) + (b["total_capacity"] or 0)
                gov_enr[gov] = gov_enr.get(gov, 0) + (b["total_enrolled"] or 0)
            chart_series = [
                {"label": gov, "value": _safe_pct(gov_enr[gov], gov_cap[gov]) if gov_cap[gov] else None}
                for gov in gov_cap
            ]
            chart_series.sort(key=lambda s: s["value"] if s["value"] is not None else -1, reverse=True)
            chart = {
                "type": "bar",
                "title_ar": "نسبة الإشغال حسب المحافظة",
                "series": chart_series,
                "group_by": "governorate",
                "orientation": "vertical",
            }

        return self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns, chart=chart)

    def _dos_monthly_attendance(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        start, end = _resolve_dos_period(filters)
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.AttendanceLog.status,
                func.count(models.AttendanceLog.id).label("count"),
            )
            .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
            .join(models.Kindergarten, models.Kindergarten.id == models.Class.kindergarten_id)
            .filter(models.AttendanceLog.date >= start, models.AttendanceLog.date <= end)
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(
            models.Kindergarten.governorate, models.Kindergarten.district, models.AttendanceLog.status
        ).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "status": _attendance_status_ar(r.status),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total_attendance = sum(r["count"] for r in breakdowns)
        # Full status breakdown: PRESENT/LATE count as attended; ABSENT/EXCUSED as absent.
        present = sum(_safe_int(r.count) for r in rows if _enum_value(r.status) in ("PRESENT", "LATE"))
        absent = sum(_safe_int(r.count) for r in rows if _enum_value(r.status) == "ABSENT")
        excused = sum(_safe_int(r.count) for r in rows if _enum_value(r.status) == "EXCUSED")
        # Expected child-days (working days during active enrolment) for a statistically
        # correct attendance rate, not merely a share of logged records.
        kg_ids = self._custom_kg_ids(filters)
        expected, _ = self._expected_child_days(kg_ids, start, end)
        summary = {
            "total_records": total_attendance,
            "present_records": present,
            "absent_records": absent,
            "excused_records": excused,
            "attendance_rate_pct": _safe_pct(present, expected) if expected else None,
            "absence_rate_pct": _safe_pct(absent, expected) if expected else None,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "expected_child_days": expected,
        }
        if expected is None:
            summary["data_quality_note_ar"] = "لا توجد أيام دوام متاحة ضمن الفترة لاحتساب معدل الحضور."

        chart_counts: dict[str, int] = {
            "حاضر": present,
            "غائب": absent,
            "متأخر": sum(_safe_int(r.count) for r in rows if _enum_value(r.status) == "LATE"),
            "غياب بعذر": excused,
        }
        chart = {
            "type": "bar",
            "title_ar": "توزيع سجلات الحضور والغياب حسب الحالة",
            "series": [{"label": label, "value": count} for label, count in chart_counts.items()],
            "group_by": "status",
            "orientation": "vertical",
        }
        return self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns, chart=chart)

    def _dos_supervisors_child_ratio(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                func.count(func.distinct(models.SupervisorAssignment.supervisor_id)).label("supervisors"),
                func.sum(models.Class.enrolled_children_count).label("enrolled"),
            )
            .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
            .outerjoin(models.SupervisorAssignment, models.SupervisorAssignment.class_id == models.Class.id)
            .filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                models.Class.is_active == True,
                models.Class.deleted_at.is_(None),
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        rows = q.group_by(models.Kindergarten.governorate, models.Kindergarten.district).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "supervisors": _safe_int(r.supervisors),
                "enrolled": _safe_int(r.enrolled),
                "children_per_supervisor": round(_safe_int(r.enrolled) / _safe_int(r.supervisors), 2)
                if _safe_int(r.supervisors)
                else None,
            }
            for r in rows
        ]
        total_sup = sum(r["supervisors"] for r in breakdowns)
        total_enr = sum(r["enrolled"] for r in breakdowns)
        overall_ratio = round(total_enr / max(total_sup, 1), 2) if total_sup else None
        summary = {
            "total_supervisors": total_sup,
            "total_enrolled": total_enr,
            "children_per_supervisor": overall_ratio,
        }

        chart = None
        if breakdowns:
            # Explicit chart: show the weighted ratio per governorate (do NOT sum ratios).
            gov_children: dict[str, int] = {}
            gov_supervisors: dict[str, int] = {}
            for b in breakdowns:
                gov = b["governorate"]
                gov_children[gov] = gov_children.get(gov, 0) + b["enrolled"]
                gov_supervisors[gov] = gov_supervisors.get(gov, 0) + b["supervisors"]
            chart_series = [
                {
                    "label": gov,
                    "value": round(gov_children[gov] / gov_supervisors[gov], 2) if gov_supervisors[gov] else None,
                }
                for gov in gov_children
            ]
            chart_series.sort(key=lambda s: s["value"] if s["value"] is not None else -1, reverse=True)
            chart = {
                "type": "bar",
                "title_ar": "معدل الأطفال لكل مشرفة حسب المحافظة",
                "series": chart_series,
                "orientation": "vertical",
                "value_suffix": " طفل/مشرفة",
            }

        return self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns, chart=chart)

    def _dos_incidents_safety(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        start, end = _resolve_dos_period(filters)
        q = (
            self.db.query(
                models.Kindergarten.governorate,
                models.Kindergarten.district,
                models.Incident.severity_level,
                func.count(models.Incident.id).label("count"),
            )
            .join(models.Kindergarten, models.Kindergarten.id == models.Incident.kindergarten_id)
            .filter(
                models.Incident.deleted_at.is_(None),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                *jordan_date_range_filter(models.Incident.occurred_at, start, end),
            )
        )
        q = self._apply_kindergarten_geo_filters(q, filters)
        _severity = _coerce_enum(models.SeverityLevel, filters.get("severity"))
        if _severity is not None:
            q = q.filter(models.Incident.severity_level == _severity)
        rows = q.group_by(
            models.Kindergarten.governorate, models.Kindergarten.district, models.Incident.severity_level
        ).all()
        breakdowns = [
            {
                "governorate": r.governorate or "غير محدد",
                "city": r.district or "غير محدد",
                "severity": _severity_ar(r.severity_level),
                "count": _safe_int(r.count),
            }
            for r in rows
        ]
        total_incidents = sum(r["count"] for r in breakdowns)

        # Exposure-adjusted rate per 1,000 eligible child-days (expected working
        # days during active enrolment), not merely attended days.
        kg_ids = self._custom_kg_ids(filters)
        expected, _ = self._expected_child_days(kg_ids, start, end)
        rate = round(total_incidents / expected * 1000, 3) if expected else None

        summary = {
            "incident_count": total_incidents,
            "eligible_child_days": expected,
            "incident_rate_per_1000_child_days": rate,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        }
        if rate is None:
            summary["data_quality_note_ar"] = "لا توجد أيام دوام متاحة ضمن الفترة لاحتساب معدل الحوادث لكل 1000 يوم."

        # Build a severity chart ordered by risk (critical -> low) with a clear
        # color scale and percentage share for immediate interpretation.
        severity_counts: dict[str, int] = {}
        for r in rows:
            code = _enum_value(r.severity_level) or "UNKNOWN"
            severity_counts[code] = severity_counts.get(code, 0) + _safe_int(r.count)

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
        severity_series: list[dict[str, Any]] = []
        for code in severity_order:
            count = severity_counts.get(code, 0)
            if count <= 0:
                continue
            severity_series.append(
                {
                    "label": _severity_ar(code),
                    "value": count,
                    "share_pct": round(count / total_incidents * 100, 1) if total_incidents else 0.0,
                    "color": _SEVERITY_COLOR.get(code, _SEVERITY_COLOR["UNKNOWN"]),
                }
            )

        chart = {
            "type": "bar",
            "title_ar": "توزيع الحوادث حسب درجة الخطورة",
            "series": severity_series,
            "orientation": "vertical",
            "value_suffix": " حادثة",
            "show_share_pct": True,
            "x_axis_title_ar": "درجة الخطورة",
            "y_axis_title_ar": "عدد الحوادث",
        }

        return self._payload(agency_code, agency, report_code, report, filters, summary, breakdowns, chart=chart)

    def _dos_data_quality(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        q = (
            self.db.query(
                models.ParentProfile.home_governorate,
                models.ParentProfile.home_district,
                func.count(models.Child.id).label("count"),
            )
            .join(models.ParentProfile, models.ParentProfile.id == models.Child.parent_id)
            .filter(models.Child.deleted_at.is_(None), models.Child.date_of_birth.is_(None))
        )
        q = self._apply_parent_geo_filters(q, filters)
        rows = q.group_by(models.ParentProfile.home_governorate, models.ParentProfile.home_district).all()
        breakdowns = [
            {
                "governorate": r.home_governorate or "غير محدد",
                "city": r.home_district or "غير محدد",
                "missing_dob": _safe_int(r.count),
            }
            for r in rows
        ]
        return self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            {"children_missing_dob": sum(r["missing_dob"] for r in breakdowns)},
            breakdowns,
        )

    def _dos_annual_trends(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        year_filter: int | None = None
        raw_year = filters.get("year")
        if isinstance(raw_year, str) and raw_year.isdigit():
            year_filter = int(raw_year)
        elif isinstance(raw_year, int):
            year_filter = raw_year

        quarter_filter: int | None = None
        raw_quarter = filters.get("quarter")
        if isinstance(raw_quarter, str):
            rq = raw_quarter.strip().upper()
            if rq.startswith("Q") and rq[1:].isdigit():
                qn = int(rq[1:])
                quarter_filter = qn if 1 <= qn <= 4 else None
            elif rq.isdigit():
                qn = int(rq)
                quarter_filter = qn if 1 <= qn <= 4 else None
        elif isinstance(raw_quarter, int) and 1 <= raw_quarter <= 4:
            quarter_filter = raw_quarter

        q = self.db.query(models.Kindergarten.id, models.Kindergarten.created_at).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if year_filter is not None:
            q = q.filter(func.extract("year", models.Kindergarten.created_at) == year_filter)
        if quarter_filter is not None:
            start_month = (quarter_filter - 1) * 3 + 1
            end_month = start_month + 2
            q = q.filter(
                func.extract("month", models.Kindergarten.created_at) >= start_month,
                func.extract("month", models.Kindergarten.created_at) <= end_month,
            )

        active_kgs = q.all()
        kg_ids = [kid for kid, _ in active_kgs]
        enrolled_map: dict[int, int] = {}
        if kg_ids:
            enrolled_rows = (
                self.db.query(
                    models.EnrollmentApplication.kindergarten_id,
                    func.count(func.distinct(models.EnrollmentApplication.child_id)).label("enrolled"),
                )
                .filter(
                    models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                    models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                )
                .group_by(models.EnrollmentApplication.kindergarten_id)
                .all()
            )
            for kid, cnt in enrolled_rows:
                enrolled_map[kid] = _safe_int(cnt)

        by_period: dict[str, dict[str, int]] = {}
        for kid, created_at in active_kgs:
            if not created_at:
                period = "غير محدد"
            else:
                year = created_at.year
                quarter = (created_at.month - 1) // 3 + 1
                period = f"Q{quarter}-{year}"
            bucket = by_period.setdefault(
                period,
                {
                    "year": str(year) if created_at else "غير محدد",
                    "quarter": f"Q{(created_at.month - 1) // 3 + 1}" if created_at else "",
                    "new_kindergartens": 0,
                    "enrolled_children": 0,
                },
            )
            bucket["new_kindergartens"] += 1
            bucket["enrolled_children"] += enrolled_map.get(kid, 0)

        def _chrono_key(item: tuple[str, dict[str, Any]]) -> tuple[int, int, int]:
            # Sort chronologically by (year, quarter), NOT by the "Q{q}-{year}"
            # string (which orders quarter-major, e.g. Q1-2020 before Q2-2019).
            # Undefined-creation-date periods sort last.
            _, v = item
            yr, qr = v.get("year"), v.get("quarter") or ""
            if not (isinstance(yr, str) and yr.isdigit()):
                return (1, 0, 0)
            quarter = int(qr[1:]) if qr.startswith("Q") and qr[1:].isdigit() else 0
            return (0, int(yr), quarter)

        breakdowns = [
            {
                "period": period,
                "year": v["year"],
                "quarter": v["quarter"],
                "new_kindergartens": v["new_kindergartens"],
                "enrolled_children": v["enrolled_children"],
            }
            for period, v in sorted(by_period.items(), key=_chrono_key)
        ]
        total_kg = sum(r["new_kindergartens"] for r in breakdowns)
        total_enr = sum(r["enrolled_children"] for r in breakdowns)

        chart = None
        if breakdowns:
            if year_filter is None:
                # First level: yearly trend for clear time-series overview.
                by_year: dict[str, int] = {}
                for b in breakdowns:
                    y = b.get("year") or "غير محدد"
                    by_year[str(y)] = by_year.get(str(y), 0) + _safe_int(b.get("enrolled_children"))

                def _year_sort_key(item: tuple[str, int]) -> tuple[int, int]:
                    y, _ = item
                    return (0, int(y)) if y.isdigit() else (1, 0)

                chart = {
                    "type": "bar",
                    "title_ar": "الاتجاهات السنوية — الأطفال المسجلون",
                    "series": [{"label": y, "value": v} for y, v in sorted(by_year.items(), key=_year_sort_key)],
                    "group_by": "year",
                    "orientation": "vertical",
                    "value_suffix": " طفل",
                    "x_axis_title_ar": "السنة",
                    "y_axis_title_ar": "الأطفال المسجلون",
                }
            else:
                # Second level after drilling into a year: quarter trend.
                q_order = ["Q1", "Q2", "Q3", "Q4"]
                by_quarter: dict[str, int] = {}
                for b in breakdowns:
                    qv = str(b.get("quarter") or "").upper()
                    if qv.startswith("Q"):
                        by_quarter[qv] = by_quarter.get(qv, 0) + _safe_int(b.get("enrolled_children"))
                chart = {
                    "type": "bar",
                    "title_ar": f"الاتجاهات الربعية — الأطفال المسجلون ({year_filter})",
                    "series": [
                        {
                            "label": _quarter_ar(qn),
                            "drill_value": qn,
                            "value": by_quarter.get(qn, 0),
                        }
                        for qn in q_order
                        if qn in by_quarter
                    ],
                    "group_by": "quarter",
                    "orientation": "vertical",
                    "value_suffix": " طفل",
                    "x_axis_title_ar": "الربع",
                    "y_axis_title_ar": "الأطفال المسجلون",
                }

        summary = {
            "trend_years": len(breakdowns),
            "total_kindergartens": total_kg,
            "total_enrolled_children": total_enr,
            "data_quality_note_ar": (
                "الأرقام تعكس الحالة الحالية للحضانات النشطة والأطفال المسجلين، مصنّفة حسب سنة إنشاء الحضانة. "
                "هذه أرقام رصيد وليست قياس تدفّق خلال فترة زمنية."
            ),
        }

        payload = self._payload(
            agency_code,
            agency,
            report_code,
            report,
            filters,
            summary,
            breakdowns,
            chart=chart,
        )
        return payload

    def _payload(
        self,
        agency_code: str,
        agency: dict[str, Any],
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        summary: dict[str, Any],
        breakdowns: list[dict[str, Any]],
        chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Professionalize the table: add a share column (count breakdowns) and a
        # totals row (المجموع), and pick a robust chart value column.
        value_col, total_row = _finalize_breakdowns(breakdowns)
        table = {"caption_ar": report.get("title_ar"), "rows": breakdowns, "total_row": total_row}

        if chart is None and breakdowns and value_col:
            chart = _build_chart(breakdowns, value_col, report.get("title_ar"))

        payload = {
            "metadata": self._metadata(agency_code, agency, report_code, report, filters),
            "summary": summary,
            "summary_labels": _label_map(summary.keys()),
            "column_labels": _label_map(breakdowns[0].keys() if breakdowns else []),
            "breakdowns": breakdowns,
            "total_row": total_row,
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
            raise AgencyReportError(
                500, f"Sensitive fields blocked from official agency report: {', '.join(text_keys)}"
            )

    # ------------------------------------------------------------------
    # Custom Reports (التقارير المخصصة)
    # ------------------------------------------------------------------
    def custom_report_schema(self) -> dict[str, Any]:
        from agency_reports_registry import custom_report_schema

        return custom_report_schema()

    def custom_report(self, scope: dict[str, Any] | None, suppress: bool = True) -> dict[str, Any]:
        """Build an aggregated custom report from a validated scope.

        ``suppress`` applies small-cell statistical disclosure control. All
        admin surfaces — the interactive in-app view and the CSV export — pass
        ``suppress=False`` so authorized admins always see the real, complete
        values/charts; the flag remains available for future external
        data-sharing contexts.

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
        # Statistical disclosure control is opt-in via ``suppress``. Admin
        # surfaces (interactive view and CSV export) pass suppress=False so the
        # payload always carries the real, complete values.
        suppressed_cells = self._apply_small_cell_suppression(charts, table) if suppress else 0
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
        q = self.db.query(models.Kindergarten.id).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
        if filters.get("governorate"):
            q = q.filter(governorate_filter(models.Kindergarten.governorate, filters["governorate"]))
        if filters.get("city"):
            q = q.filter(models.Kindergarten.district == filters["city"])
        if filters.get("kindergarten_id"):
            q = q.filter(models.Kindergarten.id == filters["kindergarten_id"])
        return [r[0] for r in q.all()]

    @staticmethod
    def _kpi(code: str, label_ar: str, value: Any, unit_ar: str = "") -> dict[str, Any]:
        return {"code": code, "label_ar": label_ar, "value": value, "unit_ar": unit_ar}

    @staticmethod
    def _dist_rows(indicator_ar: str, series: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Table rows for a categorical distribution, each carrying its share of the
        total — the standard way official statistics present a breakdown (count + %)."""
        total = sum(s["value"] for s in series if isinstance(s["value"], (int, float)))
        return [
            {
                "المؤشر": indicator_ar,
                "الفئة": s["label"],
                "القيمة": s["value"],
                "النسبة %": (round(s["value"] / total * 100, 1) if total else 0.0),
            }
            for s in series
        ]

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
        counts = {_enum_value(g): _safe_int(c) for g, c in q.group_by(models.Child.gender).all()}
        # Always show both genders (zero-filled); keep any null/other gender visible.
        series = [
            {"label": "ذكر", "value": counts.get("MALE", 0)},
            {"label": "أنثى", "value": counts.get("FEMALE", 0)},
        ]
        other = sum(v for k, v in counts.items() if k not in ("MALE", "FEMALE"))
        if other:
            series.append({"label": "غير محدد", "value": other})
        total = sum(s["value"] for s in series)
        males = counts.get("MALE", 0)
        return {
            "kpi": self._kpi("gender_distribution", "نسبة الذكور", _safe_pct(males, total), "%"),
            "chart": {"type": "pie", "title_ar": "التوزيع حسب الجنس", "series": series},
            "rows": self._dist_rows("التوزيع حسب الجنس", series),
        }

    def _ind_age_distribution(self, kg_ids, start, end):
        # Age is computed as of the reporting period end, using full year/month/day
        # boundaries (not a year+month approximation). Children with a missing or
        # invalid date of birth stay visible as a data-quality category rather
        # than being silently dropped from the distribution.
        ref = end
        # Fixed 6-month bands across the 0–60 month early-childhood range, always
        # present and zero-filled so every band shows even when it has no children
        # (a partial distribution is misleading — "each 6 months" must be visible).
        MAX_MONTHS = 60
        buckets: dict[str, int] = {f"{low}-{low + 6} شهر": 0 for low in range(0, MAX_MONTHS, 6)}
        over_label = f"{MAX_MONTHS} شهر فأكثر"
        over = 0
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
            if low >= MAX_MONTHS:
                over += 1
            else:
                buckets[f"{low}-{low + 6} شهر"] += 1
        # Dict preserves insertion order (0-6 … 54-60), so no re-sort is needed.
        series = [{"label": k, "value": v} for k, v in buckets.items()]
        if over:
            series.append({"label": over_label, "value": over})
        # KPI reports how many bands actually contain children, not the fixed 10.
        band_count = sum(1 for s in series if s["value"] > 0)
        if unknown:
            series.append({"label": "غير معروف", "value": unknown})
        return {
            "kpi": self._kpi("age_distribution_6mo", "عدد الفئات العمرية (كل 6 أشهر)", band_count, "فئة"),
            "chart": {"type": "bar", "title_ar": "التوزيع العمري كل 6 أشهر", "series": series},
            "rows": self._dist_rows("التوزيع العمري", series),
            "note": (f"يوجد {unknown} طفل بدون تاريخ ميلاد صالح ضمن النطاق." if unknown else None),
        }

    def _ind_enrollment_status(self, kg_ids, start, end):
        q = self.db.query(models.EnrollmentApplication.status, func.count(models.EnrollmentApplication.id))
        if kg_ids is not None:
            q = q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        counts = {_enum_value(s): _safe_int(c) for s, c in q.group_by(models.EnrollmentApplication.status).all()}
        # Show every enrollment status (zero-filled, localized) for a complete view
        # instead of only the statuses that happen to appear, with raw enum labels.
        series = [
            {"label": _enrollment_status_ar(st.value), "value": counts.get(st.value, 0)}
            for st in models.EnrollmentStatus
        ]
        active = counts.get("ACTIVE", 0)
        return {
            "kpi": self._kpi("enrollment_status", "التسجيلات النشطة", active, "تسجيل"),
            "chart": {"type": "bar", "title_ar": "حالة التسجيل", "series": series},
            "rows": self._dist_rows("حالة التسجيل", series),
        }

    # -- kindergartens / capacity -------------------------------------
    def _kg_query(self, kg_ids: list[int] | None):
        q = self.db.query(models.Kindergarten).filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)
        if kg_ids is not None:
            q = q.filter(models.Kindergarten.id.in_(kg_ids))
        return q

    def _ind_kindergarten_count(self, kg_ids, start, end):
        total = self._kg_query(kg_ids).count()
        return {
            "kpi": self._kpi("kindergarten_count", "عدد الحضانات", total, "حضانة"),
            "rows": [{"المؤشر": "عدد الحضانات", "القيمة": total}],
        }

    def _ind_kindergarten_status(self, kg_ids, start, end):
        q = self.db.query(models.Kindergarten.status, func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status != models.KindergartenStatus.DELETED
        )
        if kg_ids is not None:
            q = q.filter(models.Kindergarten.id.in_(kg_ids))
        counts = {_enum_value(s): _safe_int(c) for s, c in q.group_by(models.Kindergarten.status).all()}
        # Show every operational status (zero-filled, localized), excluding DELETED
        # which is already filtered out of the query above.
        statuses = [st for st in models.KindergartenStatus if st != models.KindergartenStatus.DELETED]
        series = [{"label": _kindergarten_status_ar(st.value), "value": counts.get(st.value, 0)} for st in statuses]
        active = counts.get("ACTIVE", 0)
        return {
            "kpi": self._kpi("kindergarten_status", "الحضانات النشطة", active, "حضانة"),
            "chart": {"type": "pie", "title_ar": "حالة الحضانات", "series": series},
            "rows": self._dist_rows("حالة الحضانة", series),
        }

    def _ind_occupancy_rate(self, kg_ids, start, end):
        cap_q = self.db.query(func.coalesce(func.sum(models.Class.capacity_total), 0)).filter(
            models.Class.is_active.is_(True), models.Class.deleted_at.is_(None)
        )
        enr_q = self.db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
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
            "rows": [
                {
                    "المؤشر": "نسبة الإشغال",
                    "المسجلون": enrolled,
                    "السعة": capacity,
                    "النسبة %": (pct if pct is not None else "—"),
                }
            ],
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
        return [
            r[0]
            for r in self.db.query(models.Kindergarten.id)
            .filter(models.Kindergarten.status != models.KindergartenStatus.DELETED)
            .all()
        ]

    def _working_days_by_kg(self, kg_ids: list[int], start: date, end: date) -> dict[int, set]:
        if start > end or not kg_ids:
            return {kid: set() for kid in kg_ids}
        overrides: dict[int, dict] = defaultdict(dict)
        for kid, d, is_open in (
            self.db.query(
                models.OperatingCalendar.kindergarten_id,
                models.OperatingCalendar.date,
                models.OperatingCalendar.is_open,
            )
            .filter(
                models.OperatingCalendar.kindergarten_id.in_(kg_ids),
                models.OperatingCalendar.date >= start,
                models.OperatingCalendar.date <= end,
            )
            .all()
        ):
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
        rows = (
            self.db.query(
                models.EnrollmentApplication.child_id,
                models.EnrollmentApplication.kindergarten_id,
                models.EnrollmentApplication.enrollment_start_date,
                models.EnrollmentApplication.enrollment_end_date,
            )
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(resolved),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                or_(
                    models.EnrollmentApplication.enrollment_end_date.is_(None),
                    models.EnrollmentApplication.enrollment_end_date >= start,
                ),
                or_(
                    models.EnrollmentApplication.enrollment_start_date.is_(None),
                    models.EnrollmentApplication.enrollment_start_date <= end,
                ),
            )
            .all()
        )
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
        return _safe_int(
            self.db.query(func.count(models.AttendanceLog.id))
            .filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date >= start,
                models.AttendanceLog.date <= end,
                models.AttendanceLog.status.in_([models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE]),
            )
            .scalar()
        )

    # -- attendance ----------------------------------------------------
    def _ind_attendance_rate(self, kg_ids, start, end):
        expected, expected_by_child = self._expected_child_days(kg_ids, start, end)
        attended = self._attended_child_days(list(expected_by_child.keys()), start, end)
        # Denominator is expected child-days on working days, not "all rows".
        pct = _safe_pct(attended, expected) if expected else None
        return {
            "kpi": self._kpi("attendance_rate", "نسبة الحضور", pct, "%"),
            "rows": [
                {
                    "المؤشر": "نسبة الحضور",
                    "أيام الحضور المتوقعة": expected,
                    "أيام حضور فعلية": attended,
                    "النسبة %": (pct if pct is not None else "—"),
                }
            ],
            "note": ("لا توجد أيام حضور متوقعة ضمن النطاق (لا يوجد تسجيل نشط أو أيام دوام)." if not expected else None),
        }

    def _ind_absence_requests(self, kg_ids, start, end):
        # Count absence requests that OVERLAP the period (start <= period_end and
        # end >= period_start), not only those whose start falls inside it — an
        # absence spanning into the period must still be counted.
        q = self.db.query(func.count(models.AbsenceRequest.id)).filter(
            models.AbsenceRequest.start_date <= end, models.AbsenceRequest.end_date >= start
        )
        if kg_ids is not None:
            q = q.filter(models.AbsenceRequest.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {
            "kpi": self._kpi("absence_requests", "طلبات الغياب", total, "طلب"),
            "rows": [{"المؤشر": "طلبات الغياب", "القيمة": total}],
        }

    # -- daily reports -------------------------------------------------
    def _ind_daily_report_completion(self, kg_ids, start, end):
        # Denominator is expected child-days (eligible active-enrolment days on
        # working days), NOT the count of existing report rows — missing reports
        # must lower completion rather than disappear from the denominator.
        expected, expected_by_child = self._expected_child_days(kg_ids, start, end)
        child_ids = list(expected_by_child.keys())
        completed = 0
        if child_ids:
            completed = _safe_int(
                self.db.query(func.count(models.DailyReport.id))
                .filter(
                    models.DailyReport.child_id.in_(child_ids),
                    models.DailyReport.date >= start,
                    models.DailyReport.date <= end,
                    models.DailyReport.status.in_(
                        [
                            models.DailyReportStatus.APPROVED,
                            models.DailyReportStatus.SENT_TO_PARENT,
                        ]
                    ),
                )
                .scalar()
            )
        pct = _safe_pct(completed, expected) if expected else None
        return {
            "kpi": self._kpi("daily_report_completion", "معدل إنجاز التقارير اليومية", pct, "%"),
            "rows": [
                {
                    "المؤشر": "إنجاز التقارير اليومية",
                    "التقارير المتوقعة": expected,
                    "المكتملة": completed,
                    "النسبة %": (pct if pct is not None else "—"),
                }
            ],
            "note": ("لا توجد تقارير متوقعة ضمن النطاق (لا يوجد تسجيل نشط أو أيام دوام)." if not expected else None),
        }

    def _ind_late_reports(self, kg_ids, start, end):
        q = self.db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= start,
            models.DailyReport.date <= end,
            models.DailyReport.submitted_at.isnot(None),
            func.date(models.DailyReport.submitted_at) > models.DailyReport.date,
        )
        if kg_ids is not None:
            q = q.filter(models.DailyReport.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {
            "kpi": self._kpi("late_reports", "التقارير المتأخرة", total, "تقرير"),
            "rows": [{"المؤشر": "التقارير المتأخرة", "القيمة": total}],
        }

    # -- safety / incidents -------------------------------------------
    def _ind_critical_incidents(self, kg_ids, start, end):
        q = self.db.query(func.count(models.Incident.id)).filter(
            models.Incident.deleted_at.is_(None) if hasattr(models.Incident, "deleted_at") else True,
            *jordan_date_range_filter(models.Incident.occurred_at, start, end),
            models.Incident.severity_level == models.SeverityLevel.CRITICAL,
        )
        if kg_ids is not None:
            q = q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {
            "kpi": self._kpi("critical_incidents", "الحوادث الحرجة", total, "حادثة"),
            "rows": [{"المؤشر": "الحوادث الحرجة", "القيمة": total}],
        }

    def _ind_incidents_by_severity(self, kg_ids, start, end):
        q = self.db.query(models.Incident.severity_level, func.count(models.Incident.id)).filter(
            *jordan_date_range_filter(models.Incident.occurred_at, start, end)
        )
        if kg_ids is not None:
            q = q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        counts = {_enum_value(s): _safe_int(c) for s, c in q.group_by(models.Incident.severity_level).all()}
        # All severity levels (zero-filled, localized), ordered low → critical.
        series = [{"label": _severity_ar(sev.value), "value": counts.get(sev.value, 0)} for sev in models.SeverityLevel]
        total = sum(s["value"] for s in series)
        # Exposure-adjusted incident rate per 1,000 attended child-days — the
        # comparable measure. Unavailable (not 0) when there is no attendance.
        _, expected_by_child = self._expected_child_days(kg_ids, start, end)
        attended = self._attended_child_days(list(expected_by_child.keys()), start, end)
        rate = round(total / attended * 1000, 3) if attended else None
        table = self._dist_rows("الحوادث حسب الخطورة", series)
        table.append(
            {
                "المؤشر": "معدل الحوادث لكل 1000 يوم حضور",
                "أيام الحضور": attended,
                "المعدل": (rate if rate is not None else "—"),
            }
        )
        return {
            "kpi": self._kpi("incidents_by_severity", "إجمالي الحوادث", total, "حادثة"),
            "chart": {"type": "bar", "title_ar": "الحوادث حسب الخطورة", "series": series},
            "rows": table,
            "note": (
                "لا توجد أيام حضور لاحتساب معدل الحوادث لكل 1000 يوم."
                if not attended
                else f"معدل الحوادث: {rate} لكل 1000 يوم حضور."
            ),
        }

    # -- staff / governance -------------------------------------------
    def _ind_staff_count(self, kg_ids, start, end):
        q = self.db.query(models.User.role, func.count(models.User.id)).filter(
            models.User.deleted_at.is_(None),
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
        )
        if kg_ids is not None:
            q = q.filter(models.User.kindergarten_id.in_(kg_ids))
        rows = dict((_enum_value(r), _safe_int(c)) for r, c in q.group_by(models.User.role).all())
        managers = rows.get("MANAGER", 0)
        supervisors = rows.get("SUPERVISOR", 0)
        return {
            "kpi": self._kpi("staff_count", "عدد الموظفين", managers + supervisors, "موظف"),
            "rows": [
                {
                    "المؤشر": "عدد الموظفين",
                    "المدراء": managers,
                    "المشرفون": supervisors,
                    "الإجمالي": managers + supervisors,
                }
            ],
        }

    def _ind_unassigned_classes(self, kg_ids, start, end):
        assigned = self.db.query(models.SupervisorAssignment.class_id).filter(
            models.SupervisorAssignment.deleted_at.is_(None)
        )
        q = self.db.query(func.count(models.Class.id)).filter(
            models.Class.is_active.is_(True), models.Class.deleted_at.is_(None), ~models.Class.id.in_(assigned)
        )
        if kg_ids is not None:
            q = q.filter(models.Class.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {
            "kpi": self._kpi("unassigned_classes", "الفصول غير المسندة لمشرف", total, "صف"),
            "rows": [{"المؤشر": "الفصول غير المسندة لمشرف", "القيمة": total}],
        }

    def _ind_unassigned_children(self, kg_ids, start, end):
        q = self.db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.class_id.is_(None),
        )
        if kg_ids is not None:
            q = q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total = _safe_int(q.scalar())
        return {
            "kpi": self._kpi("unassigned_children", "الأطفال غير المسجلين في صف", total, "طفل"),
            "rows": [{"المؤشر": "الأطفال غير المسجلين في صف", "القيمة": total}],
        }

    def _ind_data_quality_score(self, kg_ids, start, end):
        # Reporting participation: share of active nurseries with >=1 daily report
        # in the 7-day window ENDING on the report end date. The window is exactly
        # seven inclusive calendar dates (end-6 .. end), anchored to the selected
        # period end rather than "now".
        window_end = end
        window_start = end - timedelta(days=6)
        kg_q = self.db.query(models.Kindergarten.id).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_ids is not None:
            kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_ids))
        active_ids = [r[0] for r in kg_q.all()]
        total = len(active_ids)
        reported = 0
        if active_ids:
            reported = (
                self.db.query(func.count(func.distinct(models.DailyReport.kindergarten_id)))
                .filter(
                    models.DailyReport.kindergarten_id.in_(active_ids),
                    models.DailyReport.date >= window_start,
                    models.DailyReport.date <= window_end,
                )
                .scalar()
                or 0
            )
        # No active nurseries in scope -> participation is unavailable, not 0%.
        pct = _safe_pct(reported, total) if total else None
        return {
            "kpi": self._kpi("data_quality_score", "مؤشر جودة البيانات", pct, "%"),
            "rows": [
                {
                    "المؤشر": f"المشاركة في الإبلاغ ({window_start} → {window_end})",
                    "النشطة": total,
                    "المُبلِّغة": reported,
                    "النسبة %": (pct if pct is not None else "—"),
                }
            ],
            "note": ("لا توجد حضانات نشطة ضمن النطاق لاحتساب المشاركة في الإبلاغ." if total == 0 else None),
        }

    def _ind_service_access_ratio(self, kg_ids, start, end):
        children = self._child_base_query(kg_ids).count()
        kg_q = self.db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_ids is not None:
            kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_ids))
        active_kgs = _safe_int(kg_q.scalar())
        ratio = round(children / active_kgs, 2) if active_kgs else 0.0
        return {
            "kpi": self._kpi("service_access_ratio", "أطفال لكل حضانة نشطة", ratio, "طفل/حضانة"),
            "rows": [
                {"المؤشر": "أطفال لكل حضانة نشطة", "الأطفال": children, "الحضانات النشطة": active_kgs, "النسبة": ratio}
            ],
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
        status_ar = {
            "sufficient": "البيانات كافية",
            "limited": "البيانات محدودة",
            "incomplete": "البيانات غير مكتملة",
        }.get(status, status)
        return f"{head} أبرز المؤشرات: {highlights}. حالة البيانات: {status_ar}."
