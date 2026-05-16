"""
خدمة التصنيف والمقارنة المعيارية للإدارة
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

import models
from cache_service import dashboard_cache
from database import get_db
from dependencies import get_current_user
from kpi_service import KPIService

router = APIRouter()

BAND_RULES = [
    ("GREEN", "أخضر", 80.0, 100.0),
    ("AMBER", "كهرماني", 60.0, 79.99),
    ("RED", "أحمر", 0.0, 59.99),
]

SUPPORTED_LEVELS = {
    "NETWORK",
    "COUNTRY",
    "GOVERNORATE",
    "CITY",
    "AREA",
    "KINDERGARTEN",
}

SUPPORTED_SIZE_MODES = {"CAPACITY", "ENROLLMENT", "CLASS_COUNT"}
SUPPORTED_SIZE_BANDS = {"SMALL", "MEDIUM", "LARGE"}
DEFAULT_COUNTRY_NAME = "الأردن"


def _ensure_admin(user: models.User) -> None:
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية المدير مطلوبة")


def _ensure_manager_only(user: models.User) -> None:
    if user.role != models.UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية مدير الروضة مطلوبة")


def _ensure_supervisor_only(user: models.User) -> None:
    if user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية المشرف مطلوبة")


def _ensure_parent_only(user: models.User) -> None:
    if user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية ولي الأمر مطلوبة")


def _normalize_period(period_start: Optional[date], period_end: Optional[date]) -> Tuple[date, date]:
    today = date.today()
    if period_end is None:
        period_end = today
    if period_start is None:
        period_start = period_end - timedelta(days=29)
    if period_start > period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="تاريخ البداية يجب أن يسبق تاريخ النهاية")
    return period_start, period_end


def _previous_period(period_start: date, period_end: date) -> Tuple[date, date]:
    days = (period_end - period_start).days + 1
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return previous_start, previous_end


def _safe_percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _band_for_score(score: Optional[float]) -> Tuple[Optional[str], str]:
    if score is None:
        return None, "غير مصنف"
    for code, label, min_value, max_value in BAND_RULES:
        if min_value <= score <= max_value:
            return code, label
    return "RED", "أحمر"


def _trend_direction(delta: Optional[float]) -> str:
    if delta is None:
        return "لا يوجد"
    if delta >= 1.0:
        return "صاعد"
    if delta <= -1.0:
        return "هابط"
    return "مستقر"


def _size_band(value: int) -> str:
    if value <= 60:
        return "SMALL"
    if value <= 120:
        return "MEDIUM"
    return "LARGE"


def _size_band_label(code: str) -> str:
    return {
        "SMALL": "صغير",
        "MEDIUM": "متوسط",
        "LARGE": "كبير",
    }.get(code, "غير محدد")


def _average(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(float(mean(values)), 2)


class ClassificationRow(BaseModel):
    entity_type: str
    entity_id: int
    display_name: str
    rank: Optional[int] = None
    percentile: Optional[float] = None
    final_score: Optional[float] = None
    band_code: Optional[str] = None
    band_label: str = "غير مصنف"
    trend_vs_previous: Optional[float] = None
    trend_direction: str = "لا يوجد"
    coverage_pct: float = 0.0
    sample_size: int = 0
    insufficient_data: bool = False
    insufficient_reason: Optional[str] = None
    peer_group_key: str
    size_band: str
    size_band_label: str
    geography: Dict[str, Optional[str]]
    aspects: Dict[str, float]


class ClassificationResponse(BaseModel):
    period_start: date
    period_end: date
    level: str
    size_mode: str
    size_band: Optional[str] = None
    applied_filters: Dict[str, Optional[str]]
    total_entities: int
    ranked_entities: int
    insufficient_entities: int
    rows: List[ClassificationRow]
    band_explanations: List[Dict[str, Any]]
    indicator_explanations: List[Dict[str, str]]


class ClassificationDetailResponse(BaseModel):
    entity_type: str
    entity_id: int
    display_name: str
    period_start: date
    period_end: date
    final_score: Optional[float]
    band_code: Optional[str]
    band_label: str
    coverage_pct: float
    aspects: Dict[str, float]
    trend_points: List[Dict[str, Any]]
    indicator_definitions: List[Dict[str, str]]
    action_guidance: List[str]


class ManagerBenchmarkSummaryResponse(BaseModel):
    period_start: date
    period_end: date
    manager_id: int
    kindergarten_id: int
    final_score: Optional[float]
    percentile: Optional[float]
    band_label: str
    peer_group_size: int
    peer_group_label: str
    anonymized_peers: List[Dict[str, Any]]
    insufficient_data: bool
    insufficient_reason: Optional[str]
    indicator_explanations: List[Dict[str, str]]


class SupervisorPerformanceSummaryResponse(BaseModel):
    period_start: date
    period_end: date
    supervisor_id: int
    final_score: Optional[float]
    band_label: str
    coverage_pct: float
    sample_size: int
    aspects: Dict[str, float]
    insufficient_data: bool
    insufficient_reason: Optional[str]
    indicator_explanations: List[Dict[str, str]]


class ParentQualityBandResponse(BaseModel):
    kindergarten_id: int
    kindergarten_name: str
    period_start: date
    period_end: date
    governance_score: Optional[float]
    band_label: str
    explanation: str


class ClassificationFiltersResponse(BaseModel):
    levels: List[Dict[str, str]]
    size_modes: List[Dict[str, str]]
    size_bands: List[Dict[str, str]]
    countries: List[str]
    governorates: List[str]
    cities: List[str]
    areas: List[str]


class DataCoverageService:
    @staticmethod
    def coverage_from_bundle(bundle: Dict[str, Any]) -> float:
        quality = bundle.get("quality", {})
        if not quality:
            return 0.0
        coverage_values: List[float] = []
        for metric in (
            "attendance_rate",
            "ratio_compliance",
            "report_submission_rate",
            "training_completion_rate",
            "incident_followup_sla",
            "parent_satisfaction",
            "governance_score",
        ):
            item = quality.get(metric)
            if item is None:
                continue
            coverage_values.append(float(item.get("coverage_pct", 0.0) or 0.0))
        return _average(coverage_values)


class BenchmarkingService:
    @staticmethod
    def _has_country_column() -> bool:
        return "country" in models.Kindergarten.__table__.columns.keys()

    @staticmethod
    def _kg_country(kg: models.Kindergarten) -> str:
        if BenchmarkingService._has_country_column():
            value = getattr(kg, "country", None)
            if value:
                return str(value)
        return DEFAULT_COUNTRY_NAME

    @staticmethod
    def _get_kindergarten_scope(
        db: Session,
        *,
        level: str,
        level_value: Optional[str],
        country: Optional[str],
        governorate: Optional[str],
        city: Optional[str],
        area: Optional[str],
        kindergarten_id: Optional[int],
    ) -> List[models.Kindergarten]:
        query = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )

        has_country_column = BenchmarkingService._has_country_column()

        if level_value:
            if level == "COUNTRY":
                if has_country_column:
                    query = query.filter(models.Kindergarten.country == level_value)
                elif level_value != DEFAULT_COUNTRY_NAME:
                    return []
            elif level == "GOVERNORATE":
                query = query.filter(models.Kindergarten.governorate == level_value)
            elif level == "CITY":
                query = query.filter(models.Kindergarten.city == level_value)
            elif level == "AREA":
                query = query.filter(models.Kindergarten.area == level_value)
            elif level == "KINDERGARTEN":
                try:
                    query = query.filter(models.Kindergarten.id == int(level_value))
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="معرف الروضة غير صحيح") from exc

        if country:
            if has_country_column:
                query = query.filter(models.Kindergarten.country == country)
            elif country != DEFAULT_COUNTRY_NAME:
                return []
        if governorate:
            query = query.filter(models.Kindergarten.governorate == governorate)
        if city:
            query = query.filter(models.Kindergarten.city == city)
        if area:
            query = query.filter(models.Kindergarten.area == area)
        if kindergarten_id:
            query = query.filter(models.Kindergarten.id == kindergarten_id)

        return query.order_by(models.Kindergarten.name_ar.asc()).all()

    @staticmethod
    def _size_stats_by_kindergarten(db: Session, kindergarten_ids: List[int]) -> Dict[int, Dict[str, int]]:
        if not kindergarten_ids:
            return {}

        class_rows = db.query(
            models.Class.kindergarten_id,
            func.count(models.Class.id).label("class_count"),
            func.sum(models.Class.capacity_total).label("capacity_total"),
        ).filter(
            models.Class.kindergarten_id.in_(kindergarten_ids),
            models.Class.is_active == True,
        ).group_by(models.Class.kindergarten_id).all()

        enrollment_rows = db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id).label("active_enrollments"),
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all()

        stats: Dict[int, Dict[str, int]] = {
            kg_id: {"class_count": 0, "capacity_total": 0, "active_enrollments": 0}
            for kg_id in kindergarten_ids
        }
        for row in class_rows:
            stats[row.kindergarten_id]["class_count"] = int(row.class_count or 0)
            stats[row.kindergarten_id]["capacity_total"] = int(row.capacity_total or 0)
        for row in enrollment_rows:
            stats[row.kindergarten_id]["active_enrollments"] = int(row.active_enrollments or 0)
        return stats

    @staticmethod
    def _size_band_for_kindergarten(size_mode: str, stats: Dict[str, int]) -> str:
        if size_mode == "CAPACITY":
            return _size_band(int(stats.get("capacity_total", 0)))
        if size_mode == "ENROLLMENT":
            return _size_band(int(stats.get("active_enrollments", 0)))
        return _size_band(int(stats.get("class_count", 0)))

    @staticmethod
    def _peer_group_key(
        kg: models.Kindergarten,
        level: str,
        size_mode: str,
        size_band: str,
    ) -> str:
        country_name = BenchmarkingService._kg_country(kg)
        if level == "NETWORK":
            geo_part = "الشبكة"
        elif level == "COUNTRY":
            geo_part = f"{country_name}"
        elif level == "GOVERNORATE":
            geo_part = f"{country_name}|{kg.governorate}"
        elif level == "CITY":
            geo_part = f"{country_name}|{kg.governorate}|{kg.city}"
        elif level == "AREA":
            geo_part = f"{country_name}|{kg.governorate}|{kg.city}|{kg.area}"
        else:
            geo_part = f"KG:{kg.id}"
        return f"{geo_part}|{size_mode}:{size_band}"

    @staticmethod
    def _bundle(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        cache_key = f"classification:bundle:{kindergarten_id}:{period_start}:{period_end}"
        cached = dashboard_cache.get(cache_key)
        if cached:
            return cached

        bundle = KPIService.compute_kpi_bundle(db, kindergarten_id, period_start, period_end)
        expected_days, _, _ = KPIService._count_expected_child_days(db, kindergarten_id, period_start, period_end)
        bundle["expected_child_days"] = int(expected_days)
        bundle["coverage_pct_total"] = DataCoverageService.coverage_from_bundle(bundle)
        dashboard_cache.set(cache_key, bundle, ttl_seconds=3600)
        return bundle

    @staticmethod
    def _rank_rows(rows: List[ClassificationRow]) -> None:
        grouped: Dict[str, List[ClassificationRow]] = defaultdict(list)
        for row in rows:
            if row.insufficient_data or row.final_score is None:
                continue
            grouped[row.peer_group_key].append(row)

        for group_rows in grouped.values():
            group_rows.sort(key=lambda item: float(item.final_score or 0.0), reverse=True)
            total = len(group_rows)
            for index, row in enumerate(group_rows, start=1):
                row.rank = index
                row.percentile = round(((total - index + 1) / total) * 100.0, 2)
                row.band_code, row.band_label = _band_for_score(row.final_score)

    @staticmethod
    def _indicator_explanations() -> List[Dict[str, str]]:
        return [
            {
                "indicator": "الألوان",
                "meaning": "أخضر: أداء قوي، كهرماني: يحتاج متابعة، أحمر: يحتاج تدخل فوري",
            },
            {
                "indicator": "السهم",
                "meaning": "يعرض التغير مقارنة بالفترة السابقة بنفس الطول الزمني",
            },
            {
                "indicator": "تغطية البيانات",
                "meaning": "تمثل نسبة اكتمال البيانات المؤثرة في حساب المؤشر؛ كلما ارتفعت كانت النتيجة أكثر موثوقية",
            },
        ]

    @staticmethod
    def _band_explanations() -> List[Dict[str, Any]]:
        return [
            {"code": code, "label": label, "min": min_value, "max": max_value}
            for code, label, min_value, max_value in BAND_RULES
        ]

    @staticmethod
    def get_kindergarten_leaderboard(
        db: Session,
        *,
        period_start: date,
        period_end: date,
        level: str,
        level_value: Optional[str],
        size_mode: str,
        size_band: Optional[str],
        country: Optional[str],
        governorate: Optional[str],
        city: Optional[str],
        area: Optional[str],
        kindergarten_id: Optional[int],
        min_sample_days: int,
    ) -> ClassificationResponse:
        kindergartens = BenchmarkingService._get_kindergarten_scope(
            db,
            level=level,
            level_value=level_value,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            kindergarten_id=kindergarten_id,
        )
        if not kindergartens:
            return ClassificationResponse(
                period_start=period_start,
                period_end=period_end,
                level=level,
                size_mode=size_mode,
                size_band=size_band,
                applied_filters={
                    "country": country,
                    "governorate": governorate,
                    "city": city,
                    "area": area,
                    "level_value": level_value,
                },
                total_entities=0,
                ranked_entities=0,
                insufficient_entities=0,
                rows=[],
                band_explanations=BenchmarkingService._band_explanations(),
                indicator_explanations=BenchmarkingService._indicator_explanations(),
            )

        kg_ids = [kg.id for kg in kindergartens]
        size_stats = BenchmarkingService._size_stats_by_kindergarten(db, kg_ids)
        previous_start, previous_end = _previous_period(period_start, period_end)

        rows: List[ClassificationRow] = []
        for kg in kindergartens:
            stats = size_stats.get(kg.id, {"class_count": 0, "capacity_total": 0, "active_enrollments": 0})
            computed_size_band = BenchmarkingService._size_band_for_kindergarten(size_mode, stats)
            if size_band and computed_size_band != size_band:
                continue

            current_bundle = BenchmarkingService._bundle(db, kg.id, period_start, period_end)
            previous_bundle = BenchmarkingService._bundle(db, kg.id, previous_start, previous_end)
            coverage_pct = float(current_bundle.get("coverage_pct_total", 0.0))
            sample_size = int(current_bundle.get("expected_child_days", 0))

            insufficient_reason = None
            insufficient_data = False
            if sample_size < min_sample_days:
                insufficient_data = True
                insufficient_reason = "عدد الأيام التعليمية المحتسبة أقل من الحد الأدنى للتصنيف"
            elif coverage_pct < 40.0:
                insufficient_data = True
                insufficient_reason = "تغطية البيانات منخفضة ولا تسمح بمقارنة عادلة"

            final_score = None if insufficient_data else float(current_bundle.get("governance_score", 0.0))
            previous_score = float(previous_bundle.get("governance_score", 0.0)) if previous_bundle else None
            trend = None if final_score is None or previous_score is None else round(final_score - previous_score, 2)

            peer_key = BenchmarkingService._peer_group_key(kg, level, size_mode, computed_size_band)
            row = ClassificationRow(
                entity_type="KINDERGARTEN",
                entity_id=kg.id,
                display_name=kg.name_ar or kg.name_en or f"روضة {kg.id}",
                final_score=round(final_score, 2) if final_score is not None else None,
                trend_vs_previous=trend,
                trend_direction=_trend_direction(trend),
                coverage_pct=coverage_pct,
                sample_size=sample_size,
                insufficient_data=insufficient_data,
                insufficient_reason=insufficient_reason,
                peer_group_key=peer_key,
                size_band=computed_size_band,
                size_band_label=_size_band_label(computed_size_band),
                geography={
                    "country": BenchmarkingService._kg_country(kg),
                    "governorate": kg.governorate,
                    "city": kg.city,
                    "area": kg.area,
                },
                aspects={
                    "الحوكمة": float(current_bundle.get("gqi_score", 0.0)),
                    "تجربة_الطفل": float(current_bundle.get("cei_score", 0.0)),
                    "التشغيل": _average([
                        float(current_bundle.get("attendance_rate", 0.0)),
                        float(current_bundle.get("ratio_compliance", 0.0)),
                        float(current_bundle.get("report_submission_rate", 0.0)),
                    ]),
                    "الجودة": _average([
                        float(current_bundle.get("training_completion_rate", 0.0)),
                        float(current_bundle.get("incident_followup_sla", 0.0)),
                        float(current_bundle.get("checklist_compliance", 0.0)),
                    ]),
                    "التفاعل": _average([
                        float(current_bundle.get("parent_satisfaction", 0.0)),
                        float(current_bundle.get("parent_response_rate", 0.0)),
                    ]),
                },
            )
            rows.append(row)

        BenchmarkingService._rank_rows(rows)
        rows.sort(
            key=lambda r: (
                1 if r.rank is None else 0,
                r.rank if r.rank is not None else 999999,
                -(r.final_score or 0.0),
            )
        )
        ranked_count = sum(1 for row in rows if row.rank is not None)
        insufficient_count = sum(1 for row in rows if row.insufficient_data)

        return ClassificationResponse(
            period_start=period_start,
            period_end=period_end,
            level=level,
            size_mode=size_mode,
            size_band=size_band,
            applied_filters={
                "country": country,
                "governorate": governorate,
                "city": city,
                "area": area,
                "level_value": level_value,
            },
            total_entities=len(rows),
            ranked_entities=ranked_count,
            insufficient_entities=insufficient_count,
            rows=rows,
            band_explanations=BenchmarkingService._band_explanations(),
            indicator_explanations=BenchmarkingService._indicator_explanations(),
        )

    @staticmethod
    def _supervisor_assignments(
        db: Session,
        supervisor_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {sid: {"classes": set(), "kindergarten_id": None} for sid in supervisor_ids}
        if not supervisor_ids:
            return out

        direct_rows = db.query(
            models.Class.id,
            models.Class.supervisor_id,
            models.Class.kindergarten_id,
        ).filter(
            models.Class.supervisor_id.in_(supervisor_ids),
            models.Class.is_active == True,
        ).all()
        for class_id, supervisor_id, kindergarten_id in direct_rows:
            out.setdefault(supervisor_id, {"classes": set(), "kindergarten_id": None})
            out[supervisor_id]["classes"].add(class_id)
            out[supervisor_id]["kindergarten_id"] = kindergarten_id

        assignment_rows = db.query(
            models.SupervisorAssignment.supervisor_id,
            models.SupervisorAssignment.class_id,
            models.Class.kindergarten_id,
        ).join(
            models.Class,
            models.Class.id == models.SupervisorAssignment.class_id,
        ).filter(
            models.SupervisorAssignment.supervisor_id.in_(supervisor_ids),
            models.SupervisorAssignment.start_date <= period_end,
            or_(
                models.SupervisorAssignment.end_date.is_(None),
                models.SupervisorAssignment.end_date >= period_start,
            ),
            models.Class.is_active == True,
        ).all()
        for supervisor_id, class_id, kindergarten_id in assignment_rows:
            out.setdefault(supervisor_id, {"classes": set(), "kindergarten_id": None})
            out[supervisor_id]["classes"].add(class_id)
            out[supervisor_id]["kindergarten_id"] = kindergarten_id
        return out

    @staticmethod
    def _open_days_by_kindergarten(db: Session, kindergarten_ids: List[int], period_start: date, period_end: date) -> Dict[int, int]:
        rows = db.query(
            models.OperatingCalendar.kindergarten_id,
            func.count(models.OperatingCalendar.id).label("open_days"),
        ).filter(
            models.OperatingCalendar.kindergarten_id.in_(kindergarten_ids),
            models.OperatingCalendar.date >= period_start,
            models.OperatingCalendar.date <= period_end,
            models.OperatingCalendar.is_open == True,
        ).group_by(models.OperatingCalendar.kindergarten_id).all()
        result = {int(row.kindergarten_id): int(row.open_days or 0) for row in rows}

        weekday_fallback = 0
        current = period_start
        while current <= period_end:
            if current.weekday() < 5:
                weekday_fallback += 1
            current += timedelta(days=1)
        for kg_id in kindergarten_ids:
            result.setdefault(kg_id, weekday_fallback)
        return result

    @staticmethod
    def get_supervisor_leaderboard(
        db: Session,
        *,
        period_start: date,
        period_end: date,
        level: str,
        level_value: Optional[str],
        size_mode: str,
        size_band: Optional[str],
        country: Optional[str],
        governorate: Optional[str],
        city: Optional[str],
        area: Optional[str],
        min_sample_days: int,
    ) -> ClassificationResponse:
        kg_scope = BenchmarkingService._get_kindergarten_scope(
            db,
            level=level,
            level_value=level_value,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            kindergarten_id=None,
        )
        if not kg_scope:
            return ClassificationResponse(
                period_start=period_start,
                period_end=period_end,
                level=level,
                size_mode=size_mode,
                size_band=size_band,
                applied_filters={"country": country, "governorate": governorate, "city": city, "area": area, "level_value": level_value},
                total_entities=0,
                ranked_entities=0,
                insufficient_entities=0,
                rows=[],
                band_explanations=BenchmarkingService._band_explanations(),
                indicator_explanations=BenchmarkingService._indicator_explanations(),
            )

        kg_ids = [kg.id for kg in kg_scope]
        size_stats = BenchmarkingService._size_stats_by_kindergarten(db, kg_ids)
        kg_index = {kg.id: kg for kg in kg_scope}

        supervisor_users = db.query(models.User).filter(
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.kindergarten_id.in_(kg_ids),
        ).all()
        supervisor_ids = [user.id for user in supervisor_users]
        assignments = BenchmarkingService._supervisor_assignments(db, supervisor_ids, period_start, period_end)

        all_assigned_class_ids = sorted(
            {
                class_id
                for item in assignments.values()
                for class_id in item.get("classes", set())
            }
        )
        open_days_map = BenchmarkingService._open_days_by_kindergarten(db, kg_ids, period_start, period_end)

        enroll_rows = db.query(
            models.EnrollmentApplication.class_id,
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id).label("children_count"),
        ).filter(
            models.EnrollmentApplication.class_id.in_(all_assigned_class_ids if all_assigned_class_ids else [-1]),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).group_by(
            models.EnrollmentApplication.class_id,
            models.EnrollmentApplication.kindergarten_id,
        ).all()
        expected_by_class: Dict[int, int] = {}
        for row in enroll_rows:
            expected_by_class[int(row.class_id)] = int(row.children_count or 0) * int(open_days_map.get(int(row.kindergarten_id), 0))

        attendance_rows = db.query(
            models.AttendanceLog.recorded_by,
            func.count(models.AttendanceLog.id).label("log_count"),
        ).filter(
            models.AttendanceLog.recorded_by.in_(supervisor_ids if supervisor_ids else [-1]),
            models.AttendanceLog.class_id.in_(all_assigned_class_ids if all_assigned_class_ids else [-1]),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
        ).group_by(models.AttendanceLog.recorded_by).all()
        attendance_by_supervisor = {int(row.recorded_by): int(row.log_count or 0) for row in attendance_rows}

        subq = db.query(
            models.EnrollmentApplication.child_id.label("child_id"),
            models.EnrollmentApplication.class_id.label("class_id"),
        ).filter(
            models.EnrollmentApplication.class_id.in_(all_assigned_class_ids if all_assigned_class_ids else [-1]),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            or_(
                models.EnrollmentApplication.enrollment_end_date.is_(None),
                models.EnrollmentApplication.enrollment_end_date >= period_start,
            ),
            or_(
                models.EnrollmentApplication.enrollment_start_date.is_(None),
                models.EnrollmentApplication.enrollment_start_date <= period_end,
            ),
        ).subquery()

        report_rows = db.query(
            models.DailyReport.submitted_by,
            func.count(func.distinct(models.DailyReport.id)).label("submitted_count"),
            func.sum(
                case(
                    (
                        and_(
                            models.DailyReport.submitted_at.isnot(None),
                            func.date(models.DailyReport.submitted_at) <= models.DailyReport.date,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("timely_count"),
        ).join(
            subq,
            subq.c.child_id == models.DailyReport.child_id,
        ).filter(
            models.DailyReport.submitted_by.in_(supervisor_ids if supervisor_ids else [-1]),
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
        ).group_by(models.DailyReport.submitted_by).all()
        report_by_supervisor = {
            int(row.submitted_by): {
                "submitted": int(row.submitted_count or 0),
                "timely": int(row.timely_count or 0),
            }
            for row in report_rows
        }

        rows: List[ClassificationRow] = []
        for supervisor in supervisor_users:
            assignment = assignments.get(supervisor.id, {"classes": set(), "kindergarten_id": supervisor.kindergarten_id})
            class_ids = list(assignment.get("classes", set()))
            supervisor_kg_id = int(assignment.get("kindergarten_id") or supervisor.kindergarten_id or 0)
            kg = kg_index.get(supervisor_kg_id)
            if not kg:
                continue

            stats = size_stats.get(supervisor_kg_id, {"class_count": 0, "capacity_total": 0, "active_enrollments": 0})
            computed_size_band = BenchmarkingService._size_band_for_kindergarten(size_mode, stats)
            if size_band and computed_size_band != size_band:
                continue

            expected_total = sum(expected_by_class.get(class_id, 0) for class_id in class_ids)
            attendance_count = int(attendance_by_supervisor.get(supervisor.id, 0))
            report_data = report_by_supervisor.get(supervisor.id, {"submitted": 0, "timely": 0})
            submitted_count = int(report_data["submitted"])
            timely_count = int(report_data["timely"])

            attendance_rate = min(_safe_percent(float(attendance_count), float(expected_total)), 100.0) if expected_total > 0 else 0.0
            report_rate = min(_safe_percent(float(submitted_count), float(expected_total)), 100.0) if expected_total > 0 else 0.0
            timeliness_rate = _safe_percent(float(timely_count), float(submitted_count)) if submitted_count > 0 else 0.0

            components = [
                (attendance_rate, 0.4, expected_total > 0),
                (report_rate, 0.4, expected_total > 0),
                (timeliness_rate, 0.2, submitted_count > 0),
            ]
            weight_sum = sum(weight for _, weight, enabled in components if enabled)
            final_score = (
                round(sum(value * weight for value, weight, enabled in components if enabled) / weight_sum, 2)
                if weight_sum > 0
                else None
            )

            coverage_pct = _average([attendance_rate, report_rate])
            insufficient_data = False
            reason = None
            if expected_total < min_sample_days:
                insufficient_data = True
                reason = "حجم البيانات الصفية أقل من الحد الأدنى للمقارنة"
            elif coverage_pct < 40.0:
                insufficient_data = True
                reason = "تغطية إدخال الحضور والتقارير منخفضة"
            if insufficient_data:
                final_score = None

            peer_key = BenchmarkingService._peer_group_key(kg, level, size_mode, computed_size_band)
            band_code, band_label = _band_for_score(final_score)
            rows.append(
                ClassificationRow(
                    entity_type="SUPERVISOR",
                    entity_id=supervisor.id,
                    display_name=supervisor.full_name or supervisor.username,
                    final_score=final_score,
                    band_code=band_code,
                    band_label=band_label,
                    trend_vs_previous=None,
                    trend_direction="لا يوجد",
                    coverage_pct=coverage_pct,
                    sample_size=expected_total,
                    insufficient_data=insufficient_data,
                    insufficient_reason=reason,
                    peer_group_key=peer_key,
                    size_band=computed_size_band,
                    size_band_label=_size_band_label(computed_size_band),
                    geography={
                        "country": BenchmarkingService._kg_country(kg),
                        "governorate": kg.governorate,
                        "city": kg.city,
                        "area": kg.area,
                    },
                    aspects={
                        "اكتمال_الحضور": attendance_rate,
                        "اكتمال_التقارير": report_rate,
                        "الالتزام_بالوقت": timeliness_rate,
                    },
                )
            )

        BenchmarkingService._rank_rows(rows)
        rows.sort(
            key=lambda r: (
                1 if r.rank is None else 0,
                r.rank if r.rank is not None else 999999,
                -(r.final_score or 0.0),
            )
        )

        return ClassificationResponse(
            period_start=period_start,
            period_end=period_end,
            level=level,
            size_mode=size_mode,
            size_band=size_band,
            applied_filters={
                "country": country,
                "governorate": governorate,
                "city": city,
                "area": area,
                "level_value": level_value,
            },
            total_entities=len(rows),
            ranked_entities=sum(1 for row in rows if row.rank is not None),
            insufficient_entities=sum(1 for row in rows if row.insufficient_data),
            rows=rows,
            band_explanations=BenchmarkingService._band_explanations(),
            indicator_explanations=BenchmarkingService._indicator_explanations(),
        )

    @staticmethod
    def _manager_review_metrics(
        db: Session,
        manager_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> Dict[int, Dict[str, float]]:
        metrics = {manager_id: {"reviewed": 0, "on_time": 0, "rejected": 0} for manager_id in manager_ids}
        if not manager_ids:
            return metrics

        rows = db.query(
            models.DailyReport.approved_by,
            models.DailyReport.submitted_at,
            models.DailyReport.approved_at,
            models.DailyReport.status,
        ).filter(
            models.DailyReport.approved_by.in_(manager_ids),
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
        ).all()

        for approved_by, submitted_at, approved_at, status_value in rows:
            if approved_by is None:
                continue
            metrics.setdefault(approved_by, {"reviewed": 0, "on_time": 0, "rejected": 0})
            metrics[approved_by]["reviewed"] += 1
            if submitted_at and approved_at and (approved_at - submitted_at) <= timedelta(hours=24):
                metrics[approved_by]["on_time"] += 1
            if status_value in {models.DailyReportStatus.REJECTED, models.DailyReportStatus.RETURNED}:
                metrics[approved_by]["rejected"] += 1
        return metrics

    @staticmethod
    def get_manager_leaderboard(
        db: Session,
        *,
        period_start: date,
        period_end: date,
        level: str,
        level_value: Optional[str],
        size_mode: str,
        size_band: Optional[str],
        country: Optional[str],
        governorate: Optional[str],
        city: Optional[str],
        area: Optional[str],
        min_sample_days: int,
    ) -> ClassificationResponse:
        kg_result = BenchmarkingService.get_kindergarten_leaderboard(
            db,
            period_start=period_start,
            period_end=period_end,
            level=level,
            level_value=level_value,
            size_mode=size_mode,
            size_band=size_band,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            kindergarten_id=None,
            min_sample_days=min_sample_days,
        )
        kg_map = {row.entity_id: row for row in kg_result.rows}
        if not kg_map:
            kg_result.rows = []
            kg_result.total_entities = 0
            kg_result.ranked_entities = 0
            return kg_result

        manager_rows = db.query(models.User).filter(
            models.User.role == models.UserRole.MANAGER,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.kindergarten_id.in_(list(kg_map.keys())),
        ).all()
        manager_ids = [item.id for item in manager_rows]
        review_metrics = BenchmarkingService._manager_review_metrics(db, manager_ids, period_start, period_end)

        expected_reviews_by_kg = {
            row.kindergarten_id: int(row.count_value or 0)
            for row in db.query(
                models.DailyReport.kindergarten_id,
                func.count(models.DailyReport.id).label("count_value"),
            ).filter(
                models.DailyReport.kindergarten_id.in_(list(kg_map.keys())),
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
                models.DailyReport.status.in_([
                    models.DailyReportStatus.SUBMITTED,
                    models.DailyReportStatus.APPROVED,
                    models.DailyReportStatus.SENT_TO_PARENT,
                    models.DailyReportStatus.REJECTED,
                    models.DailyReportStatus.RETURNED,
                ]),
            ).group_by(models.DailyReport.kindergarten_id).all()
        }

        rows: List[ClassificationRow] = []
        for manager in manager_rows:
            kg_row = kg_map.get(int(manager.kindergarten_id or 0))
            if not kg_row:
                continue
            manager_metric = review_metrics.get(manager.id, {"reviewed": 0, "on_time": 0, "rejected": 0})
            reviewed = int(manager_metric["reviewed"])
            on_time_rate = _safe_percent(float(manager_metric["on_time"]), float(reviewed))
            quality_rate = 100.0 - _safe_percent(float(manager_metric["rejected"]), float(reviewed))
            expected_reviews = int(expected_reviews_by_kg.get(int(manager.kindergarten_id or 0), 0))
            coverage_pct = _safe_percent(float(reviewed), float(expected_reviews)) if expected_reviews > 0 else 0.0

            components: List[Tuple[float, float, bool]] = [
                (float(kg_row.final_score or 0.0), 0.6, kg_row.final_score is not None),
                (on_time_rate, 0.2, reviewed > 0),
                (quality_rate, 0.2, reviewed > 0),
            ]
            weight_sum = sum(weight for _, weight, enabled in components if enabled)
            final_score = (
                round(sum(value * weight for value, weight, enabled in components if enabled) / weight_sum, 2)
                if weight_sum > 0
                else None
            )

            insufficient_data = False
            reason = None
            if expected_reviews < min_sample_days:
                insufficient_data = True
                reason = "عدد التقارير الإدارية في الفترة أقل من الحد الأدنى للمقارنة"
            elif coverage_pct < 40.0:
                insufficient_data = True
                reason = "تغطية إجراءات الاعتماد منخفضة ولا تسمح بمقارنة عادلة"

            if insufficient_data:
                final_score = None

            band_code, band_label = _band_for_score(final_score)
            rows.append(
                ClassificationRow(
                    entity_type="MANAGER",
                    entity_id=manager.id,
                    display_name=manager.full_name or manager.username,
                    final_score=final_score,
                    band_code=band_code,
                    band_label=band_label,
                    trend_vs_previous=kg_row.trend_vs_previous,
                    trend_direction=kg_row.trend_direction,
                    coverage_pct=round(_average([kg_row.coverage_pct, coverage_pct]), 2),
                    sample_size=reviewed,
                    insufficient_data=insufficient_data,
                    insufficient_reason=reason,
                    peer_group_key=kg_row.peer_group_key,
                    size_band=kg_row.size_band,
                    size_band_label=kg_row.size_band_label,
                    geography=kg_row.geography,
                    aspects={
                        "حوكمة_الروضة": float(kg_row.final_score or 0.0),
                        "سرعة_الاعتماد": on_time_rate,
                        "جودة_المراجعة": quality_rate,
                    },
                )
            )

        BenchmarkingService._rank_rows(rows)
        rows.sort(
            key=lambda r: (
                1 if r.rank is None else 0,
                r.rank if r.rank is not None else 999999,
                -(r.final_score or 0.0),
            )
        )

        return ClassificationResponse(
            period_start=period_start,
            period_end=period_end,
            level=level,
            size_mode=size_mode,
            size_band=size_band,
            applied_filters={
                "country": country,
                "governorate": governorate,
                "city": city,
                "area": area,
                "level_value": level_value,
            },
            total_entities=len(rows),
            ranked_entities=sum(1 for row in rows if row.rank is not None),
            insufficient_entities=sum(1 for row in rows if row.insufficient_data),
            rows=rows,
            band_explanations=BenchmarkingService._band_explanations(),
            indicator_explanations=BenchmarkingService._indicator_explanations(),
        )


def _validate_common_filters(level: str, size_mode: str, size_band: Optional[str]) -> None:
    if level not in SUPPORTED_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="مستوى المقارنة غير مدعوم")
    if size_mode not in SUPPORTED_SIZE_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="نوع شريحة الحجم غير مدعوم")
    if size_band and size_band not in SUPPORTED_SIZE_BANDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="شريحة الحجم غير مدعومة")


def _row_by_entity_id(rows: List[ClassificationRow], entity_id: int) -> Optional[ClassificationRow]:
    for row in rows:
        if int(row.entity_id) == int(entity_id):
            return row
    return None


def _actions_from_aspects(aspects: Dict[str, float]) -> List[str]:
    actions: List[str] = []
    for key, value in aspects.items():
        if value >= 80:
            continue
        if "الحضور" in key:
            actions.append("رفع اكتمال إدخال الحضور اليومي وتقليل التأخير في التوثيق.")
        elif "التقارير" in key:
            actions.append("متابعة تسليم التقارير اليومية واعتمادها خلال 24 ساعة.")
        elif "الوقت" in key:
            actions.append("تحسين الالتزام بزمن الاعتماد ومراجعة أسباب التأخير.")
        elif "الجودة" in key:
            actions.append("تنفيذ خطة تحسين جودة الممارسات الصفية والتوثيق.")
        elif "التفاعل" in key:
            actions.append("زيادة تفاعل أولياء الأمور عبر الاستبيانات والتغذية الراجعة.")
        elif "الحوكمة" in key:
            actions.append("رفع انضباط الحوكمة عبر الالتزام بالسياسات ومتابعة مؤشرات المخاطر.")
        else:
            actions.append("تنفيذ خطة تحسين لهذا المؤشر ومراجعته أسبوعياً.")
    if not actions:
        actions.append("الاستمرار على نفس النهج مع مراقبة الاستقرار شهرياً.")
    return actions[:5]


def _build_trend_points(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    period_start: date,
    period_end: date,
    level: str,
    level_value: Optional[str],
    size_mode: str,
    size_band: Optional[str],
    country: Optional[str],
    governorate: Optional[str],
    city: Optional[str],
    area: Optional[str],
    min_sample_days: int,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    window_days = (period_end - period_start).days + 1
    if window_days <= 0:
        return []

    points: List[Dict[str, Any]] = []
    current_end = period_end
    for _ in range(periods):
        current_start = current_end - timedelta(days=window_days - 1)
        if entity_type == "KINDERGARTEN":
            response = BenchmarkingService.get_kindergarten_leaderboard(
                db,
                period_start=current_start,
                period_end=current_end,
                level=level,
                level_value=level_value,
                size_mode=size_mode,
                size_band=size_band,
                country=country,
                governorate=governorate,
                city=city,
                area=area,
                kindergarten_id=entity_id,
                min_sample_days=min_sample_days,
            )
        elif entity_type == "MANAGER":
            response = BenchmarkingService.get_manager_leaderboard(
                db,
                period_start=current_start,
                period_end=current_end,
                level=level,
                level_value=level_value,
                size_mode=size_mode,
                size_band=size_band,
                country=country,
                governorate=governorate,
                city=city,
                area=area,
                min_sample_days=min_sample_days,
            )
        else:
            response = BenchmarkingService.get_supervisor_leaderboard(
                db,
                period_start=current_start,
                period_end=current_end,
                level=level,
                level_value=level_value,
                size_mode=size_mode,
                size_band=size_band,
                country=country,
                governorate=governorate,
                city=city,
                area=area,
                min_sample_days=min_sample_days,
            )

        row = _row_by_entity_id(response.rows, entity_id)
        points.append(
            {
                "period_start": current_start,
                "period_end": current_end,
                "final_score": row.final_score if row else None,
                "coverage_pct": row.coverage_pct if row else 0.0,
            }
        )
        current_end = current_start - timedelta(days=1)

    points.reverse()
    return points


def _load_filters(db: Session) -> ClassificationFiltersResponse:
    levels = [
        {"value": "NETWORK", "label": "الشبكة"},
        {"value": "COUNTRY", "label": "الدولة"},
        {"value": "GOVERNORATE", "label": "المحافظة"},
        {"value": "CITY", "label": "المدينة"},
        {"value": "AREA", "label": "المنطقة"},
        {"value": "KINDERGARTEN", "label": "الروضة"},
    ]
    size_modes = [
        {"value": "CAPACITY", "label": "حسب السعة"},
        {"value": "ENROLLMENT", "label": "حسب عدد الملتحقين"},
        {"value": "CLASS_COUNT", "label": "حسب عدد الصفوف"},
    ]
    size_bands = [
        {"value": "SMALL", "label": "صغير"},
        {"value": "MEDIUM", "label": "متوسط"},
        {"value": "LARGE", "label": "كبير"},
    ]

    has_country_column = BenchmarkingService._has_country_column()
    if has_country_column:
        country_rows = db.query(models.Kindergarten.country).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            models.Kindergarten.country.isnot(None),
            models.Kindergarten.country != "",
        ).distinct().all()
        countries = sorted({str(row[0]) for row in country_rows if row and row[0]})
        if not countries:
            countries = [DEFAULT_COUNTRY_NAME]
    else:
        countries = [DEFAULT_COUNTRY_NAME]

    governorates = sorted(
        {
            str(row[0]) for row in db.query(models.Kindergarten.governorate).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).distinct().all()
            if row and row[0]
        }
    )
    cities = sorted(
        {
            str(row[0]) for row in db.query(models.Kindergarten.city).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).distinct().all()
            if row and row[0]
        }
    )
    areas = sorted(
        {
            str(row[0]) for row in db.query(models.Kindergarten.area).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).distinct().all()
            if row and row[0]
        }
    )

    return ClassificationFiltersResponse(
        levels=levels,
        size_modes=size_modes,
        size_bands=size_bands,
        countries=countries,
        governorates=governorates,
        cities=cities,
        areas=areas,
    )


@router.get("/admin/classification/filters", response_model=ClassificationFiltersResponse)
def get_admin_classification_filters(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    return _load_filters(db)


@router.get("/admin/classification/kindergartens", response_model=ClassificationResponse)
def get_admin_kindergarten_leaderboard(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    level: str = Query("NETWORK"),
    level_value: Optional[str] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    _validate_common_filters(level, size_mode, size_band)
    period_start, period_end = _normalize_period(period_start, period_end)
    return BenchmarkingService.get_kindergarten_leaderboard(
        db,
        period_start=period_start,
        period_end=period_end,
        level=level,
        level_value=level_value,
        size_mode=size_mode,
        size_band=size_band,
        country=country,
        governorate=governorate,
        city=city,
        area=area,
        kindergarten_id=kindergarten_id,
        min_sample_days=min_sample_days,
    )


@router.get("/admin/classification/managers", response_model=ClassificationResponse)
def get_admin_manager_leaderboard(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    level: str = Query("NETWORK"),
    level_value: Optional[str] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    _validate_common_filters(level, size_mode, size_band)
    period_start, period_end = _normalize_period(period_start, period_end)
    return BenchmarkingService.get_manager_leaderboard(
        db,
        period_start=period_start,
        period_end=period_end,
        level=level,
        level_value=level_value,
        size_mode=size_mode,
        size_band=size_band,
        country=country,
        governorate=governorate,
        city=city,
        area=area,
        min_sample_days=min_sample_days,
    )


@router.get("/admin/classification/supervisors", response_model=ClassificationResponse)
def get_admin_supervisor_leaderboard(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    level: str = Query("NETWORK"),
    level_value: Optional[str] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    _validate_common_filters(level, size_mode, size_band)
    period_start, period_end = _normalize_period(period_start, period_end)
    return BenchmarkingService.get_supervisor_leaderboard(
        db,
        period_start=period_start,
        period_end=period_end,
        level=level,
        level_value=level_value,
        size_mode=size_mode,
        size_band=size_band,
        country=country,
        governorate=governorate,
        city=city,
        area=area,
        min_sample_days=min_sample_days,
    )


@router.get("/admin/classification/detail", response_model=ClassificationDetailResponse)
def get_admin_classification_detail(
    entity_type: str = Query(..., pattern="^(KINDERGARTEN|MANAGER|SUPERVISOR)$"),
    entity_id: int = Query(..., ge=1),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    level: str = Query("NETWORK"),
    level_value: Optional[str] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    _validate_common_filters(level, size_mode, size_band)
    period_start, period_end = _normalize_period(period_start, period_end)

    if entity_type == "KINDERGARTEN":
        response = BenchmarkingService.get_kindergarten_leaderboard(
            db,
            period_start=period_start,
            period_end=period_end,
            level=level,
            level_value=level_value,
            size_mode=size_mode,
            size_band=size_band,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            kindergarten_id=entity_id,
            min_sample_days=min_sample_days,
        )
    elif entity_type == "MANAGER":
        response = BenchmarkingService.get_manager_leaderboard(
            db,
            period_start=period_start,
            period_end=period_end,
            level=level,
            level_value=level_value,
            size_mode=size_mode,
            size_band=size_band,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            min_sample_days=min_sample_days,
        )
    else:
        response = BenchmarkingService.get_supervisor_leaderboard(
            db,
            period_start=period_start,
            period_end=period_end,
            level=level,
            level_value=level_value,
            size_mode=size_mode,
            size_band=size_band,
            country=country,
            governorate=governorate,
            city=city,
            area=area,
            min_sample_days=min_sample_days,
        )

    row = _row_by_entity_id(response.rows, entity_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الكيان غير موجود ضمن نطاق الفلاتر")

    trend_points = _build_trend_points(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        period_start=period_start,
        period_end=period_end,
        level=level,
        level_value=level_value,
        size_mode=size_mode,
        size_band=size_band,
        country=country,
        governorate=governorate,
        city=city,
        area=area,
        min_sample_days=min_sample_days,
        periods=6,
    )

    return ClassificationDetailResponse(
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        display_name=row.display_name,
        period_start=period_start,
        period_end=period_end,
        final_score=row.final_score,
        band_code=row.band_code,
        band_label=row.band_label,
        coverage_pct=row.coverage_pct,
        aspects=row.aspects,
        trend_points=trend_points,
        indicator_definitions=BenchmarkingService._indicator_explanations(),
        action_guidance=_actions_from_aspects(row.aspects),
    )


@router.post("/admin/classification/cache/warm")
def warm_admin_classification_cache(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    period_start, period_end = _normalize_period(period_start, period_end)
    kindergartens = BenchmarkingService._get_kindergarten_scope(
        db,
        level="NETWORK",
        level_value=None,
        country=None,
        governorate=None,
        city=None,
        area=None,
        kindergarten_id=None,
    )
    warmed_entries = 0
    for kg in kindergartens:
        BenchmarkingService._bundle(db, kg.id, period_start, period_end)
        warmed_entries += 1
    return {
        "message": "تم تجهيز ذاكرة مؤقتة للتصنيف",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "warmed_entries": warmed_entries,
    }


@router.post("/admin/classification/cache/invalidate")
def invalidate_admin_classification_cache(
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    dashboard_cache.clear()
    return {"message": "تمت إعادة تهيئة الذاكرة المؤقتة للتصنيف"}


@router.get("/manager/benchmarking/summary", response_model=ManagerBenchmarkSummaryResponse)
def get_manager_benchmarking_summary(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_manager_only(current_user)
    _validate_common_filters("GOVERNORATE", size_mode, size_band)
    if not current_user.kindergarten_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="لا يوجد نطاق روضة مرتبط بالمستخدم")

    period_start, period_end = _normalize_period(period_start, period_end)
    manager_kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == current_user.kindergarten_id).first()
    if manager_kg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الروضة المرتبطة بالمدير غير موجودة")

    result = BenchmarkingService.get_manager_leaderboard(
        db,
        period_start=period_start,
        period_end=period_end,
        level="GOVERNORATE",
        level_value=manager_kg.governorate,
        size_mode=size_mode,
        size_band=size_band,
        country=BenchmarkingService._kg_country(manager_kg),
        governorate=manager_kg.governorate,
        city=None,
        area=None,
        min_sample_days=min_sample_days,
    )
    row = _row_by_entity_id(result.rows, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="لا يوجد تصنيف متاح للمدير ضمن نطاق المقارنة")

    peer_rows = [
        item for item in result.rows
        if item.peer_group_key == row.peer_group_key and item.rank is not None
    ]
    peer_rows.sort(key=lambda item: item.rank or 999999)
    anonymized_peers = []
    for index, peer in enumerate(peer_rows, start=1):
        if peer.entity_id == current_user.id:
            continue
        anonymized_peers.append(
            {
                "peer_code": f"ندّ {index}",
                "rank": peer.rank,
                "percentile": peer.percentile,
                "band_label": peer.band_label,
                "final_score": peer.final_score,
            }
        )
        if len(anonymized_peers) >= 10:
            break

    return ManagerBenchmarkSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        manager_id=current_user.id,
        kindergarten_id=int(current_user.kindergarten_id),
        final_score=row.final_score,
        percentile=row.percentile,
        band_label=row.band_label,
        peer_group_size=len(peer_rows),
        peer_group_label=f"{manager_kg.governorate} - {_size_band_label(row.size_band)}",
        anonymized_peers=anonymized_peers,
        insufficient_data=row.insufficient_data,
        insufficient_reason=row.insufficient_reason,
        indicator_explanations=BenchmarkingService._indicator_explanations(),
    )


@router.get("/supervisor/performance/summary", response_model=SupervisorPerformanceSummaryResponse)
def get_supervisor_performance_summary(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    size_mode: str = Query("ENROLLMENT"),
    size_band: Optional[str] = Query(None),
    min_sample_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_supervisor_only(current_user)
    if not current_user.kindergarten_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="لا يوجد نطاق روضة مرتبط بالمستخدم")
    _validate_common_filters("KINDERGARTEN", size_mode, size_band)
    period_start, period_end = _normalize_period(period_start, period_end)

    result = BenchmarkingService.get_supervisor_leaderboard(
        db,
        period_start=period_start,
        period_end=period_end,
        level="KINDERGARTEN",
        level_value=str(current_user.kindergarten_id),
        size_mode=size_mode,
        size_band=size_band,
        country=None,
        governorate=None,
        city=None,
        area=None,
        min_sample_days=min_sample_days,
    )
    row = _row_by_entity_id(result.rows, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="لا يوجد تقييم متاح للمشرف")

    return SupervisorPerformanceSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        supervisor_id=current_user.id,
        final_score=row.final_score,
        band_label=row.band_label,
        coverage_pct=row.coverage_pct,
        sample_size=row.sample_size,
        aspects=row.aspects,
        insufficient_data=row.insufficient_data,
        insufficient_reason=row.insufficient_reason,
        indicator_explanations=BenchmarkingService._indicator_explanations(),
    )


@router.get("/parent/kindergarten/quality-band", response_model=ParentQualityBandResponse)
def get_parent_kindergarten_quality_band(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_parent_only(current_user)
    period_start, period_end = _normalize_period(period_start, period_end)

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if parent_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ملف ولي الأمر غير موجود")

    enrollment = db.query(models.EnrollmentApplication).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id,
    ).filter(
        models.Child.parent_id == parent_profile.id,
        models.EnrollmentApplication.kindergarten_id.isnot(None),
        models.EnrollmentApplication.status.in_([
            models.EnrollmentStatus.ACTIVE,
            models.EnrollmentStatus.ACCEPTED,
        ]),
    ).order_by(models.EnrollmentApplication.created_at.desc()).first()
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="لا يوجد تسجيل نشط مرتبط بولي الأمر")

    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == enrollment.kindergarten_id
    ).first()
    if kindergarten is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الروضة غير موجودة")

    bundle = BenchmarkingService._bundle(db, kindergarten.id, period_start, period_end)
    governance_score = float(bundle.get("governance_score", 0.0))
    _, band_label = _band_for_score(governance_score)

    return ParentQualityBandResponse(
        kindergarten_id=kindergarten.id,
        kindergarten_name=kindergarten.name_ar or kindergarten.name_en or f"روضة {kindergarten.id}",
        period_start=period_start,
        period_end=period_end,
        governance_score=round(governance_score, 2),
        band_label=band_label,
        explanation="يعكس هذا التصنيف مستوى جودة الحوكمة والتشغيل في روضة طفلكم خلال الفترة المحددة.",
    )

