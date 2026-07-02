from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import csv
import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import models
from admin_security import log_audit_event
from audit_actions import AuditAction
from child_age_policy import calculate_age_days, calculate_age_months
from database import get_db
from dependencies import require_admin
from validators import calculate_required_supervisors


router = APIRouter(prefix="/api/admin/reports", tags=["Admin Reports"])

_JORDAN_TZ = timezone(timedelta(hours=3))
_ACTIVE_STATUSES = {models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.ACCEPTED}


class ReportLevel(str, Enum):
    JORDAN = "jordan"
    GOVERNORATE = "governorate"
    CITY = "city"
    KINDERGARTEN = "kindergarten"
    CLASS = "class"


@dataclass
class ScopeFilters:
    level: ReportLevel
    governorate: Optional[str]
    city: Optional[str]
    kindergarten_id: Optional[int]
    class_id: Optional[int]


def _today() -> date:
    return datetime.now(_JORDAN_TZ).date()


def _as_float(num: float, den: float) -> float:
    if not den:
        return 0.0
    return round(float(num) / float(den), 4)


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
        start_month = 1 if today.month <= 6 else 7
        start = date(today.year, start_month, 1)
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


def _build_scope_filters(
    level: ReportLevel,
    governorate: Optional[str],
    city: Optional[str],
    kindergarten_id: Optional[int],
    class_id: Optional[int],
) -> ScopeFilters:
    if level in {ReportLevel.GOVERNORATE, ReportLevel.CITY} and not governorate:
        raise HTTPException(status_code=422, detail="governorate is required for governorate/city level")
    if level == ReportLevel.CITY and not city:
        raise HTTPException(status_code=422, detail="city is required for city level")
    if level == ReportLevel.KINDERGARTEN and not kindergarten_id:
        raise HTTPException(status_code=422, detail="kindergarten_id is required for kindergarten level")
    if level == ReportLevel.CLASS and not class_id:
        raise HTTPException(status_code=422, detail="class_id is required for class level")

    return ScopeFilters(
        level=level,
        governorate=governorate,
        city=city,
        kindergarten_id=kindergarten_id,
        class_id=class_id,
    )


def _kg_filter_expr(filters: ScopeFilters):
    clauses = [models.Kindergarten.status == models.KindergartenStatus.ACTIVE]
    if filters.level in {ReportLevel.GOVERNORATE, ReportLevel.CITY, ReportLevel.KINDERGARTEN, ReportLevel.CLASS}:
        if filters.governorate:
            clauses.append(models.Kindergarten.governorate == filters.governorate)
    if filters.level in {ReportLevel.CITY, ReportLevel.KINDERGARTEN, ReportLevel.CLASS} and filters.city:
        clauses.append(models.Kindergarten.district == filters.city)
    if filters.level == ReportLevel.KINDERGARTEN and filters.kindergarten_id:
        clauses.append(models.Kindergarten.id == filters.kindergarten_id)
    if filters.level == ReportLevel.CLASS and filters.class_id:
        clauses.append(models.Class.id == filters.class_id)
    return clauses


def _base_enrollment_query(db: Session, filters: ScopeFilters):
    q = (
        db.query(models.EnrollmentApplication)
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

    if age_days < 70:
        return "invalid", "too_young"
    if age_months > 56:
        return "invalid", "too_old"

    if age_months < 6:
        return "B1", None
    if age_months < 12:
        return "B2", None
    if age_months < 18:
        return "B3", None
    if age_months < 24:
        return "B4", None
    if age_months < 30:
        return "B5", None
    if age_months < 36:
        return "B6", None
    if age_months < 42:
        return "B7", None
    if age_months < 48:
        return "B8", None
    if age_months < 54:
        return "B9", None
    return "B10", None


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
        f"يظهر التقرير {metrics.get('total_children', 0)} طفلا نشطا عبر {metrics.get('total_kindergartens', 0)} روضة.",
        f"The report shows {metrics.get('total_children', 0)} active children across {metrics.get('total_kindergartens', 0)} kindergartens.",
        lang,
    )
    return {
        "summary": summary,
        "severity": severity,
        "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
        "recommended_action": action,
    }


def _collect_core_metrics(db: Session, filters: ScopeFilters, date_from: date, date_to: date) -> dict[str, Any]:
    enroll_q = _base_enrollment_query(db, filters)

    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()

    child_ids = {r.child_id for r in official_rows}
    official_children = (
        db.query(models.Child)
        .filter(models.Child.id.in_(list(child_ids)))
        .all()
        if child_ids
        else []
    )

    kindergartens_q = db.query(models.Kindergarten)
    if filters.governorate:
        kindergartens_q = kindergartens_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kindergartens_q = kindergartens_q.filter(models.Kindergarten.district == filters.city)
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
            required_supervisors += 1

    actual_supervisors = len({a.supervisor_id for a in active_assignments})

    capacity_total = sum((c.capacity_total or 0) for c in classes)
    total_children = len(child_ids)

    enrollment_status_counts: dict[str, int] = {}
    for r in all_enroll_rows:
        k = str(r.status.value if hasattr(r.status, "value") else r.status).lower()
        enrollment_status_counts[k] = enrollment_status_counts.get(k, 0) + 1

    # Age buckets and invalid-age/data issues
    age_buckets = {f"B{i}": 0 for i in range(1, 11)}
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
        g = str(child.gender.value if hasattr(child.gender, "value") else child.gender).upper() if child.gender else "UNKNOWN"
        if g == "MALE":
            gender_counts["male"] += 1
        elif g == "FEMALE":
            gender_counts["female"] += 1
        else:
            gender_counts["unknown"] += 1

    children_without_class = sum(1 for r in official_rows if r.class_id is None)
    children_without_kindergarten = sum(1 for r in official_rows if r.kindergarten_id is None)

    # Geography aggregations
    by_governorate: dict[str, dict[str, Any]] = {}
    by_city: dict[tuple[str, str], dict[str, Any]] = {}
    for kg in kindergartens:
        gov = kg.governorate or "Unknown"
        city = kg.district or "Unknown"
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

        by_governorate[gov]["kindergarten_count"] += 1
        by_city[key]["kindergarten_count"] += 1

    kg_id_map = {k.id: k for k in kindergartens}
    class_map = {c.id: c for c in classes}
    kg_class_counts: dict[int, int] = {}
    for c in classes:
        kg_class_counts[c.kindergarten_id] = kg_class_counts.get(c.kindergarten_id, 0) + 1
        parent_kg = kg_id_map.get(c.kindergarten_id)
        gov = (parent_kg.governorate if parent_kg else None) or "Unknown"
        city = (parent_kg.district if parent_kg else None) or "Unknown"
        by_governorate.setdefault(gov, {"governorate": gov, "kindergarten_count": 0, "class_count": 0, "children_count": 0, "supervisor_count": 0, "capacity": 0})
        by_governorate[gov]["class_count"] += 1
        by_governorate[gov]["capacity"] += c.capacity_total or 0
        city_key = (gov, city)
        by_city.setdefault(city_key, {"governorate": gov, "city": city, "kindergarten_count": 0, "class_count": 0, "children_count": 0, "supervisor_count": 0, "capacity": 0})
        by_city[city_key]["class_count"] += 1
        by_city[city_key]["capacity"] += c.capacity_total or 0

    supervisor_counts_by_kg: dict[int, int] = {}
    for s in supervisors:
        if s.kindergarten_id:
            supervisor_counts_by_kg[s.kindergarten_id] = supervisor_counts_by_kg.get(s.kindergarten_id, 0) + 1

    children_by_kg: dict[int, int] = {}
    for row in official_rows:
        if row.kindergarten_id:
            children_by_kg[row.kindergarten_id] = children_by_kg.get(row.kindergarten_id, 0) + 1

    for row in official_rows:
        kg_id = row.kindergarten_id
        kg = kg_id_map.get(kg_id)
        if not kg:
            continue
        gov = kg.governorate or "Unknown"
        city = kg.district or "Unknown"
        by_governorate[gov]["children_count"] += 1
        by_city[(gov, city)]["children_count"] += 1

    for kg in kindergartens:
        gov = kg.governorate or "Unknown"
        city = kg.district or "Unknown"
        sup = supervisor_counts_by_kg.get(kg.id, 0)
        by_governorate[gov]["supervisor_count"] += sup
        by_city[(gov, city)]["supervisor_count"] += sup

    # Data quality and compliance issue counters
    duplicate_children = (
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

    classes_without_supervisor = sum(1 for c in classes if class_supervisor_counts.get(c.id, 0) == 0)
    classes_with_children_no_supervisor = sum(
        1
        for c in classes
        if enrolled_by_class.get(c.id, 0) > 0 and class_supervisor_counts.get(c.id, 0) == 0
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

    compliance_violations = (
        age_invalid_reasons["too_young"]
        + age_invalid_reasons["too_old"]
        + classes_with_children_no_supervisor
        + kindergartens_no_supervisor_with_children
        + kindergartens_over_capacity
    )

    # data_quality_score: % of active kindergartens in scope that filed a report in the last 7 days
    # This matches the canonical definition in admin_endpoints.py and CLAUDE.md.
    active_kg_count = len(kindergartens)
    if active_kg_count > 0 and kg_ids:
        kg_with_recent_report = db.query(
            func.count(func.distinct(models.DailyReport.kindergarten_id))
        ).filter(
            models.DailyReport.kindergarten_id.in_(kg_ids),
            models.DailyReport.date >= _today() - timedelta(days=7),
        ).scalar() or 0
        data_quality_score = round((kg_with_recent_report / active_kg_count) * 100.0, 2)
    else:
        data_quality_score = 0.0

    entity_base = max(1, total_children + active_kg_count + len(classes))
    compliance_score = max(0.0, round(100.0 - ((compliance_violations / entity_base) * 100.0), 2))

    metrics = {
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
        "duplicate_children": duplicate_children,
        "classes_without_supervisor": classes_without_supervisor,
        "classes_with_children_no_supervisor": classes_with_children_no_supervisor,
        "kindergartens_no_supervisor_with_children": kindergartens_no_supervisor_with_children,
        "kindergartens_over_capacity": kindergartens_over_capacity,
        "kindergartens_missing_coordinates": kindergartens_missing_coordinates,
        "kindergartens_missing_capacity": kindergartens_missing_capacity,
        "data_quality_score": data_quality_score,
        "compliance_score": compliance_score,
        "by_governorate": list(by_governorate.values()),
        "by_city": list(by_city.values()),
    }
    return metrics


def _risk_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in metrics.get("by_city", []):
        children = row.get("children_count", 0)
        supervisors = row.get("supervisor_count", 0)
        capacity = row.get("capacity", 0)
        cps = _safe_div(children, supervisors)
        cap_util = _pct(children, capacity)
        score = 0
        if supervisors == 0 and children > 0:
            score += 45
        elif cps > 12:
            score += 25
        elif cps > 8:
            score += 12

        if cap_util > 100:
            score += 35
        elif cap_util > 85:
            score += 15

        if row.get("class_count", 0) == 0 and children > 0:
            score += 20

        if score >= 60:
            status = "critical"
        elif score >= 35:
            status = "warning"
        else:
            status = "normal"

        rows.append(
            {
                "governorate": row.get("governorate"),
                "city": row.get("city"),
                "risk_score": min(score, 100),
                "risk_status": status,
                "children_per_supervisor": cps,
                "capacity_utilization_pct": cap_util,
            }
        )

    rows.sort(key=lambda x: x["risk_score"], reverse=True)
    return rows


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
        kg_q = kg_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
    if filters.kindergarten_id:
        kg_q = kg_q.filter(models.Kindergarten.id == filters.kindergarten_id)
    kindergartens = kg_q.all()
    kg_map = {k.id: k for k in kindergartens}

    rows: list[dict[str, Any]] = []
    for kg_id, kg in kg_map.items():
        kg_classes = [c for c in classes if c.kindergarten_id == kg_id]
        kg_supervisors = [s for s in supervisors if s.kindergarten_id == kg_id]
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
        classes_without_supervisor = sum(1 for c in kg_classes if enrolled_by_class.get(c.id, 0) > 0 and all(a.class_id != c.id for a in kg_active_assignments))
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
            recommended_action_ar = "تحقق من حالة العمل وتفعيل الروضة أو إيقافها رسميا."
            recommended_action_en = "Verify operational status and activate or formally close."
        elif classification == "resource_underuse":
            recommended_action_ar = "استخدم الموارد بشكل أفضل أو أعد توزيعها."
            recommended_action_en = "Better utilize resources or redistribute them."
        else:
            recommended_action_ar = "الوضع مستقر: استمر في المراقبة."
            recommended_action_en = "Stable: continue monitoring."

        rows.append({
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
        })
    rows.sort(key=lambda x: ({"critical": 0, "warning": 1, "normal": 2}.get(x["risk_status"], 3), -x.get("risk_score", 0)))
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
        kg_map = {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(needed_kg_ids)).all()}

    rows: list[dict[str, Any]] = []
    for cls in classes:
        kg = kg_map.get(cls.kindergarten_id) if cls.kindergarten_id else None
        cls_enrollments = [e for e in official_enrollments if e.class_id == cls.id]
        children_count = len({e.child_id for e in cls_enrollments})
        cls_assignments = [a for a in active_assignments if a.class_id == cls.id]
        sup_ids = {a.supervisor_id for a in cls_assignments}
        supervisors_in_class = [s for s in supervisors if s.id in sup_ids]
        try:
            required_sup = calculate_required_supervisors(str(cls.age_group), children_count) if children_count > 0 else 0
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

        rows.append({
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
        })
    rows.sort(key=lambda x: ({"critical": 0, "warning": 1, "normal": 2}.get(x["risk_status"], 3)))
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
    kg_map = {k.id: k for k in db.query(models.Kindergarten).all()}

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

        supervisors_data.append({
            "id": s.id,
            "username": s.username,
            "full_name": s.full_name or s.username,
            "kindergarten_id": s.kindergarten_id,
            "kindergarten_name_ar": kg_map[s.kindergarten_id].name_ar if s.kindergarten_id and s.kindergarten_id in kg_map else "",
            "kindergarten_name_en": kg_map[s.kindergarten_id].name_en if s.kindergarten_id and s.kindergarten_id in kg_map else "",
            "governorate": kg_map[s.kindergarten_id].governorate if s.kindergarten_id and s.kindergarten_id in kg_map else "",
            "city": kg_map[s.kindergarten_id].district if s.kindergarten_id and s.kindergarten_id in kg_map else "",
            "classes_count": len(s_classes),
            "children_count": children_count,
            "classes_per_supervisor": _safe_div(len(s_classes), 1),
            "children_per_supervisor": _safe_div(children_count, 1),
            "error_flags": error_flags,
            "issue_flag": issue_flag,
        })

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

    age_total = sum(metrics["age_buckets"].values())
    age_dataset = {
        "labels": list(metrics["age_buckets"].keys()),
        "datasets": [
            {
                "label": _localized("عدد الأطفال", "Children", lang),
                "data": [metrics["age_buckets"][k] for k in metrics["age_buckets"].keys()],
            }
        ],
    }

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
            "age_bucket_percentages": {
                k: _pct(v, age_total) for k, v in metrics["age_buckets"].items()
            },
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
                "labels": [r["governorate"] for r in metrics["by_governorate"]],
                "datasets": [{"label": _localized("الأطفال", "Children", lang), "data": [r["children_count"] for r in metrics["by_governorate"]]}],
            },
            "children_by_city": {
                "labels": [r["city"] for r in metrics["by_city"]],
                "datasets": [{"label": _localized("الأطفال", "Children", lang), "data": [r["children_count"] for r in metrics["by_city"]]}],
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
    kindergarten_id: Optional[int],
    class_id: Optional[int],
    period: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    lang: str,
) -> dict[str, Any]:
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)

    if report_type in {"overview", "children_summary", "kindergartens_summary", "supervisors_coverage", "drilldown"}:
        return _build_response(report_type, filters, metrics, lang)
    if report_type == "kindergartens_detail":
        return kindergartens_detail(
            level=level,
            governorate=filters.governorate,
            city=filters.city,
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
        }
    if report_type == "children_age_buckets":
        total = max(1, sum(metrics["age_buckets"].values()))
        return {
            "age_buckets": [
                {"bucket": k, "count": v, "percentage": _pct(v, total)}
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
                "duplicate_children": metrics["duplicate_children"],
            },
        }
    if report_type == "compliance":
        return {
            "compliance_score": metrics["compliance_score"],
            "violations": {
                "invalid_age_too_young": metrics["age_invalid_reasons"]["too_young"],
                "invalid_age_too_old": metrics["age_invalid_reasons"]["too_old"],
                "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
                "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
                "kindergartens_over_capacity": metrics["kindergartens_over_capacity"],
            },
        }
    if report_type == "risk_ranking":
        return {"ranking": _risk_rows(metrics)}

    raise HTTPException(status_code=422, detail="Unsupported report_type")


def resolve_kindergarten_detail_report(db: Session, filters: ScopeFilters, date_from: date, date_to: date, lang: str) -> dict[str, Any]:
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()
    official_children_ids = {r.child_id for r in official_rows}

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
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

    rows = _kindergarten_detail_rows(db, filters, official_children_ids, official_rows, classes, supervisors, active_assignments)
    total_kindergartens = len(rows)
    total_children = sum(r["children_count"] for r in rows)
    total_supervisors = sum(r["supervisors_count"] for r in rows)
    total_classes = sum(r["classes_count"] for r in rows)
    total_capacity = sum(r["capacity"] for r in rows)
    critical_count = sum(1 for r in rows if r["risk_status"] == "critical")
    warning_count = sum(1 for r in rows if r["risk_status"] == "warning")
    return {
        "level": filters.level.value,
        "filters": {
            "governorate": filters.governorate,
            "city": filters.city,
            "kindergarten_id": filters.kindergarten_id,
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
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
                f"يوجد {total_kindergartens} روضة نشطة ضمن النطاق المحدد، منها {critical_count} ذات خطورة حرجة.",
                f"There are {total_kindergartens} active kindergartens in scope, {critical_count} at critical risk.",
                lang,
            ),
            "severity": "critical" if critical_count > 0 else "warning" if warning_count > 0 else "normal",
            "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
            "recommended_action": _localized(
                "ابدأ بالروضات الحرجة ثم التي تحتاج انتباه.",
                "Start with critical kindergartens, then those needing attention.",
                lang,
            ),
        },
    }


def _safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


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
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("overview", filters, metrics, lang)


@router.get("/children/summary")
def children_summary(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("children_summary", filters, metrics, lang)


@router.get("/children/geography")
def children_geography(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return {
        "level": level.value,
        "filters": {"governorate": governorate, "city": city, "period": {"from": start.isoformat(), "to": end.isoformat()}},
        "governorates": metrics["by_governorate"],
        "cities": metrics["by_city"],
        "interpretation": _interpret_overview(metrics, lang),
    }


@router.get("/children/age-buckets")
def children_age_buckets(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    total = max(1, sum(metrics["age_buckets"].values()))
    dominant_bucket = max(metrics["age_buckets"], key=lambda k: metrics["age_buckets"][k])
    return {
        "level": level.value,
        "age_buckets": [
            {"bucket": k, "count": v, "percentage": _pct(v, total)}
            for k, v in metrics["age_buckets"].items()
        ],
        "invalid_reasons": metrics["age_invalid_reasons"],
        "dominant_bucket": dominant_bucket,
        "interpretation": {
            "summary": _localized(f"الفئة العمرية الأعلى هي {dominant_bucket}.", f"Top age bucket is {dominant_bucket}.", lang),
            "severity": "warning" if metrics["age_invalid_reasons"]["too_old"] + metrics["age_invalid_reasons"]["too_young"] > 0 else "normal",
            "comparison_baseline": _localized("توزيع الفئات العمرية", "Age bucket distribution", lang),
            "recommended_action": _localized("تحقق من صلاحية أعمار الأطفال غير المطابقة للسياسة.", "Review children with out-of-policy ages.", lang),
        },
    }


@router.get("/children/gender")
def children_gender(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
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
            "summary": _localized("توزيع الجنس وصفي ويستخدم لمراقبة جودة البيانات.", "Gender distribution is descriptive and used for data-quality monitoring.", lang),
            "severity": "warning" if g["unknown"] > 0 else "normal",
            "comparison_baseline": _localized("إجمالي الأطفال", "Total children", lang),
            "recommended_action": _localized("استكمل حقول الجنس المفقودة في السجلات.", "Complete missing gender values in records.", lang),
        },
    }


@router.get("/kindergartens/summary")
def kindergartens_summary(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("kindergartens_summary", filters, metrics, lang)


@router.get("/kindergartens/supervision")
def kindergartens_supervision(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
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
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("supervisors_coverage", filters, metrics, lang)


@router.get("/data-quality")
def data_quality_report(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    score = metrics["data_quality_score"]
    if score >= 95:
        status_band = "green"
    elif score >= 85:
        status_band = "yellow"
    elif score >= 70:
        status_band = "orange"
    else:
        status_band = "red"

    return {
        "level": level.value,
        "data_quality_score": score,
        "status": status_band,
        "issues": {
            "missing_dob": metrics["age_invalid_reasons"]["missing_dob"],
            "future_dob": metrics["age_invalid_reasons"]["future_dob"],
            "missing_gender": metrics["gender_counts"]["unknown"],
            "children_without_kindergarten": metrics["children_without_kindergarten"],
            "children_without_class": metrics["children_without_class"],
            "duplicate_children": metrics["duplicate_children"],
            "kindergartens_missing_coordinates": metrics["kindergartens_missing_coordinates"],
            "kindergartens_missing_capacity": metrics["kindergartens_missing_capacity"],
            "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
        },
        "interpretation": {
            "summary": _localized("يعكس المؤشر مدى اكتمال وصحة السجلات التشغيلية.", "The score reflects operational record completeness and validity.", lang),
            "severity": "critical" if status_band == "red" else "warning" if status_band in {"yellow", "orange"} else "normal",
            "comparison_baseline": _localized("حد الجودة الوطني", "National quality threshold", lang),
            "recommended_action": _localized("نفّذ خطة تصحيح للحقول المفقودة والتعارضات قبل دورة التقارير القادمة.", "Run a correction plan for missing/conflicting fields before the next reporting cycle.", lang),
        },
    }


@router.get("/compliance")
def compliance_report(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    score = metrics["compliance_score"]
    if score >= 95:
        status_band = "green"
    elif score >= 85:
        status_band = "yellow"
    elif score >= 70:
        status_band = "orange"
    else:
        status_band = "red"

    return {
        "level": level.value,
        "compliance_score": score,
        "status": status_band,
        "violations": {
            "invalid_age_too_young": metrics["age_invalid_reasons"]["too_young"],
            "invalid_age_too_old": metrics["age_invalid_reasons"]["too_old"],
            "classes_with_children_no_supervisor": metrics["classes_with_children_no_supervisor"],
            "kindergartens_no_supervisor_with_children": metrics["kindergartens_no_supervisor_with_children"],
            "kindergartens_over_capacity": metrics["kindergartens_over_capacity"],
        },
        "interpretation": {
            "summary": _localized("مؤشر الامتثال يقيس الالتزام بالقواعد التنظيمية والتشغيلية.", "Compliance score measures adherence to operational and regulatory rules.", lang),
            "severity": "critical" if status_band == "red" else "warning" if status_band in {"yellow", "orange"} else "normal",
            "comparison_baseline": _localized("سياسة الامتثال الوطنية", "National compliance policy", lang),
            "recommended_action": _localized("عالج المخالفات الحرجة أولا: الفصول بلا مشرف والتجاوزات الاستيعابية.", "Address critical violations first: classes without supervisors and over-capacity sites.", lang),
        },
    }


@router.get("/risk-ranking")
def risk_ranking(
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    rows = _risk_rows(metrics)
    return {
        "level": level.value,
        "ranking": rows,
        "interpretation": {
            "summary": _localized("ترتيب المخاطر يحدد المناطق ذات الأولوية للتدخل الفوري.", "Risk ranking identifies priority areas for immediate intervention.", lang),
            "severity": "critical" if rows and rows[0]["risk_score"] >= 60 else "warning" if rows and rows[0]["risk_score"] >= 35 else "normal",
            "comparison_baseline": _localized("ترتيب المدن ضمن النطاق المحدد", "City ranking within selected scope", lang),
            "recommended_action": _localized("ابدأ بأعلى 5 مواقع خطورة وفعّل خطة علاج أسبوعية.", "Start with top 5 high-risk sites and run a weekly mitigation plan.", lang),
        },
    }


@router.get("/drilldown")
def drilldown(
    level: ReportLevel = Query(...),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    metrics = _collect_core_metrics(db, filters, start, end)
    return _build_response("drilldown", filters, metrics, lang)


@router.get("/kindergartens/detail")
def kindergartens_detail(
    level: ReportLevel = Query(ReportLevel.CITY),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()
    official_children_ids = {r.child_id for r in official_rows}

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
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

    rows = _kindergarten_detail_rows(db, filters, official_children_ids, official_rows, classes, supervisors, active_assignments)
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
                f"يوجد {total_kindergartens} روضة نشطة ضمن النطاق المحدد، منها {critical_count} ذات خطورة حرجة.",
                f"There are {total_kindergartens} active kindergartens in scope, {critical_count} at critical risk.",
                lang,
            ),
            "severity": "critical" if critical_count > 0 else "warning" if warning_count > 0 else "normal",
            "comparison_baseline": _localized("متوسط الشبكة", "Network average", lang),
            "recommended_action": _localized(
                "ابدأ بالروضات الحرجة ثم التي تحتاج انتباه.",
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
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, class_id)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True), models.Class.kindergarten_id == kindergarten_id)
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
                    or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= _today()),
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
                f"يوجد {total_classes} فصل نشط في الروضة المختارة، منها {critical_count} بحالة حرجة.",
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
    kindergarten_id: Optional[int] = Query(None),
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, kindergarten_id, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    official_rows = official_enroll_q.all()

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
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
    period: Optional[str] = Query("this_month"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    filters = _build_scope_filters(level, governorate, city, None, None)
    start, end = _resolve_dates(date_from, date_to, period)
    enroll_q = _base_enrollment_query(db, filters)
    official_enroll_q = enroll_q.filter(models.EnrollmentApplication.status.in_(list(_ACTIVE_STATUSES)))
    all_enroll_rows = enroll_q.all()
    official_rows = official_enroll_q.all()
    official_children_ids = {r.child_id for r in official_rows}

    classes_q = db.query(models.Class).filter(models.Class.is_active.is_(True))
    kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if filters.governorate:
        kg_q = kg_q.filter(models.Kindergarten.governorate == filters.governorate)
    if filters.city:
        kg_q = kg_q.filter(models.Kindergarten.district == filters.city)
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

    rows = _kindergarten_detail_rows(db, filters, official_children_ids, official_rows, classes, supervisors, active_assignments)

    classification_counts = {}
    for r in rows:
        cls = r["classification"]
        classification_counts[cls] = classification_counts.get(cls, 0) + 1

    return {
        "level": level.value,
        "kindergartens": rows,
        "classification_counts": classification_counts,
        "interpretation": {
            "summary": _localized(
                f"يوجد {len(rows)} روضة مصنفة ضمن النطاق المحدد.",
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
    export_format: str = Query("csv", pattern="^(csv|json|CSV|JSON)$"),
    level: ReportLevel = Query(ReportLevel.JORDAN),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
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

    if fmt == "json":
        return payload

    rows = _rows_for_export(payload)
    output = io.StringIO()
    if rows:
        headers = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _safe_csv_cell(row.get(k)) for k in headers})
    else:
        output.write("message\n")
        output.write(_safe_csv_cell("No rows available for export"))

    csv_text = "\ufeff" + output.getvalue()
    filename = f"{report_type}_{level.value}_{_today().isoformat()}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
