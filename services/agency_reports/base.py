"""Abstract base class and shared helpers for per-agency report services.

Each agency (NCFA, MOE, MOH, DOS, MOL, MOSD, MOPIC) implements
``AbstractAgencyReportService``.  The registry in ``registry.py`` resolves an
``agency_code`` to its service class.

Shared helpers (localization maps, enum coercion, period resolution) live here
so every agency service reuses the same definitions — eliminating the
duplication that existed when all agencies shared one 4 000-line file.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from agency_reports_registry import SENSITIVE_FIELD_DENYLIST
from config import settings
from services.jordan_locations import governorate_filter
from utils.time_utils import jordan_date_range_filter

_JORDAN_TZ = timezone(timedelta(hours=3))


# ---------------------------------------------------------------------------
# Shared localization maps (used by every agency service)
# ---------------------------------------------------------------------------

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

_SEVERITY_COLOR = {
    "LOW": "#22c55e",
    "MEDIUM": "#f59e0b",
    "HIGH": "#f97316",
    "CRITICAL": "#dc2626",
    "UNKNOWN": "#64748b",
}

_QUARTER_AR = {
    "Q1": "الربع الأول",
    "Q2": "الربع الثاني",
    "Q3": "الربع الثالث",
    "Q4": "الربع الرابع",
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
    """Case-insensitively coerce a filter string to an enum member, or None."""
    if value in (None, "", "null", "undefined"):
        return None
    try:
        return enum_cls(str(value).upper())
    except ValueError:
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den) * 100.0), 2) if den else 0.0


_DOS_PERIOD_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "half_year": 180,
    "year": 365,
}


def _resolve_dos_period(filters: dict[str, Any]) -> tuple[date, date]:
    """Resolve period/date_from/date_to to an inclusive (start, end) range."""
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


def _age_months(dob: date, ref: date) -> int:
    """Full calendar months between dob and ref."""
    return (ref.year - dob.year) * 12 + (ref.month - dob.month) - (1 if ref.day < dob.day else 0)


def _date_plus_months(d: date, months: int) -> date:
    """Add/subtract calendar months, clamping day."""
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _min_cell_size() -> int:
    try:
        return max(0, int(settings.AGENCY_REPORT_MIN_CELL_SIZE))
    except (TypeError, ValueError):
        return 5


# ---------------------------------------------------------------------------
# Shared label maps (Arabic + English)
# ---------------------------------------------------------------------------

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

_SOURCE_EN = {
    "Child": "Children Registry",
    "ParentProfile": "Parent Profiles",
    "EnrollmentApplication": "Enrollment Records",
    "Kindergarten": "Kindergarten Registry",
    "Class": "Class Records",
    "Incident": "Incident and Safety Records",
    "AttendanceLog": "Attendance Records",
    "DailyReport": "Daily Reports",
    "User": "Workforce (Users) Registry",
    "AbsenceRequest": "Absence Requests",
    "StaffTrainingCompletion": "Training Completion Records",
    "Message": "Messaging Records",
    "NationalImmunizationSchedule": "National Immunization Schedule",
    "ChildVaccinationRecord": "Child Vaccination Record",
    "AbsenceReasonCategory": "Absence Reason Categories",
    "OperatingCalendar": "Operating Calendar",
    "SupervisorAssignment": "Supervisor Assignment Records",
    "StaffTraining": "Training Programs",
}


def _sources_ar(models_list: list[str]) -> str:
    names = [_SOURCE_AR.get(m, m) for m in (models_list or [])]
    return "، ".join(dict.fromkeys(names)) if names else "منصة KinJo"


def _sources_en(models_list: list[str]) -> str:
    names = [_SOURCE_EN.get(m, m) for m in (models_list or [])]
    return ", ".join(dict.fromkeys(names)) if names else "KinJo Platform"


_GEO_BASIS_AR = {
    "parent_residence": "حسب سكن ولي الأمر",
    "kindergarten_location": "حسب موقع الحضانة",
}

_GEO_BASIS_EN = {
    "parent_residence": "by parent residence",
    "kindergarten_location": "by kindergarten location",
}


def _is_rate_key(key: Any) -> bool:
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


def _build_chart(breakdowns: list[dict[str, Any]], value_col: str | None, title_ar: str | None, title_en: str | None = None) -> dict[str, Any] | None:
    if not breakdowns or not value_col:
        return None
    keys = list(breakdowns[0].keys())

    def _num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

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
    return {"type": "bar", "title_ar": title_ar, "title_en": title_en, "series": series[:15], "group_by": group_col}


def _finalize_breakdowns(breakdowns: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
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
        non_rate_numeric = [k for k in keys if k in numeric and not _is_rate_key(k)]
        value_col = non_rate_numeric[-1] if non_rate_numeric else (keys[-1] if keys else None)

    label_col = keys[0]
    total_row: dict[str, Any] = {}
    for k in breakdowns[0].keys():
        if k == label_col:
            total_row[k] = {"ar": "المجموع", "en": "Total"}
        elif k == "النسبة %":
            total_row[k] = 100.0
        elif _is_rate_key(k):
            total_row[k] = "—"
        elif k in numeric:
            total_row[k] = sum(_safe_int(b.get(k)) for b in breakdowns)
        else:
            total_row[k] = ""
    return value_col, total_row


class AgencyReportError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AbstractAgencyReportService(ABC):
    """Abstract base for per-agency report services.

    Each subclass owns the computation for its agency's reports.  Shared
    helpers (geo filtering, metadata, payload assembly, privacy assertion)
    are provided here so every agency produces the same payload shape.
    """

    agency_code: str = ""

    def __init__(self, db: Session):
        self.db = db
        self._expected_cache: dict[Any, tuple[int, dict[int, int]]] = {}

    @abstractmethod
    def list_reports(self) -> list[dict[str, Any]]:
        """Return the list of report definitions for this agency."""

    @abstractmethod
    def compute_report(
        self, report_code: str, filters: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute a single report and return the payload dict."""

    def export_report(
        self, report_code: str, filters: dict[str, Any], fmt: str = "csv"
    ) -> bytes:
        """Export a report in the given format.  Default delegates to the
        shared exporter; agencies may override for custom export logic."""
        from services.agency_reports.exporter import to_csv

        payload = self.compute_report(report_code, filters)
        if fmt == "json":
            import json
            return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        return to_csv(payload)

    # ------------------------------------------------------------------
    # Shared helpers (moved verbatim from the monolith)
    # ------------------------------------------------------------------

    def _agency(self) -> dict[str, Any]:
        from agency_reports_registry import AGENCY_REPORT_REGISTRY
        agency = AGENCY_REPORT_REGISTRY.get(self.agency_code)
        if not agency:
            raise AgencyReportError(404, "Agency not found")
        return agency

    def _report(self, report_code: str) -> dict[str, Any]:
        report = self._agency()["reports"].get(report_code)
        if not report:
            raise AgencyReportError(404, "Report not found")
        return report

    def _clean_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        cleaned = {k: v for k, v in filters.items() if v not in (None, "", "null", "undefined")}
        gov = cleaned.get("governorate")
        if isinstance(gov, str):
            aliases = settings.JORDAN_GOVERNORATE_ALIASES
            cleaned["governorate"] = aliases.get(gov) or aliases.get(gov.lower(), gov)
        return cleaned

    def _metadata(
        self,
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        status: str = "ready",
    ) -> dict[str, Any]:
        agency = self._agency()
        return {
            "agency_code": self.agency_code,
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
            "data_source_ar": _sources_ar(report.get("data_sources", [])),
            "data_source_en": _sources_en(report.get("data_sources", [])),
            "geography_basis_ar": _GEO_BASIS_AR.get(
                filters.get("geography_basis") or report.get("default_geography_basis", ""), ""
            ),
            "geography_basis_en": _GEO_BASIS_EN.get(
                filters.get("geography_basis") or report.get("default_geography_basis", ""), ""
            ),
            "definition_ar": report.get("description_ar"),
            "definition_en": report.get("description_en"),
            "units_note_ar": "الأعداد بالأرقام المطلقة، والنسب بالنسبة المئوية (%).",
            "units_note_en": "Counts are absolute numbers; ratios are percentages (%).",
            "symbols_note_ar": "«—» تعني غير متوفر أو لا ينطبق · «0» تعني لا يوجد (صفر فعلي).",
            "symbols_note_en": "'—' means not available or not applicable; '0' means none (actual zero).",
            "excluded_sensitive_fields": sorted(SENSITIVE_FIELD_DENYLIST),
            "limitations": [],
            "accessibility_status": "wcag_2_1_aa_review_required",
        }

    def _payload(
        self,
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        summary: dict[str, Any],
        breakdowns: list[dict[str, Any]],
        chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        value_col, total_row = _finalize_breakdowns(breakdowns)
        table = {"caption_ar": report.get("title_ar"), "caption_en": report.get("title_en"), "rows": breakdowns, "total_row": total_row}

        if chart is None and breakdowns and value_col:
            chart = _build_chart(breakdowns, value_col, report.get("title_ar"), report.get("title_en"))

        payload = {
            "metadata": self._metadata(report_code, report, filters),
            "summary": summary,
            "summary_labels": _label_map(summary.keys()),
            "column_labels": _label_map(breakdowns[0].keys() if breakdowns else []),
            "breakdowns": breakdowns,
            "total_row": total_row,
            "tables": [table],
            "unavailable_indicators": [],
            "exports": {"csv": "csv" in report.get("exports", []), "json": "json" in report.get("exports", [])},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
            "privacy_notice_en": "This report displays aggregated data only and contains no personal or sensitive data.",
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

    def _unavailable_payload(
        self,
        report_code: str,
        report: dict[str, Any],
        filters: dict[str, Any],
        status: str | None = None,
    ) -> dict[str, Any]:
        status = status or report.get("status", "requires_structured_data")
        return {
            "metadata": self._metadata(report_code, report, filters, status=status),
            "summary": {"status": status, "message_ar": report.get("reason_ar") or "هذا التقرير غير متاح حاليًا."},
            "breakdowns": [],
            "charts": [],
            "tables": [],
            "unavailable_indicators": [{"code": report_code, "status": status, "message_ar": report.get("reason_ar")}],
            "exports": {"csv": False, "json": True},
            "privacy_notice_ar": "يعرض هذا التقرير بيانات تجميعية فقط ولا يتضمن أي بيانات شخصية أو حساسة.",
            "privacy_notice_en": "This report displays aggregated data only and contains no personal or sensitive data.",
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

    # ------------------------------------------------------------------
    # Expected child-days computation (shared by attendance/incident reports)
    # ------------------------------------------------------------------

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
        from sqlalchemy import or_
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

    def _custom_kg_ids(self, filters: dict[str, Any]) -> list[int] | None:
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


# ---------------------------------------------------------------------------
# Shared field-label maps (Arabic + English) for summary/column keys
# ---------------------------------------------------------------------------

from services.agency_reports.labels import _FIELD_LABELS, _FIELD_LABELS_EN


def _label_map(keys) -> dict[str, dict[str, str]]:
    return {k: {"ar": _FIELD_LABELS.get(k, k), "en": _FIELD_LABELS_EN.get(k, k)} for k in keys}
