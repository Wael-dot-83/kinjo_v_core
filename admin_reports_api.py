from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import csv
import io
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import models
from admin_security import log_audit_event, validation_error, not_found_error
from audit_actions import AuditAction
from child_age_policy import calculate_age_days, calculate_age_months
from database import get_db
from export_service import export_service
from dependencies import require_admin
from validators import calculate_required_supervisors
from config import settings
from services.jordan_locations import governorate_filter
from services.admin.reports.scoring import (
    calculate_compliance_score,
    calculate_data_quality_score,
    calculate_risk_score,
    rank_kindergartens_by_risk,
)

from pydantic import BaseModel, Field
from typing import List
from fastapi import Request, Form
from fastapi.responses import JSONResponse
from rate_limiter import limiter
import logging

# Canonical age bucket labels - single source of truth (CHART-011)
AGE_BUCKET_LABELS = {
    "B1": {"ar": "يوم إلى 3 أشهر", "en": "1 day to 3 months"},
    "B2": {"ar": "3 إلى 6 أشهر", "en": "3 to 6 months"},
    "B3": {"ar": "6 إلى 9 أشهر", "en": "6 to 9 months"},
    "B4": {"ar": "9 إلى 12 شهر", "en": "9 to 12 months"},
    "B5": {"ar": "12 إلى 15 شهر", "en": "12 to 15 months"},
    "B6": {"ar": "15 إلى 18 شهر", "en": "15 to 18 months"},
    "B7": {"ar": "18 إلى 21 شهر", "en": "18 to 21 months"},
    "B8": {"ar": "21 إلى 24 شهر", "en": "21 to 24 months"},
    "B9": {"ar": "24 إلى 27 شهر", "en": "24 to 27 months"},
    "B10": {"ar": "27 إلى 30 شهر", "en": "27 to 30 months"},
    "B11": {"ar": "30 إلى 33 شهر", "en": "30 to 33 months"},
    "B12": {"ar": "33 إلى 36 شهر", "en": "33 to 36 months"},
    "B13": {"ar": "36 إلى 39 شهر", "en": "36 to 39 months"},
    "B14": {"ar": "39 إلى 42 شهر", "en": "39 to 42 months"},
    "B15": {"ar": "42 إلى 45 شهر", "en": "42 to 45 months"},
    "B16": {"ar": "45 إلى 48 شهر", "en": "45 to 48 months"},
    "B17": {"ar": "48 إلى 51 شهر", "en": "48 to 51 months"},
    "B18": {"ar": "51 إلى 54 شهر", "en": "51 to 54 months"},
    "B19": {"ar": "54 إلى 57 شهر", "en": "54 to 57 months"},
}
logger = logging.getLogger(__name__)
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from admin_security import get_correlation_id


router = APIRouter(prefix="/reports", tags=["Admin Reports"])

_JORDAN_TZ = timezone(timedelta(hours=3))
_ACTIVE_STATUSES = {models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.ACCEPTED}


class ReportLevel(str, Enum):
    JORDAN = "jordan"
    GOVERNORATE = "governorate"
    CITY = "city"
    DISTRICT = "district"
    AREA = "area"
    KINDERGARTEN = "kindergarten"
    CLASS = "class"


@dataclass
class ScopeFilters:
    level: ReportLevel
    governorate: Optional[str]
    city: Optional[str]
    area: Optional[str]
    kindergarten_id: Optional[int]
    class_id: Optional[int]


def _today() -> date:
    return datetime.now(_JORDAN_TZ).date()


def _pct(num: float, den: float) -> float:
    if not den:
        return 0.0
    return round((float(num) / float(den)) * 100.0, 2)


def _safe_div(num: float, den: float) -> float:
    if not den:
        return 0.0
    return round(float(num) / float(den), 2)


def _resolve_dates(
    date_from: Optional[date],
    date_to: Optional[date],
    period: Optional[str],
) -> tuple[date, date]:
    today = _today()
    if date_from and date_to:
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must be <= date_to")
        return date_from, date_to

    p = (period or "this_month").lower().strip()
    if p == "today":
        return today, today
    if p == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if p == "this_month":
        start = date(today.year, today.month, 1)
        return start, today
    if p == "this_semester":
        # Jordan academic calendar: 1st semester Sep–Jan, 2nd semester Feb–Jun
        m = today.month
        if m >= 9:
            start = date(today.year, 9, 1)  # Sep–Dec: first semester
        elif m >= 2:
            start = date(today.year, 2, 1)  # Feb–Jun: second semester
        else:
            start = date(today.year - 1, 9, 1)  # January: still in Sep semester
        return start, today
    if p == "this_year":
        return date(today.year, 1, 1), today
    if p == "custom":
        if not (date_from and date_to):
            raise HTTPException(status_code=422, detail="custom period requires date_from and date_to")
        return date_from, date_to

    raise HTTPException(status_code=422, detail="invalid period")


def _localized(ar: str, en: str, lang: str) -> str:
    return en if lang == "en" else ar


def _prev_period(start: date, end: date) -> tuple[date, date]:
    """Return a mirror window of the same duration immediately before [start, end]."""
    days = (end - start).days + 1
    return start - timedelta(days=days), end - timedelta(days=days)


def _delta(current: float | int, previous: float | int) -> float:
    """Absolute change current − previous, rounded to 2 decimal places."""
    return round(float(current) - float(previous), 2)


def _build_scope_filters(
    level: ReportLevel,
    governorate: Optional[str],
    city: Optional[str],
    area: Optional[str],
    kindergarten_id: Optional[int],
    class_id: Optional[int],
) -> ScopeFilters:
    if level in {ReportLevel.GOVERNORATE, ReportLevel.CITY, ReportLevel.DISTRICT, ReportLevel.AREA} and not governorate:
        raise HTTPException(status_code=422, detail="governorate is required for governorate/city/district/area level")
    if level in {ReportLevel.CITY, ReportLevel.DISTRICT} and not city:
        raise HTTPException(status_code=422, detail="city is required for city/district level")
    if level == ReportLevel.AREA and not area:
        raise HTTPException(status_code=422, detail="area is required for area level")
    if level == ReportLevel.KINDERGARTEN and not kindergarten_id:
        raise HTTPException(status_code=422, detail="kindergarten_id is required for kindergarten level")
    if level == ReportLevel.CLASS and not class_id:
        raise HTTPException(status_code=422, detail="class_id is required for class level")

    return ScopeFilters(
        level=level,
        governorate=governorate,
        city=city,
        area=area,
        kindergarten_id=kindergarten_id,
        class_id=class_id,
    )


def _kg_filter_expr(filters: ScopeFilters):
    clauses = [models.Kindergarten.status == models.KindergartenStatus.ACTIVE]
    if filters.level in {
        ReportLevel.GOVERNORATE,
        ReportLevel.CITY,
        ReportLevel.DISTRICT,
        ReportLevel.AREA,
        ReportLevel.KINDERGARTEN,
        ReportLevel.CLASS,
    }:
        if filters.governorate:
            clauses.append(governorate_filter(models.Kindergarten.governorate, filters.governorate))
    if (
        filters.level
        in {ReportLevel.CITY, ReportLevel.DISTRICT, ReportLevel.AREA, ReportLevel.KINDERGARTEN, ReportLevel.CLASS}
        and filters.city
    ):
        # CHART-017: Kindergarten model uses `district` column for city filtering
        # This is a known design decision from the city→district migration (see alembic migration b2e9a2f60c27)
        clauses.append(models.Kindergarten.district == filters.city)
    if filters.level in {ReportLevel.AREA, ReportLevel.KINDERGARTEN, ReportLevel.CLASS} and filters.area:
        clauses.append(models.Kindergarten.area == filters.area)
    if filters.level == ReportLevel.KINDERGARTEN and filters.kindergarten_id:
        clauses.append(models.Kindergarten.id == filters.kindergarten_id)
    if filters.level == ReportLevel.CLASS and filters.class_id:
        clauses.append(models.Class.id == filters.class_id)
    return clauses


def _base_enrollment_query(db: Session, filters: ScopeFilters):
    q = (
        db.query(models.EnrollmentApplication)
        .execution_options(include_out_of_range_children=True)
        .join(models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id)
        .outerjoin(models.Class, models.EnrollmentApplication.class_id == models.Class.id)
        .join(models.Child, models.EnrollmentApplication.child_id == models.Child.id)
        .filter(*_kg_filter_expr(filters))
    )
    if filters.level == ReportLevel.CLASS and filters.class_id:
        q = q.filter(models.EnrollmentApplication.class_id == filters.class_id)
    return q


def _age_bucket_key(dob: Optional[date]) -> tuple[str, Optional[str]]:
    if dob is None:
        return "invalid", "missing_dob"

    today = _today()
    if dob > today:
        return "invalid", "future_dob"

    age_days = calculate_age_days(dob, today)
    age_months = calculate_age_months(dob, today)

    if age_days < 1:
        return "invalid", "too_young"
    if age_months > 57:
        return "invalid", "too_old"

    if age_months < 3:
        return "B1", None
    if age_months < 6:
        return "B2", None
    if age_months < 9:
        return "B3", None
    if age_months < 12:
        return "B4", None
    if age_months < 15:
        return "B5", None
    if age_months < 18:
        return "B6", None
    if age_months < 21:
        return "B7", None
    if age_months < 24:
        return "B8", None
    if age_months < 27:
        return "B9", None
    if age_months < 30:
        return "B10", None
    if age_months < 33:
        return "B11", None
    if age_months < 36:
        return "B12", None
    if age_months < 39:
        return "B13", None
    if age_months < 42:
        return "B14", None
    if age_months < 45:
        return "B15", None
    if age_months < 48:
        return "B16", None
    if age_months < 51:
        return "B17", None
    if age_months < 54:
        return "B18", None
    return "B19", None


def _interpret_overview(metrics: dict[str, Any], lang: str) -> dict[str, Any]:
    util = metrics.get("capacity_utilization_pct", 0)
    cps = metrics.get("children_per_supervisor", 0)

    if util >= 100 or cps > 12:
        severity = "critical"
    elif util >= 85 or cps > 8:
        severity = "warning"
    else:
        severity = "normal"

    if severity == "critical":
        action = _localized(
            "إجراء عاجل: تعزيز عدد المشرفين وتجميد التسجيل في المواقع الأعلى ضغطا.",
            "Urgent action: increase supervisor staffing and freeze enrollment in highest-pressure sites.",
            lang,
        )
    elif severity == "warning":
        action = _localized(
            "إجراء وقائي: إعادة توزيع المشرفين وفتح فصول إضافية في المناطق المزدحمة.",
            "Preventive action: rebalance supervisors and open additional classes in crowded areas.",
            lang,
        )
    else:
        action = _localized(
            "الوضع مستقر: استمر في المراقبة الأسبوعية وجودة البيانات.",
            "Stable state: continue weekly monitoring and data-quality checks.",
            lang,
        )

    summary = _localized(
        f"يظهر التقرير {metrics.get('total_children', 0)} طفلا نشطا عبر {metrics.get('total_kindergartens', 0)} حضانة.",
        f"The report shows {metrics.get('total_children', 0)} active children across {metrics.get('total_kindergartens', 0)} kindergartens.",
        lang,
    )
    return {
        "summary": summary,
        "severity": severity,
        "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
        "recommended_action": action,
    }


class _LazyMetrics(Mapping):
    """Metrics bundle that computes each expensive section on first read.

    ADMIN-SCORING (Phase 2): _collect_core_metrics used to run every query and
    every rollup for every caller, so an endpoint that only wants age buckets
    still paid for the duplicate-children scan, the daily-report recency probe
    and three geography rollups.

    Reads look exactly like the dict this replaced -- ``metrics["key"]`` -- so
    no caller changes. Deferred sections are memoized, so two reads of the same
    key cost one computation, and sections that share work read each other
    through this same mapping rather than recomputing.
    """

    __slots__ = ("_values", "_thunks")

    def __init__(self, values: dict[str, Any], thunks: dict[str, Any]):
        self._values = values
        self._thunks = thunks

    def __getitem__(self, key):
        if key in self._values:
            return self._values[key]
        thunk = self._thunks.get(key)
        if thunk is None:
            raise KeyError(key)
        value = thunk()
        self._values[key] = value
        return value

    def __iter__(self):
        # Iterating asks for everything, so materialise everything. Callers that
        # only read individual keys never reach this.
        return iter({**self._thunks, **self._values})

    def __len__(self):
        return len(set(self._values) | set(self._thunks))

    def __contains__(self, key):
        return key in self._values or key in self._thunks


def _collect_core_metrics(db: Session, filters: ScopeFilters, date_from: date, date_to: date) -> dict[str, Any]:
    enroll_q = _base_enrollment_query(db, filters)

    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()

    child_ids = {r.child_id for r in official_rows}
    official_children = (
        db.query(models.Child)
        .execution_options(include_out_of_range_children=True)
        .filter(models.Child.id.in_(list(child_ids)))
        .all()
        if child_ids
        else []
    )

    kindergartens_q = db.query(models.Kindergarten)
    if filters.governorate:
        kindergartens_q = kindergartens_q.filter(
            governorate_filter(models.Kindergarten.governorate, filters.governorate)
        )
    if filters.city:
        kindergartens_q = kindergartens_q.filter(models.Kindergarten.district == filters.city)
    if filters.area:
        kindergartens_q = kindergartens_q.filter(models.Kindergarten.area == filters.area)
    if filters.kindergarten_id:
        kindergartens_q = kindergartens_q.filter(models.Kindergarten.id == filters.kindergarten_id)
    kindergartens_q = kindergartens_q.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    kindergartens = kindergartens_q.all()
    kg_ids = [k.id for k in kindergartens]

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    if kg_ids:
        classes_q = classes_q.filter(models.Class.kindergarten_id.in_(kg_ids))
    if filters.class_id:
        classes_q = classes_q.filter(models.Class.id == filters.class_id)
    classes = classes_q.all()
    class_ids = [c.id for c in classes]

    supervisors_q = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if kg_ids:
        supervisors_q = supervisors_q.filter(models.User.kindergarten_id.in_(kg_ids))
    supervisors = supervisors_q.all()

    active_assignments_q = db.query(models.SupervisorAssignment).filter(
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
        models.SupervisorAssignment.deleted_at.is_(None),
    )
    if class_ids:
        active_assignments_q = active_assignments_q.filter(models.SupervisorAssignment.class_id.in_(class_ids))
    active_assignments = active_assignments_q.all()

    enrolled_by_class: dict[int, int] = {}
    for r in official_rows:
        if r.class_id:
            enrolled_by_class[r.class_id] = enrolled_by_class.get(r.class_id, 0) + 1

    class_supervisor_counts: dict[int, int] = {}
    for a in active_assignments:
        class_supervisor_counts[a.class_id] = class_supervisor_counts.get(a.class_id, 0) + 1

    required_supervisors = 0
    for cls in classes:
        children_in_class = enrolled_by_class.get(cls.id, 0)
        if children_in_class <= 0:
            continue
        try:
            required_supervisors += calculate_required_supervisors(str(cls.age_group), children_in_class)
        except Exception:
            required_supervisors += max(1, -(-children_in_class // 4))

    actual_supervisors = len({a.supervisor_id for a in active_assignments})

    capacity_total = sum((c.capacity_total or 0) for c in classes)
    total_children = len(child_ids)

    enrollment_status_counts: dict[str, int] = {}
    for r in all_enroll_rows:
        k = str(r.status.value if hasattr(r.status, "value") else r.status).lower()
        enrollment_status_counts[k] = enrollment_status_counts.get(k, 0) + 1

    # Age buckets and invalid-age/data issues
    age_buckets = {f"B{i}": 0 for i in range(1, 20)}
    age_invalid_reasons = {
        "missing_dob": 0,
        "future_dob": 0,
        "too_young": 0,
        "too_old": 0,
    }
    for child in official_children:
        bucket, reason = _age_bucket_key(child.date_of_birth)
        if bucket == "invalid":
            if reason:
                age_invalid_reasons[reason] += 1
        else:
            age_buckets[bucket] += 1

    gender_counts = {"male": 0, "female": 0, "unknown": 0}
    for child in official_children:
        g = (
            str(child.gender.value if hasattr(child.gender, "value") else child.gender).upper()
            if child.gender
            else "UNKNOWN"
        )
        if g == "MALE":
            gender_counts["male"] += 1
        elif g == "FEMALE":
            gender_counts["female"] += 1
        else:
            gender_counts["unknown"] += 1

    children_without_class = len({r.child_id for r in official_rows if r.class_id is None})
    children_without_kindergarten = sum(1 for r in official_rows if r.kindergarten_id is None)
    kg_missing_location = {kg.id for kg in kindergartens if not kg.governorate or not kg.district}
    children_missing_location = len({r.child_id for r in official_rows if r.kindergarten_id in kg_missing_location})

    # Per-kindergarten tallies over rows already fetched. Shared by the
    # geography rollups and the compliance counters, so they stay eager.
    supervisor_counts_by_kg: dict[int, int] = {}
    for sup_user in supervisors:
        if sup_user.kindergarten_id:
            supervisor_counts_by_kg[sup_user.kindergarten_id] = (
                supervisor_counts_by_kg.get(sup_user.kindergarten_id, 0) + 1
            )

    children_by_kg: dict[int, int] = {}
    for row in official_rows:
        if row.kindergarten_id:
            children_by_kg[row.kindergarten_id] = children_by_kg.get(row.kindergarten_id, 0) + 1

    def _geography():
        """Roll kindergartens/children/supervisors up by governorate, city and area.

        Pure Python over rows already fetched, but it walks every row several
        times; only the geography, risk and overview endpoints read it.
        """
        # Geography aggregations
        by_governorate: dict[str, dict[str, Any]] = {}
        by_city: dict[tuple[str, str], dict[str, Any]] = {}
        by_area: dict[tuple[str, str, str], dict[str, Any]] = {}
        for kg in kindergartens:
            gov = kg.governorate or "Unknown"
            city = kg.district or "Unknown"
            area = kg.area or "Unknown"
            if gov not in by_governorate:
                by_governorate[gov] = {
                    "governorate": gov,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                }
            key = (gov, city)
            if key not in by_city:
                by_city[key] = {
                    "governorate": gov,
                    "city": city,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                }
            area_key = (gov, city, area)
            if area_key not in by_area:
                by_area[area_key] = {
                    "governorate": gov,
                    "city": city,
                    "area": area,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                }

            by_governorate[gov]["kindergarten_count"] += 1
            by_city[key]["kindergarten_count"] += 1
            by_area[area_key]["kindergarten_count"] += 1

        kg_id_map = {k.id: k for k in kindergartens}
        kg_class_counts: dict[int, int] = {}
        for c in classes:
            kg_class_counts[c.kindergarten_id] = kg_class_counts.get(c.kindergarten_id, 0) + 1
            parent_kg = kg_id_map.get(c.kindergarten_id)
            gov = (parent_kg.governorate if parent_kg else None) or "Unknown"
            city = (parent_kg.district if parent_kg else None) or "Unknown"
            area = (parent_kg.area if parent_kg else None) or "Unknown"

            by_governorate.setdefault(
                gov,
                {
                    "governorate": gov,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                },
            )
            by_governorate[gov]["class_count"] += 1
            by_governorate[gov]["capacity"] += c.capacity_total or 0

            city_key = (gov, city)
            by_city.setdefault(
                city_key,
                {
                    "governorate": gov,
                    "city": city,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                },
            )
            by_city[city_key]["class_count"] += 1
            by_city[city_key]["capacity"] += c.capacity_total or 0

            area_key = (gov, city, area)
            by_area.setdefault(
                area_key,
                {
                    "governorate": gov,
                    "city": city,
                    "area": area,
                    "kindergarten_count": 0,
                    "class_count": 0,
                    "children_count": 0,
                    "supervisor_count": 0,
                    "capacity": 0,
                },
            )
            by_area[area_key]["class_count"] += 1
            by_area[area_key]["capacity"] += c.capacity_total or 0

        for row in official_rows:
            kg_id = row.kindergarten_id
            kg = kg_id_map.get(kg_id)
            if not kg:
                continue
            gov = kg.governorate or "Unknown"
            city = kg.district or "Unknown"
            area = kg.area or "Unknown"
            by_governorate[gov]["children_count"] += 1
            by_city[(gov, city)]["children_count"] += 1
            by_area[(gov, city, area)]["children_count"] += 1

        for kg in kindergartens:
            gov = kg.governorate or "Unknown"
            city = kg.district or "Unknown"
            area = kg.area or "Unknown"
            sup = supervisor_counts_by_kg.get(kg.id, 0)
            by_governorate[gov]["supervisor_count"] += sup
            by_city[(gov, city)]["supervisor_count"] += sup
            by_area[(gov, city, area)]["supervisor_count"] += sup

        return {
            "by_governorate": list(by_governorate.values()),
            "by_city": list(by_city.values()),
            "by_area": list(by_area.values()),
        }

    # Data quality and compliance issue counters.
    # Each of these is a standalone round trip, so it is deferred: an endpoint
    # that never reads a compliance or quality figure never issues the query.
    def _duplicate_children():
        return (
            db.query(func.count())
            .select_from(
                db.query(
                    models.Child.first_name,
                    models.Child.last_name,
                    models.Child.date_of_birth,
                    func.count(models.Child.id).label("cnt"),
                )
                .group_by(models.Child.first_name, models.Child.last_name, models.Child.date_of_birth)
                .having(func.count(models.Child.id) > 1)
                .subquery()
            )
            .scalar()
            or 0
        )

    def _children_in_multiple_classes():
        """Children enrolled in more than one class at once (a violation)."""
        multi_class_sq = (
            db.query(models.EnrollmentApplication.child_id)
            .filter(
                models.EnrollmentApplication.child_id.in_(list(child_ids)),
                models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)),
                models.EnrollmentApplication.class_id.isnot(None),
            )
            .group_by(models.EnrollmentApplication.child_id)
            .having(func.count(func.distinct(models.EnrollmentApplication.class_id)) > 1)
            .subquery()
        )
        return db.query(func.count()).select_from(multi_class_sq).scalar() or 0

    classes_without_supervisor = sum(1 for c in classes if class_supervisor_counts.get(c.id, 0) == 0)
    classes_with_children_no_supervisor = sum(
        1 for c in classes if enrolled_by_class.get(c.id, 0) > 0 and class_supervisor_counts.get(c.id, 0) == 0
    )
    kindergartens_no_supervisor_with_children = 0
    kindergartens_over_capacity = 0
    kindergartens_missing_coordinates = 0
    kindergartens_missing_capacity = 0

    for kg in kindergartens:
        children_kg = children_by_kg.get(kg.id, 0)
        supervisors_kg = supervisor_counts_by_kg.get(kg.id, 0)
        classes_kg = [c for c in classes if c.kindergarten_id == kg.id]
        cap_kg = sum((c.capacity_total or 0) for c in classes_kg)

        if children_kg > 0 and supervisors_kg == 0:
            kindergartens_no_supervisor_with_children += 1
        if cap_kg <= 0:
            if children_kg > 0:
                kindergartens_missing_capacity += 1
        elif children_kg > cap_kg:
            kindergartens_over_capacity += 1

        if kg.latitude is None or kg.longitude is None:
            kindergartens_missing_coordinates += 1

    # ADMIN-SCORING-001: violations keyed to VIOLATION_RULES so each type is
    # deducted at its own severity weight. The previous formula summed the
    # counts and divided by (children + kindergartens + classes), which let a
    # large network dilute an unsupervised class to a rounding error.
    active_kg_count = len(kindergartens)

    def _compliance_violations():
        return {
            "invalid_age_too_young": age_invalid_reasons["too_young"],
            "invalid_age_too_old": age_invalid_reasons["too_old"],
            "future_dob": age_invalid_reasons["future_dob"],
            "missing_dob": age_invalid_reasons["missing_dob"],
            "class_with_children_no_supervisor": classes_with_children_no_supervisor,
            "kindergarten_no_supervisor_with_children": kindergartens_no_supervisor_with_children,
            "kindergarten_over_capacity": kindergartens_over_capacity,
            "child_in_multiple_classes": metrics["children_in_multiple_classes"],
        }

    def _compliance():
        return calculate_compliance_score(metrics["compliance_violations"])

    def _kg_with_recent_report():
        if active_kg_count <= 0 or not kg_ids:
            return 0
        return (
            db.query(func.count(func.distinct(models.DailyReport.kindergarten_id)))
            .filter(
                models.DailyReport.kindergarten_id.in_(kg_ids),
                models.DailyReport.date >= _today() - timedelta(days=7),
            )
            .scalar()
            or 0
        )

    def _data_quality():
        """ADMIN-SCORING-002: four weighted dimensions, not a filing rate.

        Completeness is measured over the four child fields already counted in
        the eager pass -- date of birth, gender, kindergarten assignment and
        class assignment -- so the dimension adds no queries (mandate 4).
        """
        fields_per_child = 4
        total_fields_required = total_children * fields_per_child
        missing_fields = (
            age_invalid_reasons["missing_dob"]
            + gender_counts["unknown"]
            + children_without_kindergarten
            + children_without_class
        )
        total_fields_filled = max(0, total_fields_required - missing_fields)

        return calculate_data_quality_score(
            total_children=total_children,
            missing_dob_count=age_invalid_reasons["missing_dob"],
            missing_gender_count=gender_counts["unknown"],
            invalid_age_count=age_invalid_reasons["too_young"] + age_invalid_reasons["too_old"],
            duplicate_count=metrics["duplicate_children"],
            total_enrollments=sum(enrollment_status_counts.values()),
            active_kg_count=active_kg_count,
            kg_with_recent_report=metrics["kg_with_recent_report"],
            total_fields_required=total_fields_required,
            total_fields_filled=total_fields_filled,
        )

    eager = {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "total_children": total_children,
        "total_kindergartens": len(kindergartens),
        "total_supervisors": len(supervisors),
        "total_classes": len(classes),
        "children_per_kindergarten": _safe_div(total_children, len(kindergartens)),
        "children_per_supervisor": _safe_div(total_children, actual_supervisors),
        "children_per_class": _safe_div(total_children, len(classes)),
        "required_supervisors": required_supervisors,
        "actual_supervisors": actual_supervisors,
        "supervisor_gap": max(0, required_supervisors - actual_supervisors),
        "capacity_total": capacity_total,
        "capacity_utilization_pct": _pct(total_children, capacity_total),
        "enrollment_status_counts": enrollment_status_counts,
        "age_buckets": age_buckets,
        "age_invalid_reasons": age_invalid_reasons,
        "gender_counts": gender_counts,
        "children_without_kindergarten": children_without_kindergarten,
        "children_without_class": children_without_class,
        "children_missing_location": children_missing_location,
        "classes_without_supervisor": classes_without_supervisor,
        "classes_with_children_no_supervisor": classes_with_children_no_supervisor,
        "kindergartens_no_supervisor_with_children": kindergartens_no_supervisor_with_children,
        "kindergartens_over_capacity": kindergartens_over_capacity,
        "kindergartens_missing_coordinates": kindergartens_missing_coordinates,
        "kindergartens_missing_capacity": kindergartens_missing_capacity,
    }

    # Deferred sections: each is a standalone query or a multi-pass rollup, and
    # most endpoints read only a few of them. The mapping memoizes on first
    # read, so a caller that does want everything pays exactly what the old
    # eager version cost.
    deferred = {
        "duplicate_children": _duplicate_children,
        "children_in_multiple_classes": _children_in_multiple_classes,
        "kg_with_recent_report": _kg_with_recent_report,
        "compliance_violations": _compliance_violations,
        "compliance": _compliance,
        "compliance_score": lambda: metrics["compliance"]["score"],
        "data_quality": _data_quality,
        "data_quality_score": lambda: metrics["data_quality"]["overall_score"],
        "by_governorate": lambda: metrics["_geography"]["by_governorate"],
        "by_city": lambda: metrics["_geography"]["by_city"],
        "by_area": lambda: metrics["_geography"]["by_area"],
        "_geography": _geography,
    }

    metrics = _LazyMetrics(eager, deferred)
    return metrics


def _risk_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank the in-scope cities by risk (ADMIN-SCORING-003).

    Two changes from the previous implementation:

    * The raw score is the composite pressure score from the scoring module
      (capacity 0.4, staffing 0.4, unsupervised classes 0.2) instead of a
      ladder of hand-picked increments.
    * The band is a percentile against the population in scope, not an
      absolute cut-off. The old thresholds (>=60 critical, >=35 warning)
      reported nothing at risk in a uniformly healthy network and everything
      critical in a stressed one; percentile bands always surface the worst
      10%, which is what an inspection schedule actually needs.

    CHART-018: still aggregated at city level. Kindergarten-level ranking
    needs per-facility coordinates and class rollups that this metrics bundle
    does not carry.
    """
    rows: list[dict[str, Any]] = []
    for row in metrics.get("by_city", []):
        children = row.get("children_count", 0)
        supervisors = row.get("supervisor_count", 0)
        capacity = row.get("capacity", 0)
        class_count = row.get("class_count", 0)

        cps = _safe_div(children, supervisors)
        cap_util = _pct(children, capacity)

        # Same 1-supervisor-per-4-children ratio the class-level requirement
        # uses in _collect_core_metrics, applied to the city total.
        required_supervisors = -(-children // 4) if children > 0 else 0
        supervisor_gap = max(0, required_supervisors - supervisors)

        # A city with children but no classes on record has, in effect, all of
        # its children in unsupervised arrangements.
        classes_without_supervisor = 1 if (class_count == 0 and children > 0) else 0

        raw_score = calculate_risk_score(
            capacity_utilization_pct=cap_util,
            supervisor_gap=supervisor_gap,
            children_count=children,
            has_missing_capacity=(capacity <= 0 and children > 0),
            has_missing_coordinates=False,
            classes_without_supervisor=classes_without_supervisor,
        )

        rows.append(
            {
                "governorate": row.get("governorate"),
                "city": row.get("city"),
                "id": f"{row.get('governorate')}/{row.get('city')}",
                "raw_score": raw_score,
                "risk_score": raw_score,
                "children_per_supervisor": cps,
                "capacity_utilization_pct": cap_util,
                "supervisor_gap": supervisor_gap,
            }
        )

    return rank_kindergartens_by_risk(rows)


def _classify_kindergarten(
    children_count: int,
    supervisors_count: int,
    classes_count: int,
    capacity: int,
    has_supervisor: bool,
    has_children: bool,
    children_per_supervisor: float,
    capacity_utilization_pct: float,
    children_per_class: float,
) -> str:
    if not has_children and not has_supervisor:
        return "inactive"
    if has_supervisor and not has_children:
        return "resource_underuse"
    if has_children and not has_supervisor:
        return "critical_risk"
    if children_per_supervisor > 12:
        return "under_supervised"
    if children_per_class > 0 and children_per_class > 20:
        return "capacity_class_pressure"
    if capacity_utilization_pct > 100:
        return "over_capacity"
    if has_children and classes_count == 0:
        return "operational_issue"
    return "normal"


def _kindergarten_detail_rows(
    db: Session,
    filters: ScopeFilters,
    official_children_ids: set[int],
    official_enrollments: list[models.EnrollmentApplication],
    classes: list[models.Class],
    supervisors: list[models.User],
    active_assignments: list[models.SupervisorAssignment],
) -> list[dict[str, Any]]:
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(governorate_filter(models.Kindergarten.governorate, filters.governorate))
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
    if filters.kindergarten_id:
        kg_q = kg_q.filter(models.Kindergarten.id == filters.kindergarten_id)
    kindergartens = kg_q.all()
    kg_map = {k.id: k for k in kindergartens}

    rows: list[dict[str, Any]] = []
    for kg_id, kg in kg_map.items():
        kg_classes = [c for c in classes if c.kindergarten_id == kg_id]
        kg_enrollments = [e for e in official_enrollments if e.kindergarten_id == kg_id]
        kg_class_ids = {c.id for c in kg_classes}
        kg_active_assignments = [a for a in active_assignments if a.class_id in kg_class_ids]
        active_sup_count = len({a.supervisor_id for a in kg_active_assignments})
        children_count = len({e.child_id for e in kg_enrollments})
        capacity = sum(c.capacity_total or 0 for c in kg_classes)
        cps = _safe_div(children_count, active_sup_count)
        cap_util = _pct(children_count, capacity)
        enrolled_by_class = {}
        for e in kg_enrollments:
            if e.class_id:
                enrolled_by_class[e.class_id] = enrolled_by_class.get(e.class_id, 0) + 1
        required_sup = 0
        for c in kg_classes:
            children_in_class = enrolled_by_class.get(c.id, 0)
            if children_in_class > 0:
                try:
                    required_sup += calculate_required_supervisors(str(c.age_group), children_in_class)
                except Exception:
                    required_sup += 1
        children_per_class = _safe_div(children_count, len(kg_classes))
        classification = _classify_kindergarten(
            children_count=children_count,
            supervisors_count=active_sup_count,
            classes_count=len(kg_classes),
            capacity=capacity,
            has_supervisor=active_sup_count > 0,
            has_children=children_count > 0,
            children_per_supervisor=cps,
            capacity_utilization_pct=cap_util,
            children_per_class=children_per_class,
        )
        over_capacity = capacity > 0 and children_count > capacity
        missing_capacity = capacity <= 0 and children_count > 0
        no_supervisor_with_children = children_count > 0 and active_sup_count == 0
        classes_without_supervisor = sum(
            1
            for c in kg_classes
            if enrolled_by_class.get(c.id, 0) > 0 and all(a.class_id != c.id for a in kg_active_assignments)
        )
        data_issues = []
        if missing_capacity:
            data_issues.append("missing_capacity")
        if kg.latitude is None or kg.longitude is None:
            data_issues.append("missing_coordinates")
        if children_count == 0 and active_sup_count > 0:
            data_issues.append("underuse")
        if no_supervisor_with_children:
            data_issues.append("no_supervisor")
        if over_capacity:
            data_issues.append("over_capacity")
        if classes_without_supervisor > 0:
            data_issues.append("class_without_supervisor")

        if classification == "critical_risk" or over_capacity or missing_capacity:
            risk_status = "critical"
        elif classification == "under_supervised" or classes_without_supervisor > 0:
            risk_status = "warning"
        else:
            risk_status = "normal"

        if classification == "over_capacity" or no_supervisor_with_children:
            recommended_action_ar = "إجراء عاجل: خفض الاستيعاب أو تعيين مشرف فورا."
            recommended_action_en = "Urgent: reduce enrollment or assign a supervisor immediately."
        elif classification == "under_supervised":
            recommended_action_ar = "إجراء وقائي: تعزيز المشرفين في الموقع."
            recommended_action_en = "Preventive: reinforce supervisors at this site."
        elif classification == "inactive":
            recommended_action_ar = "تحقق من حالة العمل وتفعيل الحضانة أو إيقافها رسميا."
            recommended_action_en = "Verify operational status and activate or formally close."
        elif classification == "resource_underuse":
            recommended_action_ar = "استخدم الموارد بشكل أفضل أو أعد توزيعها."
            recommended_action_en = "Better utilize resources or redistribute them."
        else:
            recommended_action_ar = "الوضع مستقر: استمر في المراقبة."
            recommended_action_en = "Stable: continue monitoring."

        rows.append(
            {
                "id": kg.id,
                "name_ar": kg.name_ar,
                "name_en": kg.name_en,
                "governorate": kg.governorate,
                "city": kg.district,
                "children_count": children_count,
                "supervisors_count": active_sup_count,
                "classes_count": len(kg_classes),
                "capacity": capacity,
                "capacity_utilization_pct": cap_util,
                "children_per_supervisor": cps,
                "children_per_class": children_per_class,
                "required_supervisors": required_sup,
                "supervisor_gap": max(0, required_sup - active_sup_count),
                "over_capacity": over_capacity,
                "missing_capacity": missing_capacity,
                "no_supervisor_with_children": no_supervisor_with_children,
                "classes_without_supervisor": classes_without_supervisor,
                "classification": classification,
                "risk_status": risk_status,
                "data_issues": data_issues,
                "recommended_action_ar": recommended_action_ar,
                "recommended_action_en": recommended_action_en,
            }
        )
    rows.sort(
        key=lambda x: ({"critical": 0, "warning": 1, "normal": 2}.get(x["risk_status"], 3), -x.get("risk_score", 0))
    )
    return rows


def _class_detail_rows(
    db: Session,
    filters: ScopeFilters,
    official_enrollments: list[models.EnrollmentApplication],
    supervisors: list[models.User],
    active_assignments: list[models.SupervisorAssignment],
) -> list[dict[str, Any]]:
    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    if filters.kindergarten_id:
        classes_q = classes_q.filter(models.Class.kindergarten_id == filters.kindergarten_id)
    if filters.class_id:
        classes_q = classes_q.filter(models.Class.id == filters.class_id)
    classes = classes_q.all()

    needed_kg_ids = {cls.kindergarten_id for cls in classes if cls.kindergarten_id}
    kg_map: dict[int, models.Kindergarten] = {}
    if needed_kg_ids:
        kg_map = {
            k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(needed_kg_ids)).all()
        }

    rows: list[dict[str, Any]] = []
    for cls in classes:
        kg = kg_map.get(cls.kindergarten_id) if cls.kindergarten_id else None
        cls_enrollments = [e for e in official_enrollments if e.class_id == cls.id]
        children_count = len({e.child_id for e in cls_enrollments})
        cls_assignments = [a for a in active_assignments if a.class_id == cls.id]
        sup_ids = {a.supervisor_id for a in cls_assignments}
        supervisors_in_class = [s for s in supervisors if s.id in sup_ids]
        try:
            required_sup = (
                calculate_required_supervisors(str(cls.age_group), children_count) if children_count > 0 else 0
            )
        except Exception:
            required_sup = 1 if children_count > 0 else 0
        actual_sup = len(sup_ids)
        supervisor_gap = max(0, required_sup - actual_sup)
        cps = _safe_div(children_count, actual_sup)
        cap_util = _pct(children_count, cls.capacity_total or 0)

        if children_count > 0 and actual_sup == 0:
            risk_status = "critical"
        elif supervisor_gap > 0:
            risk_status = "warning"
        else:
            risk_status = "normal"

        if children_count > 0 and actual_sup == 0:
            recommended_action_ar = "إجراء عاجل: تعيين مشرف لهذا الفصل قبل قبول أي تسجيلات جديدة."
            recommended_action_en = "Urgent: assign a supervisor to this class before accepting new enrollments."
        elif supervisor_gap > 0:
            recommended_action_ar = "إجراء وقائي: إضافة مشرف إضافي لتغطية الفصل."
            recommended_action_en = "Preventive: add additional supervisor coverage for this class."
        else:
            recommended_action_ar = "الوضع مستقر: استمر في المراقبة."
            recommended_action_en = "Stable: continue monitoring."

        supervisor_names = [s.full_name or s.username for s in supervisors_in_class]

        rows.append(
            {
                "id": cls.id,
                "class_code": cls.class_code,
                "name_ar": cls.name_ar,
                "name_en": cls.name_en,
                "age_group": cls.age_group,
                "kindergarten_id": cls.kindergarten_id,
                "kindergarten_name_ar": kg.name_ar if kg else "",
                "kindergarten_name_en": kg.name_en if kg else "",
                "governorate": kg.governorate if kg else "",
                "city": kg.district if kg else "",
                "children_count": children_count,
                "capacity": cls.capacity_total or 0,
                "capacity_utilization_pct": cap_util,
                "supervisors": supervisor_names,
                "supervisors_count": actual_sup,
                "required_supervisors": required_sup,
                "supervisor_gap": supervisor_gap,
                "children_per_supervisor": cps,
                "risk_status": risk_status,
                "recommended_action_ar": recommended_action_ar,
                "recommended_action_en": recommended_action_en,
            }
        )
    rows.sort(key=lambda x: {"critical": 0, "warning": 1, "normal": 2}.get(x["risk_status"], 3))
    return rows


def _supervisor_analytics(
    db: Session,
    filters: ScopeFilters,
    classes: list[models.Class],
    supervisors: list[models.User],
    active_assignments: list[models.SupervisorAssignment],
    official_enrollments: list[models.EnrollmentApplication],
) -> dict[str, Any]:
    class_supervisor_map: dict[int, list[int]] = {}
    for a in active_assignments:
        class_supervisor_map.setdefault(a.class_id, []).append(a.supervisor_id)

    class_map = {c.id: c for c in classes}
    kg_ids_needed = {c.kindergarten_id for c in classes if c.kindergarten_id}
    kg_ids_needed.update(s.kindergarten_id for s in supervisors if s.kindergarten_id)
    kg_map = (
        {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids_needed)).all()}
        if kg_ids_needed
        else {}
    )

    enrolled_by_class: dict[int, int] = {}
    for e in official_enrollments:
        if e.class_id:
            enrolled_by_class[e.class_id] = enrolled_by_class.get(e.class_id, 0) + 1

    supervisors_data: list[dict[str, Any]] = []
    for s in supervisors:
        s_assignments = [a for a in active_assignments if a.supervisor_id == s.id]
        s_class_ids = {a.class_id for a in s_assignments}
        s_classes = [class_map[cid] for cid in s_class_ids if cid in class_map]
        kgs_in_charge = {class_map[cid].kindergarten_id for cid in s_class_ids if cid in class_map}
        children_count = sum(enrolled_by_class.get(cid, 0) for cid in s_class_ids)
        expected_kgs = {s.kindergarten_id} if s.kindergarten_id else set()
        outside_kg = kgs_in_charge - expected_kgs
        multiple_classes = len(s_class_ids) > 1
        error_flags = []
        if outside_kg:
            error_flags.append("assigned_outside_kindergarten")
        if multiple_classes:
            error_flags.append("assigned_to_multiple_classes")
        inactive_classes = [c for c in s_classes if not c.is_active]
        if inactive_classes:
            error_flags.append("assigned_to_inactive_class")
        no_class_assignment = len(s_class_ids) == 0
        if no_class_assignment:
            error_flags.append("no_class_assignment")

        if children_count > 0 and len(s_class_ids) == 0:
            issue_flag = "critical"
        elif error_flags:
            issue_flag = "invalid"
        elif children_count == 0 and len(s_class_ids) > 0:
            issue_flag = "underused"
        else:
            issue_flag = "ok"

        supervisors_data.append(
            {
                "id": s.id,
                "username": s.username,
                "full_name": s.full_name or s.username,
                "kindergarten_id": s.kindergarten_id,
                "kindergarten_name_ar": kg_map[s.kindergarten_id].name_ar
                if s.kindergarten_id and s.kindergarten_id in kg_map
                else "",
                "kindergarten_name_en": kg_map[s.kindergarten_id].name_en
                if s.kindergarten_id and s.kindergarten_id in kg_map
                else "",
                "governorate": kg_map[s.kindergarten_id].governorate
                if s.kindergarten_id and s.kindergarten_id in kg_map
                else "",
                "city": kg_map[s.kindergarten_id].district if s.kindergarten_id and s.kindergarten_id in kg_map else "",
                "classes_count": len(s_classes),
                "children_count": children_count,
                "error_flags": error_flags,
                "issue_flag": issue_flag,
            }
        )

    total_supervisors = len(supervisors)
    actual_supervisors = len({a.supervisor_id for a in active_assignments})
    required_supervisors = 0
    for c in classes:
        n = enrolled_by_class.get(c.id, 0)
        if n > 0:
            try:
                required_supervisors += calculate_required_supervisors(str(c.age_group), n)
            except Exception:
                required_supervisors += 1

    supervisors_with_errors = [s for s in supervisors_data if s["error_flags"]]
    supervisors_without_class = [s for s in supervisors_data if "no_class_assignment" in s["error_flags"]]
    supervisors_multiple_classes = [s for s in supervisors_data if "assigned_to_multiple_classes" in s["error_flags"]]
    supervisors_outside_kg = [s for s in supervisors_data if "assigned_outside_kindergarten" in s["error_flags"]]

    return {
        "total_supervisors": total_supervisors,
        "kpis": {
            "required_supervisors": required_supervisors,
            "actual_supervisors": actual_supervisors,
        },
        "supervisors": supervisors_data,
        "supervisors_with_errors": len(supervisors_with_errors),
        "supervisors_without_class": len(supervisors_without_class),
        "supervisors_multiple_classes": len(supervisors_multiple_classes),
        "supervisors_outside_kg": len(supervisors_outside_kg),
        "error_table": supervisors_with_errors,
    }


def _build_response(report_type: str, filters: ScopeFilters, metrics: dict[str, Any], lang: str) -> dict[str, Any]:
    interpretation = _interpret_overview(metrics, lang)
    risk_rows = _risk_rows(metrics)

    mapped_labels = [AGE_BUCKET_LABELS.get(k, {"ar": k, "en": k}) for k in metrics["age_buckets"].keys()]

    age_total = sum(metrics["age_buckets"].values())
    age_dataset = {
        "labels": mapped_labels,
        "datasets": [
            {
                "label": _localized("عدد الأطفال", "Children", lang),
                "data": [metrics["age_buckets"][k] for k in metrics["age_buckets"].keys()],
            }
        ],
    }

    def _gov_en(gov: str) -> str:
        if not gov:
            return ""
        if gov in settings.JORDAN_GOVERNORATES:
            idx = settings.JORDAN_GOVERNORATES.index(gov)
            if idx < len(settings.JORDAN_GOVERNORATES_ENGLISH):
                return settings.JORDAN_GOVERNORATES_ENGLISH[idx]
        return gov

    def _city_en(city: str) -> str:
        """Translate city name to English using jordan_locations data (CHART-002)."""
        if not city:
            return ""
        from services.jordan_locations import AREAS

        # Search through all governorates for the city
        for gov_key, areas in AREAS.items():
            for area in areas:
                if area["name_ar"] == city or city in area.get("aliases", []):
                    return area["name_en"]
        return city

    return {
        "report_type": report_type,
        "level": filters.level.value,
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "kindergarten_id": filters.kindergarten_id,
            "class_id": filters.class_id,
            "period": metrics["period"],
        },
        "kpis": {
            "total_children": metrics["total_children"],
            "total_kindergartens": metrics["total_kindergartens"],
            "total_supervisors": metrics["total_supervisors"],
            "total_classes": metrics["total_classes"],
            "children_per_kindergarten": metrics["children_per_kindergarten"],
            "children_per_supervisor": metrics["children_per_supervisor"],
            "children_per_class": metrics["children_per_class"],
            "required_supervisors": metrics["required_supervisors"],
            "actual_supervisors": metrics["actual_supervisors"],
            "supervisor_gap": metrics["supervisor_gap"],
            "capacity_utilization_pct": metrics["capacity_utilization_pct"],
            "data_quality_score": metrics["data_quality_score"],
            "compliance_score": metrics["compliance_score"],
        },
        "children": {
            "enrollment_status_counts": metrics["enrollment_status_counts"],
            "age_buckets": metrics["age_buckets"],
            "age_bucket_percentages": {k: _pct(v, age_total) for k, v in metrics["age_buckets"].items()},
            "age_invalid_reasons": metrics["age_invalid_reasons"],
            "gender_counts": metrics["gender_counts"],
            "gender_percentages": {
                "male_pct": _pct(metrics["gender_counts"]["male"], metrics["total_children"]),
                "female_pct": _pct(metrics["gender_counts"]["female"], metrics["total_children"]),
                "unknown_pct": _pct(metrics["gender_counts"]["unknown"], metrics["total_children"]),
            },
        },
        "quality": {
            "children_without_kindergarten": metrics["children_without_kindergarten"],
            "children_without_class": metrics["children_without_class"],
            "children_missing_location": metrics["children_missing_location"],
            "children_in_multiple_classes": metrics["children_in_multiple_classes"],
            "duplicate_children": metrics["duplicate_children"],
            "classes_without_supervisor": metrics["classes_without_supervisor"],
            "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
            "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
            "kindergartens_over_capacity": metrics["kindergartens_over_capacity"],
            "kindergartens_missing_coordinates": metrics["kindergartens_missing_coordinates"],
            "kindergartens_missing_capacity": metrics["kindergartens_missing_capacity"],
        },
        "charts": {
            "age_distribution": age_dataset,
            "children_by_governorate": {
                "labels": [
                    {"ar": r["governorate"], "en": _gov_en(r["governorate"])} for r in metrics["by_governorate"]
                ],
                "datasets": [
                    {
                        "label": _localized("الأطفال", "Children", lang),
                        "data": [r["children_count"] for r in metrics["by_governorate"]],
                    }
                ],
            },
            "children_by_city": {
                "labels": [{"ar": r["city"], "en": _city_en(r["city"])} for r in metrics["by_city"]],
                "datasets": [
                    {
                        "label": _localized("الأطفال", "Children", lang),
                        "data": [r["children_count"] for r in metrics["by_city"]],
                    }
                ],
            },
            "risk_ranking": risk_rows,
        },
        "tables": {
            "governorate_breakdown": metrics["by_governorate"],
            "city_breakdown": metrics["by_city"],
            "risk_ranking": risk_rows,
        },
        "interpretation": interpretation,
        "recommended_actions": [interpretation["recommended_action"]],
    }


def _resolve_report_payload(
    report_type: str,
    db: Session,
    level: ReportLevel,
    governorate: Optional[str],
    city: Optional[str],
    area: Optional[str],
    kindergarten_id: Optional[int],
    class_id: Optional[int],
    period: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    lang: str,
) -> dict[str, Any]:
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)

    if report_type in {"overview", "children_summary", "kindergartens_summary", "supervisors_coverage", "drilldown"}:
        return _build_response(report_type, filters, metrics, lang)
    if report_type == "kindergartens_detail":
        return kindergartens_detail(
            level=level,
            governorate=filters.governorate,
            city=filters.city,
            area=filters.area,
            kindergarten_id=filters.kindergarten_id,
            date_from=start,
            date_to=end,
            lang=lang,
            db=db,
            _=None,
        )
    if report_type == "classes_detail":
        return classes_detail(
            level=level,
            governorate=filters.governorate,
            city=filters.city,
            area=filters.area,
            kindergarten_id=filters.kindergarten_id,
            date_from=start,
            date_to=end,
            lang=lang,
            db=db,
            _=None,
        )
    if report_type == "supervisors_analytics":
        return supervisors_analytics(
            level=level,
            governorate=filters.governorate,
            city=filters.city,
            area=filters.area,
            kindergarten_id=filters.kindergarten_id,
            date_from=start,
            date_to=end,
            lang=lang,
            db=db,
            _=None,
        )
    if report_type == "kindergartens_classification":
        return kindergartens_classification(
            level=level,
            governorate=filters.governorate,
            city=filters.city,
            area=filters.area,
            date_from=start,
            date_to=end,
            lang=lang,
            db=db,
            _=None,
        )
    if report_type == "children_geography":
        return {
            "governorates": metrics["by_governorate"],
            "cities": metrics["by_city"],
            "areas": metrics["by_area"],
        }
    if report_type == "children_age_buckets":
        total = max(1, sum(metrics["age_buckets"].values()))
        return {
            "age_buckets": [
                {
                    "bucket": _localized(
                        AGE_BUCKET_LABELS.get(k, {"ar": k, "en": k})["ar"],
                        AGE_BUCKET_LABELS.get(k, {"ar": k, "en": k})["en"],
                        lang,
                    ),
                    "count": v,
                    "percentage": _pct(v, total),
                }
                for k, v in metrics["age_buckets"].items()
            ],
            "invalid_reasons": metrics["age_invalid_reasons"],
        }
    if report_type == "children_gender":
        total = max(1, metrics["total_children"])
        g = metrics["gender_counts"]
        return {
            "counts": g,
            "percentages": {
                "male_pct": _pct(g["male"], total),
                "female_pct": _pct(g["female"], total),
                "unknown_pct": _pct(g["unknown"], total),
            },
        }
    if report_type == "data_quality":
        return {
            "data_quality_score": metrics["data_quality_score"],
            "issues": {
                "missing_dob": metrics["age_invalid_reasons"]["missing_dob"],
                "future_dob": metrics["age_invalid_reasons"]["future_dob"],
                "missing_gender": metrics["gender_counts"]["unknown"],
                "children_without_kindergarten": metrics["children_without_kindergarten"],
                "children_without_class": metrics["children_without_class"],
                "children_in_multiple_classes": metrics["children_in_multiple_classes"],
                "duplicate_children": metrics["duplicate_children"],
            },
        }
    if report_type == "compliance":
        return {
            "compliance_score": metrics["compliance_score"],
            "violations": {
                "invalid_age_too_young": metrics["age_invalid_reasons"]["too_young"],
                "invalid_age_too_old": metrics["age_invalid_reasons"]["too_old"],
                "children_in_multiple_classes": metrics["children_in_multiple_classes"],
                "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
                "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
                "kindergartens_over_capacity": metrics["kindergartens_over_capacity"],
            },
        }
    if report_type == "risk_ranking":
        return {"ranking": _risk_rows(metrics)}

    raise HTTPException(status_code=422, detail="Unsupported report_type")


def _rows_for_export(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "tables" in payload:
        risk = payload["tables"].get("risk_ranking", [])
        if risk:
            return risk
        gov = payload["tables"].get("governorate_breakdown", [])
        if gov:
            return gov
    for key in ("ranking", "governorates", "cities", "age_buckets", "kindergartens", "classes", "supervisors"):
        if isinstance(payload.get(key), list) and payload[key]:
            return payload[key]
    if isinstance(payload.get("issues"), dict):
        return [{"issue": k, "count": v} for k, v in payload["issues"].items()]
    if isinstance(payload.get("violations"), dict):
        return [{"violation": k, "count": v} for k, v in payload["violations"].items()]
    return []


@router.get("/overview")
def reports_overview(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    prev_start, prev_end = _prev_period(start, end)
    prev_metrics = _collect_core_metrics(db, filters, prev_start, prev_end)
    response = _build_response("overview", filters, metrics, lang)
    children_delta = _delta(metrics["total_children"], prev_metrics["total_children"])
    quality_delta = _delta(metrics["data_quality_score"], prev_metrics["data_quality_score"])
    compliance_delta = _delta(metrics["compliance_score"], prev_metrics["compliance_score"])
    util_delta = _delta(metrics["capacity_utilization_pct"], prev_metrics["capacity_utilization_pct"])
    gap_delta = _delta(metrics["supervisor_gap"], prev_metrics["supervisor_gap"])
    response["comparison"] = {
        "period": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "total_children_delta": children_delta,
        "supervisor_gap_delta": gap_delta,
        "data_quality_score_delta": quality_delta,
        "compliance_score_delta": compliance_delta,
        "capacity_utilization_delta": util_delta,
        "prev_total_children": prev_metrics["total_children"],
        "prev_supervisor_gap": prev_metrics["supervisor_gap"],
        "prev_data_quality_score": prev_metrics["data_quality_score"],
        "prev_compliance_score": prev_metrics["compliance_score"],
    }
    sign = lambda v: "+" if v > 0 else ""
    response["interpretation"]["comparison_baseline"] = _localized(
        f"الفترة السابقة: {prev_metrics['total_children']} طفل | جودة البيانات {sign(quality_delta)}{quality_delta}% | امتثال {sign(compliance_delta)}{compliance_delta}%",
        f"Previous period: {prev_metrics['total_children']} children | data quality {sign(quality_delta)}{quality_delta}% | compliance {sign(compliance_delta)}{compliance_delta}%",
        lang,
    )
    return response


@router.get("/children/summary")
def children_summary(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("children_summary", filters, metrics, lang)


@router.get("/children/geography")
def children_geography(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    # CHART-031: Geography endpoints currently don't support kindergarten/class level filtering
    # Future enhancement: Add kindergarten_id and class_id parameters for granular geography data
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return {
        "level": level.value,
        "filters": {
            "governorate": governorate,
            "city": city,
            "area": area,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
        },
        "governorates": metrics["by_governorate"],
        "cities": metrics["by_city"],
        "areas": metrics["by_area"],
        "interpretation": _interpret_overview(metrics, lang),
    }


@router.get("/children/age-buckets")
def children_age_buckets(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    total = max(1, sum(metrics["age_buckets"].values()))
    dominant_bucket = max(metrics["age_buckets"], key=lambda k: metrics["age_buckets"][k])

    dom_lbl = AGE_BUCKET_LABELS.get(dominant_bucket, {"ar": dominant_bucket, "en": dominant_bucket})
    summary_ar = f"الفئة العمرية الأعلى هي {dom_lbl['ar']}."
    summary_en = f"Top age bucket is {dom_lbl['en']}."

    return {
        "level": level.value,
        "age_buckets": [
            {
                "bucket": _localized(
                    AGE_BUCKET_LABELS.get(k, {"ar": k, "en": k})["ar"],
                    AGE_BUCKET_LABELS.get(k, {"ar": k, "en": k})["en"],
                    lang,
                ),
                "count": v,
                "percentage": _pct(v, total),
            }
            for k, v in metrics["age_buckets"].items()
        ],
        "invalid_reasons": metrics["age_invalid_reasons"],
        "dominant_bucket": _localized(
            AGE_BUCKET_LABELS.get(dominant_bucket, {"ar": dominant_bucket, "en": dominant_bucket})["ar"],
            AGE_BUCKET_LABELS.get(dominant_bucket, {"ar": dominant_bucket, "en": dominant_bucket})["en"],
            lang,
        ),
        "interpretation": {
            "summary": _localized(summary_ar, summary_en, lang),
            "severity": "warning"
            if metrics["age_invalid_reasons"]["too_old"] + metrics["age_invalid_reasons"]["too_young"] > 0
            else "normal",
            "comparison_baseline": _localized("توزيع الفئات العمرية", "Age bucket distribution", lang),
            "recommended_action": _localized(
                "تحقق من صلاحية أعمار الأطفال غير المطابقة للسياسة.", "Review children with out-of-policy ages.", lang
            ),
        },
    }


@router.get("/children/gender")
def children_gender(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    total = max(1, metrics["total_children"])
    g = metrics["gender_counts"]
    return {
        "level": level.value,
        "counts": g,
        "percentages": {
            "male_pct": _pct(g["male"], total),
            "female_pct": _pct(g["female"], total),
            "unknown_pct": _pct(g["unknown"], total),
            "gender_balance_ratio": round(_safe_div(g["male"], g["female"] if g["female"] else 1), 2),
        },
        "interpretation": {
            "summary": _localized(
                "توزيع الجنس وصفي ويستخدم لمراقبة جودة البيانات.",
                "Gender distribution is descriptive and used for data-quality monitoring.",
                lang,
            ),
            "severity": "warning" if g["unknown"] > 0 else "normal",
            "comparison_baseline": _localized("إجمالي الأطفال", "Total children", lang),
            "recommended_action": _localized(
                "استكمل حقول الجنس المفقودة في السجلات.", "Complete missing gender values in records.", lang
            ),
        },
    }


@router.get("/kindergartens/summary")
def kindergartens_summary(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("kindergartens_summary", filters, metrics, lang)


@router.get("/kindergartens/supervision")
def kindergartens_supervision(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return {
        "level": level.value,
        "required_supervisors": metrics["required_supervisors"],
        "actual_supervisors": metrics["actual_supervisors"],
        "supervisor_gap": metrics["supervisor_gap"],
        "classes_without_supervisor": metrics["classes_without_supervisor"],
        "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
        "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
        "interpretation": _interpret_overview(metrics, lang),
    }


@router.get("/supervisors/coverage")
def supervisors_coverage(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("supervisors_coverage", filters, metrics, lang)


@router.get("/data-quality")
def data_quality_report(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    prev_start, prev_end = _prev_period(start, end)
    prev_metrics = _collect_core_metrics(db, filters, prev_start, prev_end)
    score = metrics["data_quality_score"]
    # ADMIN-SCORING-002: the band comes from the scoring module so endpoints
    # cannot drift from the authoritative thresholds.
    status_band = metrics["data_quality"]["status"]
    quality_delta = _delta(score, prev_metrics["data_quality_score"])
    sign = lambda v: "+" if v > 0 else ""
    return {
        "level": level.value,
        "data_quality_score": score,
        "status": status_band,
        "comparison": {
            "period": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
            "data_quality_score_delta": quality_delta,
            "prev_data_quality_score": prev_metrics["data_quality_score"],
        },
        "issues": {
            "missing_dob": metrics["age_invalid_reasons"]["missing_dob"],
            "future_dob": metrics["age_invalid_reasons"]["future_dob"],
            "missing_gender": metrics["gender_counts"]["unknown"],
            "children_without_kindergarten": metrics["children_without_kindergarten"],
            "children_without_class": metrics["children_without_class"],
            "children_missing_location": metrics["children_missing_location"],
            "children_in_multiple_classes": metrics["children_in_multiple_classes"],
            "duplicate_children": metrics["duplicate_children"],
            "kindergartens_missing_coordinates": metrics["kindergartens_missing_coordinates"],
            "kindergartens_missing_capacity": metrics["kindergartens_missing_capacity"],
            "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
        },
        # ADMIN-SCORING-002: the four weighted dimensions behind the score.
        "dimensions": metrics["data_quality"]["dimensions"],
        "interpretation": {
            "summary": _localized(
                "يعكس المؤشر مدى اكتمال وصحة السجلات التشغيلية.",
                "The score reflects operational record completeness and validity.",
                lang,
            ),
            "severity": "critical"
            if status_band == "red"
            else "warning"
            if status_band in {"yellow", "orange"}
            else "normal",
            "comparison_baseline": _localized(
                f"الفترة السابقة: جودة البيانات {prev_metrics['data_quality_score']}% (التغيير: {sign(quality_delta)}{quality_delta}%)",
                f"Previous period: data quality {prev_metrics['data_quality_score']}% (change: {sign(quality_delta)}{quality_delta}%)",
                lang,
            ),
            "recommended_action": _localized(
                "نفّذ خطة تصحيح للحقول المفقودة والتعارضات قبل دورة التقارير القادمة.",
                "Run a correction plan for missing/conflicting fields before the next reporting cycle.",
                lang,
            ),
        },
    }


@router.get("/compliance")
def compliance_report(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    prev_start, prev_end = _prev_period(start, end)
    prev_metrics = _collect_core_metrics(db, filters, prev_start, prev_end)
    score = metrics["compliance_score"]
    # ADMIN-SCORING-001: band supplied by the scoring module.
    status_band = metrics["compliance"]["status"]
    compliance_delta = _delta(score, prev_metrics["compliance_score"])
    sign = lambda v: "+" if v > 0 else ""
    return {
        "level": level.value,
        "compliance_score": score,
        "status": status_band,
        "comparison": {
            "period": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
            "compliance_score_delta": compliance_delta,
            "prev_compliance_score": prev_metrics["compliance_score"],
        },
        "violations": {
            "invalid_age_too_young": metrics["age_invalid_reasons"]["too_young"],
            "invalid_age_too_old": metrics["age_invalid_reasons"]["too_old"],
            "future_dob": metrics["age_invalid_reasons"]["future_dob"],
            "children_in_multiple_classes": metrics["children_in_multiple_classes"],
            "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
            "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
            "kindergartens_over_capacity": metrics["kindergartens_over_capacity"],
        },
        # ADMIN-SCORING-001: what each violation type actually cost, so a
        # reader can see why the score is where it is instead of guessing.
        "severity_breakdown": metrics["compliance"]["breakdown"],
        "weighted_violations": metrics["compliance"]["violations"],
        "total_deduction": metrics["compliance"]["total_deduction"],
        "interpretation": {
            "summary": _localized(
                "مؤشر الامتثال يقيس الالتزام بالقواعد التنظيمية والتشغيلية.",
                "Compliance score measures adherence to operational and regulatory rules.",
                lang,
            ),
            "severity": "critical"
            if status_band == "red"
            else "warning"
            if status_band in {"yellow", "orange"}
            else "normal",
            "comparison_baseline": _localized(
                f"الفترة السابقة: امتثال {prev_metrics['compliance_score']}% (التغيير: {sign(compliance_delta)}{compliance_delta}%)",
                f"Previous period: compliance {prev_metrics['compliance_score']}% (change: {sign(compliance_delta)}{compliance_delta}%)",
                lang,
            ),
            "recommended_action": _localized(
                "عالج المخالفات الحرجة أولا: الفصول بلا مشرف والتجاوزات الاستيعابية.",
                "Address critical violations first: classes without supervisors and over-capacity sites.",
                lang,
            ),
        },
    }


@router.get("/risk-ranking")
def risk_ranking(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    rows = _risk_rows(metrics)
    return {
        "level": level.value,
        "ranking": rows,
        "interpretation": {
            "summary": _localized(
                "ترتيب المخاطر يحدد المناطق ذات الأولوية للتدخل الفوري.",
                "Risk ranking identifies priority areas for immediate intervention.",
                lang,
            ),
            "severity": "critical"
            if rows and rows[0]["risk_score"] >= 60
            else "warning"
            if rows and rows[0]["risk_score"] >= 35
            else "normal",
            "comparison_baseline": _localized(
                "ترتيب المدن ضمن النطاق المحدد", "City ranking within selected scope", lang
            ),
            "recommended_action": _localized(
                "ابدأ بأعلى 5 مواقع خطورة وفعّل خطة علاج أسبوعية.",
                "Start with top 5 high-risk sites and run a weekly mitigation plan.",
                lang,
            ),
        },
    }


@router.get("/drilldown")
def drilldown(
    level: ReportLevel = Query(...),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("drilldown", filters, metrics, lang)


@router.get("/kindergartens/detail")
def kindergartens_detail(
    level: ReportLevel = Query(ReportLevel.CITY),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    official_rows = official_enroll_q.all()
    official_children_ids = {r.child_id for r in official_rows}

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(governorate_filter(models.Kindergarten.governorate, filters.governorate))
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
    if filters.area:
        kg_q = kg_q.filter(models.Kindergarten.area == filters.area)
    if filters.kindergarten_id:
        kg_q = kg_q.filter(models.Kindergarten.id == filters.kindergarten_id)
    kg_ids = [k.id for k in kg_q.all()]
    if kg_ids:
        classes_q = classes_q.filter(models.Class.kindergarten_id.in_(kg_ids))
    classes = classes_q.all()

    supervisors_q = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if kg_ids:
        supervisors_q = supervisors_q.filter(models.User.kindergarten_id.in_(kg_ids))
    supervisors = supervisors_q.all()

    active_assignments_q = db.query(models.SupervisorAssignment).filter(
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
        models.SupervisorAssignment.deleted_at.is_(None),
    )
    class_ids = [c.id for c in classes]
    if class_ids:
        active_assignments_q = active_assignments_q.filter(models.SupervisorAssignment.class_id.in_(class_ids))
    active_assignments = active_assignments_q.all()

    rows = _kindergarten_detail_rows(
        db, filters, official_children_ids, official_rows, classes, supervisors, active_assignments
    )
    total_kindergartens = len(rows)
    total_children = sum(r["children_count"] for r in rows)
    total_supervisors = sum(r["supervisors_count"] for r in rows)
    total_classes = sum(r["classes_count"] for r in rows)
    total_capacity = sum(r["capacity"] for r in rows)
    critical_count = sum(1 for r in rows if r["risk_status"] == "critical")
    warning_count = sum(1 for r in rows if r["risk_status"] == "warning")

    return {
        "level": level.value,
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "area": filters.area,
            "kindergarten_id": filters.kindergarten_id,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
        },
        "summary": {
            "total_kindergartens": total_kindergartens,
            "total_children": total_children,
            "total_supervisors": total_supervisors,
            "total_classes": total_classes,
            "total_capacity": total_capacity,
            "critical_count": critical_count,
            "warning_count": warning_count,
        },
        "kindergartens": rows,
        "interpretation": {
            "summary": _localized(
                f"يوجد {total_kindergartens} حضانة نشطة ضمن النطاق المحدد، منها {critical_count} ذات خطورة حرجة.",
                f"There are {total_kindergartens} active kindergartens in scope, {critical_count} at critical risk.",
                lang,
            ),
            "severity": "critical" if critical_count > 0 else "warning" if warning_count > 0 else "normal",
            "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
            "recommended_action": _localized(
                "ابدأ بالحضانات الحرجة ثم التي تحتاج انتباه.",
                "Start with critical kindergartens, then those needing attention.",
                lang,
            ),
        },
    }


@router.get("/classes/detail")
def classes_detail(
    level: ReportLevel = Query(ReportLevel.KINDERGARTEN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    if level != ReportLevel.KINDERGARTEN or not kindergarten_id:
        raise HTTPException(status_code=422, detail="kindergarten_id is required for class detail")
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    official_rows = official_enroll_q.all()

    classes_q = db.query(models.Class).filter(
        models.Class.is_active.is_(True), models.Class.kindergarten_id == kindergarten_id
    )
    if class_id:
        classes_q = classes_q.filter(models.Class.id == class_id)
    classes = classes_q.all()
    class_ids = [c.id for c in classes]

    supervisors_q = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if class_ids:
        supervisors_q = supervisors_q.filter(
            models.User.id.in_(
                db.query(models.SupervisorAssignment.supervisor_id).filter(
                    models.SupervisorAssignment.class_id.in_(class_ids),
                    or_(
                        models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()
                    ),
                    models.SupervisorAssignment.deleted_at.is_(None),
                )
            )
        )
    supervisors = supervisors_q.all()

    active_assignments_q = db.query(models.SupervisorAssignment).filter(
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
        models.SupervisorAssignment.deleted_at.is_(None),
    )
    if class_ids:
        active_assignments_q = active_assignments_q.filter(models.SupervisorAssignment.class_id.in_(class_ids))
    active_assignments = active_assignments_q.all()

    rows = _class_detail_rows(db, filters, official_rows, supervisors, active_assignments)
    total_classes = len(rows)
    total_children = sum(r["children_count"] for r in rows)
    total_capacity = sum(r["capacity"] for r in rows)
    critical_count = sum(1 for r in rows if r["risk_status"] == "critical")
    warning_count = sum(1 for r in rows if r["risk_status"] == "warning")

    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()

    return {
        "level": level.value,
        "kindergarten": {
            "id": kg.id if kg else None,
            "name_ar": kg.name_ar if kg else "",
            "name_en": kg.name_en if kg else "",
            "governorate": kg.governorate if kg else "",
            "city": kg.district if kg else "",
        },
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "area": filters.area,
            "kindergarten_id": filters.kindergarten_id,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
        },
        "summary": {
            "total_classes": total_classes,
            "total_children": total_children,
            "total_capacity": total_capacity,
            "critical_count": critical_count,
            "warning_count": warning_count,
        },
        "classes": rows,
        "interpretation": {
            "summary": _localized(
                f"يوجد {total_classes} فصل نشط في الحضانة المختارة، منها {critical_count} بحالة حرجة.",
                f"There are {total_classes} active classes in the selected kindergarten, {critical_count} at critical risk.",
                lang,
            ),
            "severity": "critical" if critical_count > 0 else "warning" if warning_count > 0 else "normal",
            "comparison_baseline": _localized("معدل الشبكة", "Network average", lang),
            "recommended_action": _localized(
                "عالج الفصول الحرجة أولا ثم راجع التغطية المشرفية.",
                "Address critical classes first, then review supervisor coverage.",
                lang,
            ),
        },
    }


@router.get("/supervisors/analytics")
def supervisors_analytics(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, kindergarten_id, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    official_rows = official_enroll_q.all()

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(governorate_filter(models.Kindergarten.governorate, filters.governorate))
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
    if filters.area:
        kg_q = kg_q.filter(models.Kindergarten.area == filters.area)
    if filters.kindergarten_id:
        kg_q = kg_q.filter(models.Kindergarten.id == filters.kindergarten_id)
    kg_ids = [k.id for k in kg_q.all()]
    if kg_ids:
        classes_q = classes_q.filter(models.Class.kindergarten_id.in_(kg_ids))
    classes = classes_q.all()
    class_ids = [c.id for c in classes]

    supervisors_q = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if kg_ids:
        supervisors_q = supervisors_q.filter(models.User.kindergarten_id.in_(kg_ids))
    supervisors = supervisors_q.all()

    active_assignments_q = db.query(models.SupervisorAssignment).filter(
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
        models.SupervisorAssignment.deleted_at.is_(None),
    )
    if class_ids:
        active_assignments_q = active_assignments_q.filter(models.SupervisorAssignment.class_id.in_(class_ids))
    active_assignments = active_assignments_q.all()

    analytics = _supervisor_analytics(db, filters, classes, supervisors, active_assignments, official_rows)

    return {
        "level": level.value,
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "area": filters.area,
            "kindergarten_id": filters.kindergarten_id,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
        },
        **analytics,
        "interpretation": {
            "summary": _localized(
                f"يوجد {analytics['total_supervisors']} مشرف نشط، مع {analytics['supervisors_with_errors']} يحتاج مراجعة.",
                f"There are {analytics['total_supervisors']} active supervisors, {analytics['supervisors_with_errors']} need review.",
                lang,
            ),
            "severity": "warning" if analytics["supervisors_with_errors"] > 0 else "normal",
            "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
            "recommended_action": _localized(
                "صحح أخطاء التعيين وتأكد من تغطية كل فصل بمشرف مؤهل.",
                "Correct assignment errors and ensure every class has a qualified supervisor.",
                lang,
            ),
        },
    }


@router.get("/kindergartens/classification")
def kindergartens_classification(
    level: ReportLevel = Query(ReportLevel.GOVERNORATE),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, area, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    official_rows = official_enroll_q.all()
    official_children_ids = {r.child_id for r in official_rows}

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(governorate_filter(models.Kindergarten.governorate, filters.governorate))
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
    if filters.area:
        kg_q = kg_q.filter(models.Kindergarten.area == filters.area)
    kg_ids = [k.id for k in kg_q.all()]
    if kg_ids:
        classes_q = classes_q.filter(models.Class.kindergarten_id.in_(kg_ids))
    classes = classes_q.all()
    class_ids = [c.id for c in classes]

    supervisors_q = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if kg_ids:
        supervisors_q = supervisors_q.filter(models.User.kindergarten_id.in_(kg_ids))
    supervisors = supervisors_q.all()

    active_assignments_q = db.query(models.SupervisorAssignment).filter(
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
        models.SupervisorAssignment.deleted_at.is_(None),
    )
    if class_ids:
        active_assignments_q = active_assignments_q.filter(models.SupervisorAssignment.class_id.in_(class_ids))
    active_assignments = active_assignments_q.all()

    rows = _kindergarten_detail_rows(
        db, filters, official_children_ids, official_rows, classes, supervisors, active_assignments
    )

    classification_counts = {}
    for r in rows:
        cls = r["classification"]
        classification_counts[cls] = classification_counts.get(cls, 0) + 1

    return {
        "level": level.value,
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "area": filters.area,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
        },
        "kindergartens": rows,
        "classification_counts": classification_counts,
        "interpretation": {
            "summary": _localized(
                f"يوجد {len(rows)} حضانة مصنفة ضمن النطاق المحدد.",
                f"There are {len(rows)} classified kindergartens in scope.",
                lang,
            ),
            "severity": "warning" if any(r["risk_status"] in ("critical", "warning") for r in rows) else "normal",
            "comparison_baseline": _localized("توزيع الفئات", "Category distribution", lang),
            "recommended_action": _localized(
                "راجع الفئات الحرجة وغير الطبيعية واتخذ إجراء تصحيحي.",
                "Review critical and abnormal categories and take corrective action.",
                lang,
            ),
        },
    }


@router.get("/export")
def export_report(
    report_type: str = Query(...),
    export_format: str = Query("csv", pattern="^(?i)(csv|json)$"),  # Simplified pattern (CHART-014)
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    payload = _resolve_report_payload(
        report_type=report_type,
        db=db,
        level=level,
        governorate=governorate,
        city=city,
        area=area,
        kindergarten_id=kindergarten_id,
        class_id=class_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
        lang=lang,
    )

    fmt = export_format.lower()

    log_audit_event(
        db=db,
        action=AuditAction.ANALYTICS_EXPORT_DOWNLOADED,
        actor=current_user,
        target_type="Report",
        target_ids=None,
        metadata={"report_type": report_type, "level": level.value, "format": fmt},
        sensitivity_level=2,
    )
    db.commit()

    if fmt == "json":
        return payload

    rows = _rows_for_export(payload)
    if rows:
        csv_header_map = {
            "total_children": _localized("إجمالي الأطفال", "Total Children", lang),
            "total_kindergartens": _localized("إجمالي الحضانات", "Total Kindergartens", lang),
            "total_supervisors": _localized("إجمالي المشرفات", "Total Supervisors", lang),
            "total_classes": _localized("إجمالي الشعب", "Total Classes", lang),
            "governorate": _localized("المحافظة", "Governorate", lang),
            "city": _localized("المدينة", "City", lang),
            "district": _localized("اللواء", "District", lang),
            "kindergarten": _localized("الحضانة", "Kindergarten", lang),
            "kindergartens": _localized("الحضانات", "Kindergartens", lang),
            "kindergarten_name": _localized("اسم الحضانة", "Kindergarten Name", lang),
            "kindergarten_count": _localized("عدد الحضانات", "Kindergartens", lang),
            "class": _localized("الشعبة", "Class", lang),
            "classes": _localized("الشعب", "Classes", lang),
            "class_count": _localized("عدد الشعب", "Classes", lang),
            "children": _localized("الأطفال", "Children", lang),
            "children_count": _localized("عدد الأطفال", "Children", lang),
            "supervisor": _localized("المشرفة", "Supervisor", lang),
            "supervisors": _localized("المشرفات", "Supervisors", lang),
            "supervisor_count": _localized("عدد المشرفات", "Supervisors", lang),
            "required_supervisors": _localized("المشرفات المطلوبات", "Required Supervisors", lang),
            "actual_supervisors": _localized("المشرفات الفعليات", "Actual Supervisors", lang),
            "supervisor_gap": _localized("فجوة الإشراف", "Supervisor Gap", lang),
            "capacity": _localized("الطاقة الاستيعابية", "Capacity", lang),
            "capacity_utilization_pct": _localized("نسبة إشغال الطاقة", "Capacity Utilization %", lang),
            "data_quality_score": _localized("مؤشر جودة البيانات", "Data Quality Score", lang),
            "compliance_score": _localized("مؤشر الامتثال", "Compliance Score", lang),
            "attendance_rate": _localized("نسبة الحضور", "Attendance Rate", lang),
            "absent_count": _localized("عدد الغياب", "Absent Count", lang),
            "present_count": _localized("عدد الحضور", "Present Count", lang),
            "B1": _localized("يوم إلى 3 أشهر", "1 day to 3 months", lang),
            "B2": _localized("3 إلى 6 أشهر", "3 to 6 months", lang),
            "B3": _localized("6 إلى 9 أشهر", "6 to 9 months", lang),
            "B4": _localized("9 إلى 12 شهر", "9 to 12 months", lang),
            "B5": _localized("12 إلى 15 شهر", "12 to 15 months", lang),
            "B6": _localized("15 إلى 18 شهر", "15 to 18 months", lang),
            "B7": _localized("18 إلى 21 شهر", "18 to 21 months", lang),
            "B8": _localized("21 إلى 24 شهر", "21 to 24 months", lang),
            "B9": _localized("24 إلى 27 شهر", "24 to 27 months", lang),
            "B10": _localized("27 إلى 30 شهر", "27 to 30 months", lang),
            "B11": _localized("30 إلى 33 شهر", "30 to 33 months", lang),
            "B12": _localized("33 إلى 36 شهر", "33 to 36 months", lang),
            "B13": _localized("36 إلى 39 شهر", "36 to 39 months", lang),
            "B14": _localized("39 إلى 42 شهر", "39 to 42 months", lang),
            "B15": _localized("42 إلى 45 شهر", "42 to 45 months", lang),
            "B16": _localized("45 إلى 48 شهر", "45 to 48 months", lang),
            "B17": _localized("48 إلى 51 شهر", "48 to 51 months", lang),
            "B18": _localized("51 إلى 54 شهر", "51 to 54 months", lang),
            "B19": _localized("54 إلى 57 شهر", "54 to 57 months", lang),
            # Additional keys for complete translation coverage (CHART-004)
            "supervisor_id": _localized("معرف المشرفة", "Supervisor ID", lang),
            "supervisor_name": _localized("اسم المشرفة", "Supervisor Name", lang),
            "kindergarten_name": _localized("اسم الحضانة", "Kindergarten Name", lang),
            "class_name": _localized("اسم الفصل", "Class Name", lang),
            "kindergarten_id": _localized("معرف الحضانة", "Kindergarten ID", lang),
            "class_id": _localized("معرف الفصل", "Class ID", lang),
            "child_id": _localized("معرف الطفل", "Child ID", lang),
            "child_name": _localized("اسم الطفل", "Child Name", lang),
            "parent_name": _localized("اسم ولي الأمر", "Parent Name", lang),
            "phone": _localized("الهاتف", "Phone", lang),
            "email": _localized("البريد الإلكتروني", "Email", lang),
            "address": _localized("العنوان", "Address", lang),
            "date": _localized("التاريخ", "Date", lang),
            "time": _localized("الوقت", "Time", lang),
            "status": _localized("الحالة", "Status", lang),
            "type": _localized("النوع", "Type", lang),
            "description": _localized("الوصف", "Description", lang),
            "notes": _localized("الملاحظات", "Notes", lang),
            "created_at": _localized("تاريخ الإنشاء", "Created At", lang),
            "updated_at": _localized("تاريخ التحديث", "Updated At", lang),
        }

        original_keys = list(rows[0].keys())
        translated_headers = [csv_header_map.get(k, k.replace("_", " ").title()) for k in original_keys]

        data = []
        for row in rows:
            data.append([row.get(k) for k in original_keys])
    else:
        translated_headers = ["message"]
        data = [["No rows available for export"]]

    filename = f"{report_type}_{level.value}_{_today().isoformat()}.csv"
    return export_service.generate_csv_response(translated_headers, data, filename)


# Admin Incident Reporting Endpoints
# =============================================================================


@router.post("/incidents/generate")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def generate_incident_report(
    request: Request,
    scope_type: str = Form(...),
    kindergarten_id: Optional[int] = Form(None),
    governorate: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    area: Optional[str] = Form(None),
    period_type: str = Form(...),
    year: Optional[int] = Form(None),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Generate and save an incident report"""
    try:
        # Validate scope
        try:
            scope_enum = models.ReportScopeType(scope_type)
        except ValueError:
            raise validation_error("Invalid scope type")

        # Calculate date range
        from report_service import ReportService

        reference_date = date(year, 1, 1) if period_type == "annual" and year else None
        start_date, end_date = ReportService.calculate_date_range(period_type, reference_date)

        # Generate metrics
        metrics = ReportService.generate_incident_report(
            scope_type=scope_enum,
            start_date=start_date,
            end_date=end_date,
            kindergarten_id=kindergarten_id,
            governorate=governorate,
            district=district,
            area=area,
            db=db,
        )

        # Create report record
        report = models.Report(
            report_type=models.ReportType.INCIDENT_SUMMARY,
            scope_type=scope_enum,
            kindergarten_id=kindergarten_id,
            governorate=governorate,
            district=district,
            area=area,
            start_date=start_date,
            end_date=end_date,
            metrics_json=metrics,
            created_by=current_user.id,
        )

        db.add(report)
        db.flush()

        log_audit_event(
            db,
            AuditAction.REPORT_GENERATED,
            current_user,
            "report",
            target_ids=report.id,
            metadata={
                "description": f"Generated incident report ID {report.id} for scope {scope_type}",
                "correlation_id": get_correlation_id(),
            },
        )
        db.commit()
        db.refresh(report)

        return JSONResponse({"success": True, "report_id": report.id, "message": "تم إنشاء التقرير بنجاح"})

    except HTTPException:
        db.rollback()
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to generate incident report: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_incident_reports(
    request: Request,
    scope_filter: Optional[str] = Query(None, description="Filter by scope type: KINDERGARTEN, GOVERNORATE, ALL"),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List incident reports with filtering"""
    try:
        query = (
            db.query(models.Report)
            .options(
                selectinload(models.Report.kindergarten),
                selectinload(models.Report.creator),
            )
            .filter(models.Report.report_type == models.ReportType.INCIDENT_SUMMARY)
        )

        # Apply scope filters
        if scope_filter:
            try:
                scope_enum = models.ReportScopeType(scope_filter)
                query = query.filter(models.Report.scope_type == scope_enum)
            except ValueError:
                raise validation_error("Invalid scope filter")

        if kindergarten_id:
            query = query.filter(models.Report.kindergarten_id == kindergarten_id)

        if governorate:
            query = query.filter(governorate_filter(models.Report.governorate, governorate))

        # Pagination
        total = query.count()
        reports = query.order_by(models.Report.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        # Format response
        report_list = []
        for report in reports:
            scope_name = ""
            if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
                scope_name = report.kindergarten.name_ar
            elif report.scope_type == models.ReportScopeType.GOVERNORATE:
                scope_name = report.governorate
            elif report.scope_type == models.ReportScopeType.DISTRICT:
                scope_name = report.district
            elif report.scope_type == models.ReportScopeType.AREA:
                scope_name = report.area
            elif report.scope_type == models.ReportScopeType.ALL:
                scope_name = _localized("جميع الحضانات", "All Kindergartens", lang)

            report_list.append(
                {
                    "id": report.id,
                    "title": _localized(
                        f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
                        f"Incident Report - {scope_name} ({report.start_date} - {report.end_date})",
                        lang,
                    ),
                    "scope_type": report.scope_type.value,
                    "scope_name": scope_name,
                    "start_date": report.start_date.isoformat(),
                    "end_date": report.end_date.isoformat(),
                    "created_at": report.created_at.isoformat(),
                    "created_by": report.creator.username
                    if report.creator
                    else _localized("غير معروف", "Unknown", lang),
                    "total_incidents": report.metrics_json.get("total_incidents", 0),
                }
            )

        return {
            "reports": report_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to list incident reports: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents/{report_id}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_incident_report_detail(
    report_id: int,
    request: Request,
    lang: str = Query("ar", pattern="^(ar|en)$"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get detailed incident report"""
    try:
        report = (
            db.query(models.Report)
            .filter(models.Report.id == report_id, models.Report.report_type == models.ReportType.INCIDENT_SUMMARY)
            .first()
        )

        if not report:
            raise not_found_error("Report not found")

        # Format scope name
        scope_name = ""
        if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
            scope_name = report.kindergarten.name_ar
        elif report.scope_type == models.ReportScopeType.GOVERNORATE:
            scope_name = report.governorate
        elif report.scope_type == models.ReportScopeType.DISTRICT:
            scope_name = report.district
        elif report.scope_type == models.ReportScopeType.AREA:
            scope_name = report.area
        elif report.scope_type == models.ReportScopeType.ALL:
            scope_name = _localized("جميع الحضانات", "All Kindergartens", lang)

        return {
            "id": report.id,
            "title": _localized(
                f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
                f"Incident Report - {scope_name} ({report.start_date} - {report.end_date})",
                lang,
            ),
            "scope_type": report.scope_type.value,
            "scope_name": scope_name,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "created_at": report.created_at.isoformat(),
            "created_by": report.creator.username if report.creator else _localized("غير معروف", "Unknown", lang),
            "metrics": report.metrics_json,
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get incident report detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents/{report_id}/export")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def export_incident_report_csv(
    report_id: int,
    request: Request,
    lang: str = Query("ar", pattern="^(ar|en)$"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export incident report as CSV"""
    try:
        report = (
            db.query(models.Report)
            .filter(models.Report.id == report_id, models.Report.report_type == models.ReportType.INCIDENT_SUMMARY)
            .first()
        )

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Not localised: both halves are derived from enum values, which are the
        # same in either language. Wrapping identical strings in _localized() only
        # looked bilingual.
        report_title = f"{report.report_type.value.replace('_', ' ').title()} - {report.scope_type.value.title()}"

        rows = []
        rows.append([_localized("عنوان التقرير", "Report Title", lang), report_title])
        rows.append(
            [_localized("النطاق", "Scope", lang), _localized(report.scope_type.value, report.scope_type.value, lang)]
        )
        rows.append([_localized("تاريخ البداية", "Start Date", lang), report.start_date.isoformat()])
        rows.append([_localized("تاريخ النهاية", "End Date", lang), report.end_date.isoformat()])
        rows.append(
            [
                _localized("أنشأ بواسطة", "Generated By", lang),
                report.creator.username if report.creator else _localized("غير معروف", "Unknown", lang),
            ]
        )
        rows.append([_localized("تاريخ الإنشاء", "Generated At", lang), report.created_at.isoformat()])
        rows.append([])

        # Write metrics
        metrics = report.metrics_json
        rows.append([_localized("المؤشر", "Metric", lang), _localized("القيمة", "Value", lang)])
        rows.append([_localized("إجمالي الحوادث", "Total Incidents", lang), metrics.get("total_incidents", 0)])
        rows.append([_localized("الحوادث المفتوحة", "Open Incidents", lang), metrics.get("open_incidents", 0)])
        rows.append([_localized("الحوادث المغلقة", "Closed Incidents", lang), metrics.get("closed_incidents", 0)])
        rows.append([])

        # Incidents by type
        rows.append([_localized("الحوادث حسب النوع", "Incidents by Type", lang)])
        rows.append([_localized("النوع", "Type", lang), _localized("العدد", "Count", lang)])
        for type_name, count in metrics.get("incidents_by_type", {}).items():
            rows.append([type_name, count])
        rows.append([])

        # Incidents by severity
        rows.append([_localized("الحوادث حسب الخطورة", "Incidents by Severity", lang)])
        rows.append([_localized("الخطورة", "Severity", lang), _localized("العدد", "Count", lang)])
        for severity, count in metrics.get("incidents_by_severity", {}).items():
            rows.append([severity, count])
        rows.append([])

        # Per kindergarten (if applicable)
        per_kg = metrics.get("per_kindergarten", {})
        if per_kg:
            rows.append([_localized("الحوادث حسب الحضانة", "Incidents by Kindergarten", lang)])
            rows.append([_localized("الحضانة", "Kindergarten", lang), _localized("العدد", "Count", lang)])
            for kg, count in per_kg.items():
                rows.append([kg, count])

        # Build the response before recording a successful export so a local
        # serialization failure is logged only by the failure path below.
        filename = f"incident_report_{report_id}_{report.start_date.isoformat()}_{report.end_date.isoformat()}.csv"
        response = export_service.generate_raw_csv_response(rows, filename)

        log_audit_event(
            db=db,
            action=AuditAction.INCIDENT_REPORT_EXPORT,
            actor=current_user,
            target_type="Report",
            target_ids=report.id,
            metadata={
                "format": "csv",
                "report_type": report.report_type.value,
                "scope_type": report.scope_type.value,
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
            },
            sensitivity_level=2,
        )
        db.commit()
        return response

    except HTTPException:
        raise
    except (SQLAlchemyError, ValueError, IOError, OSError) as e:
        db.rollback()
        try:
            log_audit_event(
                db=db,
                action=AuditAction.INCIDENT_REPORT_EXPORT_FAILED,
                actor=current_user,
                target_type="Report",
                target_ids=report_id,
                metadata={"format": "csv", "error_type": type(e).__name__},
                sensitivity_level=3,
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Failed to persist incident-report export failure audit")
        logger.error(f"Failed to export incident report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/geography/districts")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_districts(
    request: Request,
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List distinct districts/قصبة/لواء, optionally filtered by governorate"""
    try:
        query = db.query(models.Kindergarten.district).distinct()
        if governorate:
            query = query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
        districts = [d[0] for d in query.all() if d[0]]
        return {"districts": sorted(districts)}
    except Exception as e:
        logger.error(f"Failed to list districts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/geography/areas")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_areas(
    request: Request,
    governorate: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List distinct areas/منطقة, optionally filtered by governorate and/or district"""
    try:
        query = db.query(models.Kindergarten.area).distinct()
        if governorate:
            query = query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
        if district:
            query = query.filter(models.Kindergarten.district == district)
        areas = [a[0] for a in query.all() if a[0]]
        return {"areas": sorted(areas)}
    except Exception as e:
        logger.error(f"Failed to list areas: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scopes")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_available_scopes(
    request: Request, current_user: models.User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Get available report scopes for the current user"""
    try:
        from report_service import ReportService

        scopes = ReportService.get_available_scopes(current_user, db)
        return {"scopes": scopes}

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get available scopes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Admin Alerts API
# =============================================================================


class AdminAlertResponse(BaseModel):
    id: int
    severity: str
    governorate: Optional[str] = None
    kindergarten_name: Optional[str] = None
    metric: str
    current_value: float
    threshold: Optional[float] = None
    triggered_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by_id: Optional[int] = None
    status: str
    message: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None


class AdminAlertsListResponse(BaseModel):
    alerts: List[AdminAlertResponse]
    total: int
    page: int
    page_size: int
