"""
Analytics and Reporting Services for Admin Dashboard
Implements drill-down analytics from Network → Governorate → Kindergarten → Class → Child
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks, Response
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from enum import Enum
import os
from pathlib import Path
import csv
import io
import tempfile
import logging

try:
    import openpyxl
except ImportError:
    openpyxl = None

import models
from database import get_db, SessionLocal
from dependencies import get_current_user, get_current_user_or_redirect
from kpi_service import KPIService
import validators
from audit_actions import AuditAction
from admin_security import log_audit_event
from analytics_domain import (
    PredictRequest,
    PredictResponse,
    ScopeInfo,
    SeriesPoint,
    AnomalyRecord,
    DrilldownResponse,
    ThresholdRequest,
    ActionPlanRequest,
    TargetRequest,
    DataQualityResult,
    hash_params,
    build_forecast,
    attendance_series,
    incident_series,
    enrollment_series,
    z_score_anomalies,
)
from api.analytics.scope_domain import (
    allowed_kindergarten_ids as _allowed_kindergarten_ids,
    allowed_governorates as _allowed_governorates,
    enforce_analytics_rbac as _enforce_analytics_rbac,
    enforce_kindergarten_scope,
    get_date_range,
    kg_ids_for_governorate as _kg_ids_for_governorate,
)

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return UTC timestamp without tzinfo for legacy naive DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Jordan timezone — UTC+3 (no DST). Use for all operational date arithmetic.
_JORDAN_TZ = timezone(timedelta(hours=3))


def _jordan_today() -> date:
    """Return the current calendar date in Jordan (UTC+3)."""
    return datetime.now(_JORDAN_TZ).date()


def _jordan_now() -> datetime:
    """Return the current datetime in Jordan (UTC+3), timezone-aware."""
    return datetime.now(_JORDAN_TZ)


def _to_jordan_iso(dt: datetime | None) -> str | None:
    """
    Serialise a datetime for JSON/JS consumption.

    Naive datetimes are assumed to be UTC (as stored by SQLAlchemy on SQLite
    with server_default=func.now()).  The value is shifted to Jordan UTC+3 and
    returned as a full ISO-8601 string with offset (+03:00) so that
    `new Date(val)` parses unambiguously in every browser and environment.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_JORDAN_TZ).isoformat()

# =============================================================================
# Pydantic Schemas for API
# =============================================================================

class AdvancedAnalyticsCacheResponse(BaseModel):
    dimension_type: str
    dimension_id: str
    period_type: str
    period_start: date
    period_end: date
    attendance_rate: Optional[float] = None
    chronic_absence_rate: Optional[float] = None
    incident_rate_per_100: Optional[float] = None
    serious_incident_rate: Optional[float] = None
    ratio_compliance_rate: Optional[float] = None
    report_completion_rate: Optional[float] = None
    parent_satisfaction_nps: Optional[float] = None
    child_development_index: Optional[float] = None
    staff_turnover_rate: Optional[float] = None
    regulatory_compliance_score: Optional[float] = None
    attendance_trend_slope: Optional[float] = None
    risk_score: Optional[float] = None
    improvement_velocity: Optional[float] = None
    attendance_incident_correlation: Optional[float] = None
    staffing_quality_correlation: Optional[float] = None
    health_alerts_count: Optional[int] = None
    curriculum_progress: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)

class InvalidateCacheRequest(BaseModel):
    dimension_type: Optional[str] = None
    dimension_id: Optional[str] = None
    period_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None

class WarmCacheRequest(BaseModel):
    dimension_type: str
    dimension_ids: List[str]
    period_type: str
    period_start: date
    period_end: date

# =============================================================================
# API Endpoints for Advanced Analytics Cache
# =============================================================================

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _ensure_admin_only(current_user: models.User):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")


def _normalize_scope(scope_type: str) -> str:
    return scope_type.upper()


def _scope_label(db: Session, scope_type: str, scope_id: Optional[str]) -> Optional[str]:
    if scope_type == "GOVERNORATE":
        return scope_id
    if scope_type == "KINDERGARTEN" and scope_id:
        kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == int(scope_id)).first()
        return kg.name_ar if kg else None
    if scope_type == "CLASS" and scope_id:
        cls = db.query(models.Class).filter(models.Class.id == int(scope_id)).first()
        return cls.name_ar if cls else None
    if scope_type == "CHILD" and scope_id:
        child = db.query(models.Child).filter(models.Child.id == int(scope_id)).first()
        return f"{child.first_name} {child.last_name}" if child else None
    return "الشبكة" if scope_type == "NETWORK" else None

@router.get("/metadata")
def get_analytics_metadata(lang: str = Query("ar", pattern="^(ar|en)$")):
    """Return static analytics metadata (datasets/dimensions/metrics/time grains)."""
    dims = [
        {"id": "date.day", "label_ar": "اليوم", "label_en": "Day", "allowed_filters": ["between", "eq", "gte", "lte"], "drill_targets": ["date.week", "date.month"]},
        {"id": "org.kindergarten", "label_ar": "الروضة", "label_en": "Kindergarten", "allowed_filters": ["eq", "in"], "drill_targets": ["org.class"]},
        {"id": "org.class", "label_ar": "الصف", "label_en": "Class", "allowed_filters": ["eq", "in"]},
        {"id": "geo.governorate", "label_ar": "المحافظة", "label_en": "Governorate", "allowed_filters": ["eq", "in"]},
    ]
    metrics = [
        {"id": "attendance_rate", "label_ar": "نسبة الحضور", "label_en": "Attendance Rate", "aggregation": "ratio"},
        {"id": "incident_rate_per_100", "label_ar": "الحوادث لكل 100 يوم-طفل", "label_en": "Incidents per 100 child-days", "aggregation": "rate"},
        {"id": "serious_incident_rate", "label_ar": "حوادث خطيرة", "label_en": "Serious Incident Rate", "aggregation": "rate"},
        {"id": "ratio_compliance_rate", "label_ar": "التزام النِسَب", "label_en": "Ratio Compliance", "aggregation": "ratio"},
        {"id": "report_completion_rate", "label_ar": "إكمال التقارير", "label_en": "Report Completion", "aggregation": "ratio"},
    ]
    label_key = "label_ar" if lang == "ar" else "label_en"
    return {
        "datasets": [
            {"id": "advanced_analytics_cache", "label": "مؤشرات متقدمة" if lang == "ar" else "Advanced Analytics"},
            {"id": "analytics_dimension_cache", "label": "مُلخص سريع" if lang == "ar" else "Cached Snapshots"},
        ],
        "dimensions": [{**d, "label": d[label_key]} for d in dims],
        "metrics": [{**m, "label": m[label_key]} for m in metrics],
        "time_grains": ["daily", "weekly", "monthly"],
        "defaults": {"date_range_days": 30, "limit": 200}
    }


@router.post("/predict/{metric}", response_model=PredictResponse)
def predict_metric(
    metric: str,
    req: PredictRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    metric = metric.lower()
    if metric not in {"attendance", "incidents", "enrollment"}:
        raise HTTPException(status_code=400, detail="Unsupported metric")

    scope_type = _normalize_scope(req.scope_type)
    scope_id = req.scope_id
    params_key = hash_params(metric, scope_type, scope_id, req.start_date, req.end_date, req.horizon_days)

    cached = db.query(models.PredictionCache).filter(
        models.PredictionCache.metric_type == metric,
        models.PredictionCache.scope_type == scope_type,
        models.PredictionCache.scope_id == scope_id,
        models.PredictionCache.params_hash == params_key,
    ).first()
    if cached:
        # Convert ISO strings from JSON back to date objects for SeriesPoint
        def deserialize_series_points(data):
            return [SeriesPoint(date=date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"], value=p["value"]) for p in data]
        
        return PredictResponse(
            metric=metric,
            scope=ScopeInfo(scope_type=scope_type, scope_id=scope_id, label=_scope_label(db, scope_type, scope_id)),
            points=deserialize_series_points(cached.points),
            forecast_points=deserialize_series_points(cached.forecast_points),
            confidence={
                "lower": deserialize_series_points(cached.confidence.get("lower", [])),
                "upper": deserialize_series_points(cached.confidence.get("upper", [])),
            },
            model_meta=cached.model_meta,
        )

    if metric == "attendance":
        series = attendance_series(db, scope_type, scope_id, req.start_date, req.end_date)
    elif metric == "incidents":
        series = incident_series(db, scope_type, scope_id, req.start_date, req.end_date)
    else:
        series = enrollment_series(db, scope_type, scope_id, req.start_date, req.end_date)

    forecast_points, confidence, model_meta = build_forecast(series, req.horizon_days)
    model_meta = {**model_meta, "last_trained": model_meta.get("trained_at"), "metric": metric}

    # Convert date objects to ISO strings for JSON storage
    def serialize_series_points(points):
        return [{"date": p.date.isoformat() if hasattr(p.date, "isoformat") else str(p.date), "value": p.value} for p in points]

    cache = models.PredictionCache(
        metric_type=metric,
        scope_type=scope_type,
        scope_id=scope_id,
        period_start=req.start_date,
        period_end=req.end_date,
        horizon_days=req.horizon_days,
        params_hash=params_key,
        points=serialize_series_points(series),
        forecast_points=serialize_series_points(forecast_points),
        confidence={
            "lower": serialize_series_points(confidence["lower"]),
            "upper": serialize_series_points(confidence["upper"]),
        },
        model_meta=model_meta,
    )
    db.add(cache)
    db.commit()

    return PredictResponse(
        metric=metric,
        scope=ScopeInfo(scope_type=scope_type, scope_id=scope_id, label=_scope_label(db, scope_type, scope_id)),
        points=series,
        forecast_points=forecast_points,
        confidence=confidence,
        model_meta=model_meta,
    )


@router.get("/anomalies")
def get_anomalies(
    scope_type: str = Query("NETWORK"),
    scope_id: Optional[str] = Query(None),
    metric_type: str = Query("attendance"),
    start_date: date = Query(..., alias="from"),
    end_date: date = Query(..., alias="to"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    scope_type = _normalize_scope(scope_type)

    if metric_type == "attendance":
        series = attendance_series(db, scope_type, scope_id, start_date, end_date)
    elif metric_type == "incidents":
        series = incident_series(db, scope_type, scope_id, start_date, end_date)
    else:
        series = enrollment_series(db, scope_type, scope_id, start_date, end_date)

    anomalies = z_score_anomalies(series)
    response_items: List[AnomalyRecord] = []
    for point, score, severity in anomalies:
        existing = db.query(models.AnomalyAlert).filter(
            models.AnomalyAlert.metric_type == metric_type,
            models.AnomalyAlert.scope_type == scope_type,
            models.AnomalyAlert.scope_id == scope_id,
            models.AnomalyAlert.detected_at == point.date,
        ).first()
        if not existing:
            existing = models.AnomalyAlert(
                metric_type=metric_type,
                scope_type=scope_type,
                scope_id=scope_id,
                detected_at=point.date,
                score=score,
                severity=severity,
                message=f"Anomaly detected for {metric_type}",
                is_acknowledged=False,
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
        response_items.append(
            AnomalyRecord(
                id=existing.id,
                metric_type=existing.metric_type,
                scope_type=existing.scope_type,
                scope_id=existing.scope_id,
                detected_at=existing.detected_at,
                score=existing.score,
                severity=existing.severity,
                message=existing.message,
                ack_status=existing.is_acknowledged,
            )
        )

    return {"anomalies": [item.model_dump() for item in response_items]}



@router.get("/alerts")
def list_alerts(
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    AnalyticsService.evaluate_thresholds(db)
    query = db.query(models.ActiveAlert)
    if scope_type:
        query = query.filter(models.ActiveAlert.scope_type == _normalize_scope(scope_type))
    if scope_id:
        query = query.filter(models.ActiveAlert.scope_id == scope_id)
    alerts = query.order_by(models.ActiveAlert.triggered_at.desc()).all()
    return {"alerts": [
        {
            "id": alert.id,
            "metric_type": alert.metric_type,
            "scope_type": alert.scope_type,
            "scope_id": alert.scope_id,
            "current_value": alert.current_value,
            "message": alert.message,
            "severity": alert.severity,
            "status": alert.status,
            "triggered_at": _to_jordan_iso(alert.triggered_at),
            "acknowledged_at": _to_jordan_iso(alert.acknowledged_at),
        }
        for alert in alerts
    ]}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    alert = db.query(models.ActiveAlert).filter(models.ActiveAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = models.AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = _utcnow_naive()
    db.commit()
    return {"status": "acknowledged", "id": alert_id}


@router.put("/alerts/thresholds")
def upsert_threshold(
    req: ThresholdRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    scope_type = _normalize_scope(req.scope_type)
    threshold = models.AlertThreshold(
        metric_type=req.metric_type,
        scope_type=scope_type,
        scope_id=req.scope_id,
        operator=models.AlertOperator(req.operator),
        threshold_value=req.threshold_value,
        window_days=req.window_days,
        severity=models.SeverityLevel(req.severity),
        is_active=req.is_active,
        created_by=current_user.id,
    )
    db.add(threshold)
    db.commit()
    db.refresh(threshold)
    return {"id": threshold.id, "status": "created"}


@router.get("/benchmarks/{kindergarten_id}")
def get_benchmarks(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    benchmarks = db.query(models.BenchmarkData).filter(
        models.BenchmarkData.scope_type == "KINDERGARTEN",
        models.BenchmarkData.scope_id == str(kindergarten_id)
    ).all()
    return {"benchmarks": [
        {
            "metric_type": b.metric_type,
            "comparison_group": b.comparison_group,
            "period_start": b.period_start.isoformat(),
            "period_end": b.period_end.isoformat(),
            "value": b.value,
        }
        for b in benchmarks
    ]}


@router.get("/targets")
def get_targets(
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    query = db.query(models.PerformanceTarget)
    if scope_type:
        query = query.filter(models.PerformanceTarget.scope_type == _normalize_scope(scope_type))
    if scope_id:
        query = query.filter(models.PerformanceTarget.scope_id == scope_id)
    targets = query.order_by(models.PerformanceTarget.effective_date.desc()).all()
    return {"targets": [
        {
            "id": t.id,
            "metric_type": t.metric_type,
            "scope_type": t.scope_type,
            "scope_id": t.scope_id,
            "target_value": t.target_value,
            "effective_date": t.effective_date.isoformat(),
        }
        for t in targets
    ]}


@router.put("/targets")
def set_target(
    req: TargetRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    target = models.PerformanceTarget(
        metric_type=req.metric_type,
        scope_type=_normalize_scope(req.scope_type),
        scope_id=req.scope_id,
        target_value=req.target_value,
        effective_date=req.effective_date,
        created_by=current_user.id,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return {"id": target.id, "status": "created"}


@router.get("/recommendations/{kindergarten_id}")
def get_recommendations(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    AnalyticsService.generate_recommendations_for_kindergarten(db, kindergarten_id, current_user.id)
    recs = db.query(models.Recommendation).filter(
        models.Recommendation.kindergarten_id == kindergarten_id
    ).all()
    return {"recommendations": [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "severity": r.severity,
            "metric_type": r.metric_type,
            "recommended_actions": r.recommended_actions,
        }
        for r in recs
    ]}


@router.post("/actions")
def create_action_plan(
    req: ActionPlanRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    plan = models.ActionPlan(
        recommendation_id=req.recommendation_id,
        kindergarten_id=req.kindergarten_id,
        title=req.title,
        description=req.description,
        assigned_to=req.assigned_to,
        due_date=req.due_date,
        created_by=current_user.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "status": "created"}


@router.get("/actions/{action_id}/progress")
def get_action_progress(
    action_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    plan = db.query(models.ActionPlan).filter(models.ActionPlan.id == action_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Action plan not found")
    return {
        "id": plan.id,
        "status": plan.status,
        "progress_percent": plan.progress_percent,
        "due_date": plan.due_date.isoformat() if plan.due_date else None,
    }


@router.get("/data-quality")
def get_data_quality(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    AnalyticsService.evaluate_data_quality(db, current_user.id)
    latest = db.query(models.DataQualityMetric).order_by(models.DataQualityMetric.evaluated_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No data quality metrics available")
    return {
        "entity_type": latest.entity_type,
        "entity_id": latest.entity_id,
        "completeness_percent": latest.completeness_percent,
        "accuracy_score": latest.accuracy_score,
        "timeliness_score": latest.timeliness_score,
        "consistency_score": latest.consistency_score,
        "evaluated_at": _to_jordan_iso(latest.evaluated_at),
    }


@router.get("/data-quality/report")
def get_data_quality_report(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin_only(current_user)
    AnalyticsService.evaluate_data_quality(db, current_user.id)
    metrics = db.query(models.DataQualityMetric).order_by(models.DataQualityMetric.evaluated_at.desc()).limit(50).all()
    return {
        "reports": [
            {
                "entity_type": m.entity_type,
                "entity_id": m.entity_id,
                "completeness_percent": m.completeness_percent,
                "accuracy_score": m.accuracy_score,
                "timeliness_score": m.timeliness_score,
                "consistency_score": m.consistency_score,
                "evaluated_at": _to_jordan_iso(m.evaluated_at),
                "details": m.details,
            }
            for m in metrics
        ]
    }

@router.get("/advanced-cache", response_model=AdvancedAnalyticsCacheResponse)
def get_advanced_analytics_cache(
    dimension_type: str = Query(...),
    dimension_id: str = Query(...),
    period_type: str = Query(...),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Enforce RBAC and kindergarten isolation
    _enforce_analytics_rbac(current_user, db, dimension_type, dimension_id)
    
    dim_type_enum = models.AnalyticsDimensionType(dimension_type)
    period_type_enum = models.AnalyticsPeriodType(period_type)
    cache = AnalyticsService.get_advanced_analytics_cache(
        db, dim_type_enum, dimension_id, period_type_enum, period_start, period_end
    )
    if not cache:
        cache = AnalyticsService.compute_advanced_analytics(
            db, dim_type_enum, dimension_id, period_type_enum, period_start, period_end
        )
    if not cache:
        raise HTTPException(status_code=404, detail="No cache found")
    return cache

@router.post("/advanced-cache/invalidate")
def invalidate_advanced_analytics_cache(
    req: InvalidateCacheRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    count = AnalyticsService.invalidate_advanced_analytics_cache(
        db,
        models.AnalyticsDimensionType(req.dimension_type) if req.dimension_type else None,
        req.dimension_id,
        models.AnalyticsPeriodType(req.period_type) if req.period_type else None,
        req.period_start,
        req.period_end
    )
    return {"deleted": count}

@router.post("/advanced-cache/warm")
def warm_advanced_analytics_cache(
    req: WarmCacheRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    count = AnalyticsService.warm_advanced_analytics_cache(
        db,
        models.AnalyticsDimensionType(req.dimension_type),
        req.dimension_ids,
        models.AnalyticsPeriodType(req.period_type),
        req.period_start,
        req.period_end
    )
    return {"created": count}

# =============================================================================
# Response Models
# =============================================================================

class MetricValue(BaseModel):
    value: float
    change: Optional[float] = None  # Percentage change from previous period
    trend: Optional[str] = None  # "up", "down", "stable"


class MetricDelta(BaseModel):
    current_value: Any
    previous_value: Optional[Any] = None
    delta_absolute: Optional[Any] = None
    delta_percent: Optional[float] = None
    direction: str
    source: str


class NetworkSummary(BaseModel):
    total_kindergartens: int
    total_children: int
    total_staff: int
    total_capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    report_submission_rate: float
    report_approval_rate: float
    report_completion_rate: float = Field(alias="report_approval_rate")  # Backward compatibility
    governance_avg_score: float
    previous_period: Dict[str, Any] = Field(default_factory=dict)
    deltas: Dict[str, MetricDelta] = Field(default_factory=dict)


class GovernorateMetrics(BaseModel):
    governorate: str
    kindergarten_count: int
    children_count: int
    capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    governance_score: float


class ConsolidatedAnalyticsResponse(BaseModel):
    network_summary: NetworkSummary
    governorate_breakdown: List["GovernorateMetrics"]
    attendance_trend: List["TimeSeriesPoint"]
    incident_trend: List["TimeSeriesPoint"]
    risk_radar: List[Dict[str, Any]]
    governance_distribution: "GovernanceDistribution"


class KindergartenMetrics(BaseModel):
    id: int
    name: str
    governorate: str
    children_count: int
    capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    report_submission_rate: float
    report_approval_rate: float
    report_completion_rate: float = Field(alias="report_approval_rate")  # Backward compatibility
    ratio_compliance: float
    governance_score: float
    governance_band: str
    
    # Advanced Metrics
    attendance_trend_slope: Optional[float] = None
    risk_score: Optional[float] = None
    attendance_incident_correlation: Optional[float] = None


class ClassMetrics(BaseModel):
    id: int
    name: str
    children_count: int
    capacity: int
    age_group: str
    attendance_rate: float
    assigned_teachers: int


class TimeSeriesPoint(BaseModel):
    date: str
    value: float
    label: Optional[str] = None


class RankingEntry(BaseModel):
    rank: int
    kindergarten_id: int
    kindergarten_name: str
    governorate: str
    value: float
    band: Optional[str] = None


class GovernanceDistribution(BaseModel):
    green: int
    amber: int
    red: int


class DrilldownResponse(BaseModel):
    dimension_type: str
    dimension_id: str
    dimension_name: str
    period_start: date
    period_end: date
    metrics: Dict[str, Any]
    children: Optional[List[Any]] = None



class ExportJobResponse(BaseModel):
    job_id: int
    status: str
    report_type: str
    created_at: Optional[str] = None  # ISO-8601 with Jordan +03:00 offset
    file_path: Optional[str] = None
    error: Optional[str] = None       # short error message when status == FAILED
    trace_url: Optional[str] = None   # link to audit log entry for this job


class ExportRequest(BaseModel):
    """Request body for export endpoint"""
    report_type: Optional[str] = Field(None, description="Report type: overview, attendance, incidents, etc.")
    export_format: Optional[str] = Field("CSV", description="CSV, PDF, EXCEL")
    filters: Optional[Dict[str, Any]] = None
    retry_job_id: Optional[int] = Field(None, description="Job ID to retry")


def _log_analytics_export_audit(
    db: Session,
    *,
    action: str,
    actor: Optional[models.User],
    report_type: Optional[str],
    export_format: Optional[Any] = None,
    filters: Optional[Dict[str, Any]] = None,
    job_id: Optional[int] = None,
    status_value: Optional[str] = None,
    file_path: Optional[str] = None,
    file_size: Optional[int] = None,
    error_message: Optional[str] = None,
    sensitivity_level: int = 2,
) -> None:
    export_format_value = export_format.value if isinstance(export_format, Enum) else export_format
    metadata: Dict[str, Any] = {
        "report_type": report_type,
        "export_format": export_format_value,
    }
    if filters:
        metadata["filters"] = filters
    if status_value:
        metadata["status"] = status_value
    if file_path:
        metadata["file_path"] = file_path
    if file_size is not None:
        metadata["file_size"] = file_size
    if error_message:
        metadata["error_message"] = error_message

    log_audit_event(
        db=db,
        action=action,
        actor=actor,
        target_type="Export",
        target_ids=job_id,
        metadata=metadata,
        sensitivity_level=sensitivity_level,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/network-summary", response_model=NetworkSummary)
def get_network_summary_endpoint(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get network-wide summary metrics (scoped for managers/supervisors)"""
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must be before or equal to period_end")
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    return AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)

@router.get("/governorate-breakdown", response_model=List[GovernorateMetrics])
def get_governorate_breakdown_endpoint(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get metrics broken down by governorate (scoped for managers/supervisors)"""
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must be before or equal to period_end")
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    allowed_govs = _allowed_governorates(current_user, db) or []
    gov_filter = governorate
    if current_user.role != models.UserRole.ADMIN:
        if gov_filter and gov_filter not in allowed_govs:
            raise HTTPException(status_code=403, detail="Governorate not allowed")
        if not gov_filter and len(allowed_govs) == 1:
            gov_filter = allowed_govs[0]

    return AnalyticsService.get_governorate_breakdown(
        db, period_start, period_end, gov_filter, allowed_kgs, allowed_govs
    )


def _previous_period_bounds(period_start: date, period_end: date) -> Optional[tuple[date, date]]:
    if period_start > period_end or period_start <= date.min:
        return None
    duration_days = (period_end - period_start).days + 1
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=duration_days - 1)
    if previous_start < date.min or previous_start > previous_end:
        return None
    return previous_start, previous_end


def _count_active_kindergartens_at(db: Session, kg_ids: Optional[List[int]], as_of_date: date) -> int:
    if kg_ids is not None and not kg_ids:
        return 0

    query = db.query(func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        func.date(models.Kindergarten.created_at) <= as_of_date,
        or_(
            models.Kindergarten.license_valid_until.is_(None),
            models.Kindergarten.license_valid_until >= as_of_date,
        ),
    )
    if kg_ids is not None:
        query = query.filter(models.Kindergarten.id.in_(kg_ids))
    return int(query.scalar() or 0)


def _network_expected_child_days(
    db: Session,
    period_start: date,
    period_end: date,
    kg_ids: Optional[List[int]],
) -> int:
    if kg_ids is not None and not kg_ids:
        return 0
    days_in_period = (period_end - period_start).days + 1
    query = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )
    if kg_ids is not None:
        query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
    return int(query.scalar() or 0) * days_in_period


def _network_attended_child_days(
    db: Session,
    period_start: date,
    period_end: date,
    kg_ids: Optional[List[int]],
) -> int:
    if kg_ids is not None and not kg_ids:
        return 0
    query = db.query(func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date >= period_start,
        models.AttendanceLog.date <= period_end,
    ).join(models.Child).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.Child.id,
    ).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )
    if kg_ids is not None:
        query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
    return int(query.scalar() or 0)


def _build_metric_delta(
    current_value,
    previous_value,
    higher_is_good: bool,
    available: bool = True,
) -> Dict[str, Any]:
    if not available or previous_value is None:
        return {
            "current_value": current_value,
            "previous_value": None,
            "delta_absolute": None,
            "delta_percent": None,
            "direction": "neutral",
            "source": "unavailable",
        }

    try:
        current = float(current_value)
        previous = float(previous_value)
    except (TypeError, ValueError):
        return {
            "current_value": current_value,
            "previous_value": previous_value,
            "delta_absolute": None,
            "delta_percent": None,
            "direction": "neutral",
            "source": "unavailable",
        }

    delta_absolute = current - previous
    delta_percent = None if previous == 0 else round((delta_absolute / previous) * 100, 2)
    if delta_absolute > 0:
        direction = "up" if higher_is_good else "down"
    elif delta_absolute < 0:
        direction = "down" if higher_is_good else "up"
    else:
        direction = "neutral"

    return {
        "current_value": current_value,
        "previous_value": previous_value,
        "delta_absolute": round(delta_absolute, 4),
        "delta_percent": delta_percent,
        "direction": direction,
        "source": "real",
    }


@router.get("/dashboard-data", response_model=ConsolidatedAnalyticsResponse)
def get_consolidated_dashboard_data(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all data needed for the main analytics dashboard."""
    logger.info(f"Analytics request from user {current_user.id}: {period_start} to {period_end}, gov={governorate}")
    
    try:
        allowed_kgs = _allowed_kindergarten_ids(current_user, db)
        allowed_govs: Optional[List[str]] = None
        if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Validate date range
        if period_start > period_end:
            logger.warning(f"Invalid date range: {period_start} > {period_end}")
            raise HTTPException(status_code=400, detail="Invalid date range: start date must be before or equal to end date")
        
        if (period_end - period_start).days > 365:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

        # Resolve filter set: intersection of allowed and requested governorate
        gov_filter = governorate
        if current_user.role != models.UserRole.ADMIN:
            allowed_govs = _allowed_governorates(current_user, db) or []
            if gov_filter and gov_filter not in allowed_govs:
                raise HTTPException(status_code=403, detail="Governorate not allowed")
            if not gov_filter and len(allowed_govs) == 1:
                gov_filter = allowed_govs[0]

        kg_filter = _kg_ids_for_governorate(db, gov_filter)
        if allowed_kgs is not None and kg_filter is not None:
            kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
        elif allowed_kgs is not None:
            kg_filter = allowed_kgs

        logger.info(f"Fetching analytics data for date range {period_start} to {period_end}")
        
        network_summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)
        previous_period_bounds = _previous_period_bounds(period_start, period_end)
        if previous_period_bounds:
            previous_start, previous_end = previous_period_bounds
            previous_summary = AnalyticsService.get_network_summary(db, previous_start, previous_end, kg_filter)
            previous_summary.total_kindergartens = _count_active_kindergartens_at(db, kg_filter, previous_end)
            previous_expected_child_days = _network_expected_child_days(db, previous_start, previous_end, kg_filter)
            previous_attended_child_days = _network_attended_child_days(db, previous_start, previous_end, kg_filter)
            previous_period = {
                "period_start": previous_start.isoformat(),
                "period_end": previous_end.isoformat(),
            }
            deltas = {
                "total_kindergartens": MetricDelta(
                    **_build_metric_delta(
                        network_summary.total_kindergartens,
                        previous_summary.total_kindergartens,
                        True,
                        available=True,
                    )
                ),
                "attendance_rate": MetricDelta(
                    **_build_metric_delta(
                        network_summary.attendance_rate,
                        previous_summary.attendance_rate,
                        True,
                        available=previous_expected_child_days > 0,
                    )
                ),
                "incident_rate": MetricDelta(
                    **_build_metric_delta(
                        network_summary.incident_rate,
                        previous_summary.incident_rate,
                        False,
                        available=previous_attended_child_days > 0,
                    )
                ),
            }
        else:
            previous_period = {}
            deltas = {
                "total_kindergartens": MetricDelta(
                    **_build_metric_delta(network_summary.total_kindergartens, None, True, available=False)
                ),
                "attendance_rate": MetricDelta(
                    **_build_metric_delta(network_summary.attendance_rate, None, True, available=False)
                ),
                "incident_rate": MetricDelta(
                    **_build_metric_delta(network_summary.incident_rate, None, False, available=False)
                ),
            }
        network_summary.previous_period = previous_period
        network_summary.deltas = deltas
        governorate_breakdown = AnalyticsService.get_governorate_breakdown(
            db, period_start, period_end, gov_filter, allowed_kgs, allowed_govs
        )
        attendance_trend = AnalyticsService.get_network_trends(db, "attendance", period_start, period_end, kg_filter)
        incident_trend = AnalyticsService.get_network_trends(db, "incidents", period_start, period_end, kg_filter)
        risk_radar = AnalyticsService.get_high_risk_children(db, kg_filter)
        governance_distribution = AnalyticsService.get_governance_distribution(db, period_start, period_end, kg_filter)

        logger.info("Successfully retrieved analytics data")
        
        return ConsolidatedAnalyticsResponse(
            network_summary=network_summary,
            governorate_breakdown=governorate_breakdown,
            attendance_trend=attendance_trend,
            incident_trend=incident_trend,
            risk_radar=risk_radar,
            governance_distribution=governance_distribution,
        )
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error("Database error fetching analytics data: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while fetching analytics data")
    except (TypeError, ValueError) as e:
        logger.error("Invalid analytics data while fetching analytics data: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while fetching analytics data")
    except Exception as e:
        logger.error("Unexpected error fetching analytics data: %s: %s", type(e).__name__, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while fetching analytics data")



@router.get("/trends", response_model=List[TimeSeriesPoint])
def get_network_trends_endpoint(
    metric: str = Query(..., description="Metric to retrieve: attendance, incidents"),
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get time-series trend data for network (Admin only)"""
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must be before or equal to period_end")
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")
    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs
    return AnalyticsService.get_network_trends(db, metric, period_start, period_end, kg_filter)

@router.get("/risk-radar")
def get_risk_radar_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of high-risk entities (scoped)"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")
    return AnalyticsService.get_high_risk_children(db, allowed_kgs)

@router.post("/export/sync")
def export_analytics_data(
    request: ExportRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export analytics reports (CSV or Excel) with memory streaming for large datasets.
    """
    validators.validate_admin_role(current_user)

    start_str = request.filters.get("period_start") if request.filters else None
    end_str = request.filters.get("period_end") if request.filters else None
    
    if not start_str or not end_str:
         end_date = _jordan_today()
         start_date = end_date - timedelta(days=30)
    else:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if isinstance(start_str, str) else start_str
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date() if isinstance(end_str, str) else end_str
        except ValueError:
            _log_analytics_export_audit(
                db, action=AuditAction.ANALYTICS_EXPORT_SYNC_FAILED, actor=current_user,
                report_type=request.report_type, export_format=request.export_format,
                filters=request.filters, status_value="failed", error_message="Invalid date format", sensitivity_level=3
            )
            raise HTTPException(status_code=400, detail="Invalid date format")

    import csv
    import io
    from fastapi.responses import Response, StreamingResponse

    # Determine headers and row generator
    headers = []
    
    def row_generator():
        if request.report_type == "attendance":
            headers.extend(["Kindergarten", "Children Count", "Capacity", "Attendance Rate %"])
            yield headers
            kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).yield_per(100)
            for kg in kgs:
                rate = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
                yield [kg.name_ar, len(kg.enrollments), "N/A", rate]
                
        elif request.report_type == "incidents":
            headers.extend(["Date", "Kindergarten", "Type", "Severity", "Description", "Child"])
            yield headers
            incidents = db.query(models.Incident).filter(
                func.date(models.Incident.occurred_at) >= start_date,
                func.date(models.Incident.occurred_at) <= end_date
            ).yield_per(100)
            for inc in incidents:
                ch_name = f"{inc.child.first_name} {inc.child.last_name}" if inc.child else "Unknown"
                yield [inc.occurred_at.strftime("%Y-%m-%d"), inc.kindergarten.name_ar if inc.kindergarten else "", inc.type.value, inc.severity_level.value, inc.description, ch_name]

        elif request.report_type == "compliance":
            headers.extend(["Kindergarten", "Ratio Compliance %", "Governance Score"])
            yield headers
            kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).yield_per(100)
            for kg in kgs:
                ratio = KPIService.compute_ratio_compliance(db, kg.id, start_date, end_date)
                try:
                    gov_score, _ = KPIService.compute_governance_score(db, kg.id, start_date, end_date)
                except (SQLAlchemyError, TypeError, ValueError):
                    gov_score = 0
                yield [kg.name_ar, ratio, gov_score]

        elif request.report_type == "governorate":
            headers.extend(["Governorate", "Kindergartens", "Children", "Attendance %", "Incident Rate", "Governance Score"])
            yield headers
            data = AnalyticsService.get_governorate_breakdown(db, start_date, end_date, None, None, None)
            for item in data:
                yield [item.governorate, item.kindergarten_count, item.children_count, item.attendance_rate, item.incident_rate, item.governance_score]

        elif request.report_type == "full_audit":
            headers.extend(["Timestamp", "User", "Action", "Entity", "Details", "IP"])
            yield headers
            
            # Streaming query for large audit logs
            query = db.query(models.AuditLog).filter(
                 func.date(models.AuditLog.created_at) >= start_date,
                 func.date(models.AuditLog.created_at) <= end_date
            ).order_by(desc(models.AuditLog.created_at))
            
            # Simple caching for users
            user_cache = {}
            for log in query.yield_per(500):
                uid = log.user_id
                username = "Unknown"
                if uid:
                    if uid not in user_cache:
                        u = db.query(models.User.username).filter(models.User.id == uid).first()
                        user_cache[uid] = u[0] if u else "Unknown"
                    username = user_cache[uid]
                yield [str(log.created_at), username, log.action, log.entity_type, log.details, log.ip_address]
                
        else:
            raise ValueError("Invalid report type")

    try:
        # Pre-flight check to fail early if report type is invalid
        gen = row_generator()
        first_row_headers = next(gen)
    except ValueError:
        _log_analytics_export_audit(
            db, action=AuditAction.ANALYTICS_EXPORT_SYNC_FAILED, actor=current_user,
            report_type=request.report_type, export_format=request.export_format,
            filters=request.filters, status_value="failed", error_message="Invalid report type", sensitivity_level=3
        )
        raise HTTPException(status_code=400, detail="Invalid report type")

    # Excel Export
    if request.export_format and request.export_format.lower() == "excel":
        if openpyxl is None:
            raise HTTPException(status_code=500, detail="Excel export is not supported (openpyxl missing)")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = request.report_type.capitalize()
        
        ws.append(first_row_headers)
        for row in gen:
            ws.append(row)
            
        output = io.BytesIO()
        wb.save(output)
        
        filename = f"{request.report_type}_report_{start_date}_{end_date}.xlsx"
        _log_analytics_export_audit(db, action=AuditAction.ANALYTICS_EXPORT_SYNC, actor=current_user, report_type=request.report_type, export_format="EXCEL", filters=request.filters, status_value="completed", file_path=filename)
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    # Default: CSV Export (Streaming)
    filename = f"{request.report_type}_report_{start_date}_{end_date}.csv"
    _log_analytics_export_audit(db, action=AuditAction.ANALYTICS_EXPORT_SYNC, actor=current_user, report_type=request.report_type, export_format="CSV", filters=request.filters, status_value="completed", file_path=filename)

    def iter_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(first_row_headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        for row in gen:
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(iter_csv(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def get_enrollment_analytics(
    db: Session,
    period_start: date,
    period_end: date,
    kindergarten_id: Optional[int] = None,
    kindergarten_ids: Optional[List[int]] = None,
    status_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    reviewer_id: Optional[int] = None,
) -> Dict[str, Any]:
        """Get comprehensive enrollment/registration analytics"""
        query = db.query(models.EnrollmentApplication)

        if kindergarten_ids:
            query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids))
        elif kindergarten_id:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        if status_filter:
            try:
                query = query.filter(models.EnrollmentApplication.status == models.EnrollmentStatus(status_filter.upper()))
            except ValueError:
                pass

        if source_filter:
            query = query.filter(models.EnrollmentApplication.source == source_filter)

        if reviewer_id:
            query = query.filter(models.EnrollmentApplication.decision_by == reviewer_id)

        # Period filter on created_at for "new applications"
        period_query = query.filter(
            func.date(models.EnrollmentApplication.created_at) >= period_start,
            func.date(models.EnrollmentApplication.created_at) <= period_end,
        )

        # Applications by status
        status_counts = {}
        for status in models.EnrollmentStatus:
            count = query.filter(
                models.EnrollmentApplication.status == status
            ).count()
            status_counts[status.value] = count

        # New applications in period
        new_applications = period_query.count()

        # Conversion funnel
        total = query.count()
        active = status_counts.get("ACTIVE", 0)
        conversion_rate = (active / total * 100) if total > 0 else 0

        # Funnel stages: DRAFT → SUBMITTED → PENDING_REVIEW → ACCEPTED/REJECTED → ACTIVE
        funnel = {
            "draft": status_counts.get("DRAFT", 0),
            "submitted": status_counts.get("SUBMITTED", 0),
            "pending_review": status_counts.get("PENDING_REVIEW", 0),
            "accepted": status_counts.get("ACCEPTED", 0),
            "rejected": status_counts.get("REJECTED", 0),
            "active": status_counts.get("ACTIVE", 0),
            "waitlisted": status_counts.get("WAITLISTED", 0),
            "withdrawn": status_counts.get("WITHDRAWN", 0),
        }

        # Rejection reasons breakdown
        rejection_query = query.filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.REJECTED,
            models.EnrollmentApplication.status_reason.isnot(None),
            models.EnrollmentApplication.status_reason != "",
        )
        rejection_reasons = {}
        for ea in rejection_query.all():
            reason = ea.status_reason.strip()[:255]
            if reason:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

        # Approval workflow metrics
        decided_query = query.filter(
            models.EnrollmentApplication.decision_at.isnot(None),
            models.EnrollmentApplication.submitted_at.isnot(None),
        )
        approval_times = []
        reviewer_counts = {}
        for ea in decided_query.all():
            if ea.submitted_at and ea.decision_at:
                delta_hours = (ea.decision_at - ea.submitted_at).total_seconds() / 3600.0
                approval_times.append(delta_hours)
            if ea.decision_by:
                reviewer_counts[ea.decision_by] = reviewer_counts.get(ea.decision_by, 0) + 1

        avg_approval_hours = round(sum(approval_times) / len(approval_times), 2) if approval_times else 0
        rejection_rate = round((funnel["rejected"] / max(total, 1)) * 100, 2)

        # Source breakdown
        source_counts = {}
        for ea in query.filter(models.EnrollmentApplication.source.isnot(None)).all():
            src = ea.source or "UNKNOWN"
            source_counts[src] = source_counts.get(src, 0) + 1

        # Daily approval trend (decided per day within period)
        daily_decided = {}
        for ea in query.filter(
            models.EnrollmentApplication.decision_at.isnot(None),
            func.date(models.EnrollmentApplication.decision_at) >= period_start,
            func.date(models.EnrollmentApplication.decision_at) <= period_end,
        ).all():
            day = ea.decision_at.date().isoformat()
            daily_decided[day] = daily_decided.get(day, 0) + 1

        # Time-series for new applications per day in period
        daily_new = {}
        for ea in period_query.all():
            day = ea.created_at.date().isoformat()
            daily_new[day] = daily_new.get(day, 0) + 1

        return {
            "status_breakdown": status_counts,
            "new_applications": new_applications,
            "total_applications": total,
            "active_enrollments": active,
            "conversion_rate": round(conversion_rate, 2),
            "funnel": funnel,
            "rejection_reasons": rejection_reasons,
            "approval_workflow": {
                "avg_approval_hours": avg_approval_hours,
                "rejection_rate": rejection_rate,
                "reviewer_counts": reviewer_counts,
                "daily_decided": daily_decided,
            },
            "source_breakdown": source_counts,
            "daily_new_applications": daily_new,
        }

def get_attendance_analytics(
    db: Session,
    period_start: date,
    period_end: date,
    kindergarten_id: Optional[int] = None
) -> Dict[str, Any]:
        """Get attendance-specific analytics"""
        query = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        )

        if kindergarten_id:
            query = query.join(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        total_logs = query.count()

        # Attendance by day of week
        day_distribution = {}
        for i in range(7):
            day_name = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"][i]
            from sqlalchemy import extract
            count = query.filter(
                extract('dow', models.AttendanceLog.date) == i
            ).count()
            day_distribution[day_name] = count

        # Average daily attendance
        days_in_period = (period_end - period_start).days + 1
        avg_daily = total_logs / days_in_period if days_in_period > 0 else 0

        return {
            "total_attendance_logs": total_logs,
            "average_daily_attendance": round(avg_daily, 1),
            "day_of_week_distribution": day_distribution,
            "period_days": days_in_period
        }

def get_safety_analytics(
    db: Session,
    period_start: date,
    period_end: date,
    kindergarten_id: Optional[int] = None
) -> Dict[str, Any]:
        """Get safety/incident analytics"""
        query = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        )

        if kindergarten_id:
            query = query.filter(models.Incident.kindergarten_id == kindergarten_id)

        total_incidents = query.count()

        # By severity
        severity_counts = {}
        for severity in models.SeverityLevel:
            count = query.filter(models.Incident.severity_level == severity).count()
            severity_counts[severity.value] = count

        # By type
        type_counts = {}
        for inc_type in models.IncidentType:
            count = query.filter(models.Incident.type == inc_type).count()
            type_counts[inc_type.value] = count

        # Resolution rate (using closed_at since that's what the model has)
        resolved = query.filter(models.Incident.closed_at.isnot(None)).count()
        resolution_rate = (resolved / total_incidents * 100) if total_incidents > 0 else 0

        return {
            "total_incidents": total_incidents,
            "severity_breakdown": severity_counts,
            "type_breakdown": type_counts,
            "resolved_count": resolved,
            "resolution_rate": round(resolution_rate, 2)
        }

def get_staffing_analytics(
    db: Session,
    period_start: date,
    period_end: date,
    kindergarten_id: Optional[int] = None
) -> Dict[str, Any]:
        """Get staffing and ratio compliance analytics"""
        query = db.query(models.RatioCompliance).filter(
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end
        )

        if kindergarten_id:
            query = query.filter(models.RatioCompliance.kindergarten_id == kindergarten_id)

        # Sum up compliance data
        result = query.with_entities(
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes),
            func.avg(models.RatioCompliance.staff_count_avg),
            func.avg(models.RatioCompliance.child_count_avg)
        ).first()

        compliant_min = result[0] or 0
        operating_min = result[1] or 1
        avg_staff = result[2] or 0
        avg_children = result[3] or 0

        compliance_rate = (compliant_min / operating_min * 100) if operating_min > 0 else 0
        avg_ratio = (avg_children / avg_staff) if avg_staff > 0 else 0

        # Staff count by role
        staff_query = db.query(models.User).filter(
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            models.User.status == models.UserStatus.ACTIVE
        )
        if kindergarten_id:
            staff_query = staff_query.filter(models.User.kindergarten_id == kindergarten_id)

        staff_by_role = {}
        for role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
            count = staff_query.filter(models.User.role == role).count()
            staff_by_role[role.value] = count

        return {
            "compliance_rate": round(compliance_rate, 2),
            "average_staff_count": round(avg_staff, 1),
            "average_child_count": round(avg_children, 1),
            "average_ratio": round(avg_ratio, 1),
            "staff_by_role": staff_by_role,
            "compliant_minutes": compliant_min,
            "operating_minutes": operating_min
        }

def get_daily_reports_analytics(
    db: Session,
    period_start: date,
    period_end: date,
    kindergarten_id: Optional[int] = None
) -> Dict[str, Any]:
        """Get daily reports analytics"""
        query = db.query(models.DailyReport).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        )

        if kindergarten_id:
            query = query.join(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        total_reports = query.count()

        # By status
        status_counts = {}
        for status in models.DailyReportStatus:
            count = query.filter(models.DailyReport.status == status).count()
            status_counts[status.value] = count

        # Completion rate
        sent_count = status_counts.get("SENT", 0)
        completion_rate = (sent_count / total_reports * 100) if total_reports > 0 else 0

        return {
            "total_reports": total_reports,
            "status_breakdown": status_counts,
            "sent_count": sent_count,
            "completion_rate": round(completion_rate, 2)
        }


# =============================================================================
# API Endpoints
# =============================================================================

def get_time_series(
    db: Session,
    metric: str,
    dimension_type: str,
    dimension_id: Optional[str],
    period_start: date,
    period_end: date,
    granularity: str = "daily",
    kg_scope: Optional[List[int]] = None
) -> List[TimeSeriesPoint]:
    """Get time series data for charts (global helper with scoping support)."""
    points: List[TimeSeriesPoint] = []
    current = period_start
    dim_upper = dimension_type.upper() if dimension_type else "NETWORK"

    while current <= period_end:
        if granularity == "daily":
            next_date = current + timedelta(days=1)
        elif granularity == "weekly":
            next_date = current + timedelta(weeks=1)
        elif granularity == "monthly":
            if current.month == 12:
                next_date = date(current.year + 1, 1, 1)
            else:
                next_date = date(current.year, current.month + 1, 1)
        else:
            next_date = current + timedelta(days=1)

        value = 0.0

        if metric == "attendance_rate":
            if dim_upper == "NETWORK":
                total_children_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
                    models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
                )
                actual_q = db.query(func.count(models.AttendanceLog.id)).filter(
                    models.AttendanceLog.date >= current,
                    models.AttendanceLog.date < next_date
                )
                if kg_scope:
                    total_children_q = total_children_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_scope))
                    actual_q = actual_q.join(models.Child).join(
                        models.EnrollmentApplication,
                        models.EnrollmentApplication.child_id == models.Child.id
                    ).filter(models.EnrollmentApplication.kindergarten_id.in_(kg_scope))
                total_children = total_children_q.scalar() or 1
                actual = actual_q.scalar() or 0
                value = (actual / total_children * 100) if total_children > 0 else 0
            elif dim_upper == "KINDERGARTEN" and kg_scope:
                value = KPIService.compute_attendance_rate(
                    db, kg_scope[0], current, next_date - timedelta(days=1)
                )
            elif dim_upper == "GOVERNORATE" and kg_scope:
                value = AnalyticsService._compute_network_attendance_rate(
                    db, current, next_date - timedelta(days=1), kg_scope
                )

        elif metric == "incident_count":
            query = db.query(func.count(models.Incident.id)).filter(
                func.date(models.Incident.occurred_at) >= current,
                func.date(models.Incident.occurred_at) < next_date
            )
            if dim_upper in ("KINDERGARTEN", "GOVERNORATE") and kg_scope:
                query = query.filter(models.Incident.kindergarten_id.in_(kg_scope))
            value = query.scalar() or 0

        elif metric == "enrollment_count":
            query = db.query(func.count(models.EnrollmentApplication.id)).filter(
                func.date(models.EnrollmentApplication.created_at) >= current,
                func.date(models.EnrollmentApplication.created_at) < next_date
            )
            if dim_upper in ("KINDERGARTEN", "GOVERNORATE") and kg_scope:
                query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_scope))
            value = query.scalar() or 0

        points.append(TimeSeriesPoint(date=current.isoformat(), value=round(value, 2)))
        current = next_date

    return points


@router.get("/overview")
def get_analytics_overview(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get network-wide analytics overview (admin only)
    """
    validators.validate_admin_role(current_user)
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    allowed_govs = _allowed_governorates(current_user, db) or []

    period_start, period_end = get_date_range(start_date, end_date)

    summary = AnalyticsService.get_network_summary(db, period_start, period_end, allowed_kgs)
    governorates = AnalyticsService.get_governorate_breakdown(
        db, period_start, period_end, None, allowed_kgs, allowed_govs
    )

    # Include all Jordan governorates for filter dropdown, even if no data
    from config import settings
    visible_governorates = settings.JORDAN_GOVERNORATES if current_user.role == models.UserRole.ADMIN else allowed_govs
    visible_governorates = visible_governorates or []

    all_governorates = []
    for gov_name in visible_governorates:
        # Find if we have data for this governorate
        existing = next((g for g in governorates if g.governorate == gov_name), None)
        if existing:
            all_governorates.append(existing)
        else:
            # Add empty entry for governorates with no data
            all_governorates.append(GovernorateMetrics(
                governorate=gov_name,
                kindergarten_count=0,
                children_count=0,
                capacity=0,
                enrollment_rate=0.0,
                attendance_rate=0.0,
                incident_rate=0.0,
                governance_score=0.0
            ))

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "summary": summary,
        "governorates": all_governorates
    }


@router.get("/drilldown/{dimension_type}/{dimension_id}")
def get_drilldown(
    dimension_type: str,
    dimension_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Drill down into a specific dimension (governorate, kindergarten, class, child)
    """
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    allowed_govs = _allowed_governorates(current_user, db) or []
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    period_start, period_end = get_date_range(start_date, end_date)

    if dimension_type.upper() == "GOVERNORATE":
        if current_user.role != models.UserRole.ADMIN and allowed_govs and dimension_id not in allowed_govs:
            raise HTTPException(status_code=403, detail="Governorate not allowed")

        kg_ids = _kg_ids_for_governorate(db, dimension_id) or []
        if allowed_kgs is not None:
            kg_ids = [kg for kg in kg_ids if kg in allowed_kgs]
        if not kg_ids:
            raise HTTPException(status_code=403, detail="No allowed kindergartens in this governorate")

        # Get all kindergartens in this governorate
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.id.in_(kg_ids),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        children_list = []
        for kg in kindergartens:
            metrics = AnalyticsService.get_kindergarten_metrics(
                db, kg.id, period_start, period_end
            )
            children_list.append(metrics.model_dump())

        return DrilldownResponse(
            dimension_type="GOVERNORATE",
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            period_start=period_start,
            period_end=period_end,
            metrics={"kindergarten_count": len(kindergartens)},
            children=children_list
        )

    elif dimension_type.upper() == "KINDERGARTEN":
        kg_id = enforce_kindergarten_scope(current_user, int(dimension_id), db)
        metrics = AnalyticsService.get_kindergarten_metrics(
            db, kg_id, period_start, period_end
        )

        # Get classes
        classes = db.query(models.Class).filter(
            models.Class.kindergarten_id == kg_id
        ).all()

        class_list = []
        for cls in classes:
            # Count children in class
            children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.class_id == cls.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Compute age group from min/max months
            age_group = f"{cls.min_age_months}-{cls.max_age_months} شهر"

            class_list.append({
                "id": cls.id,
                "name": cls.name_ar,
                "capacity": cls.capacity_total,
                "children_count": children_count,
                "age_group": age_group
            })

        return DrilldownResponse(
            dimension_type="KINDERGARTEN",
            dimension_id=dimension_id,
            dimension_name=metrics.name,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics.model_dump(),
            children=class_list
        )

    elif dimension_type.upper() == "CLASS":
        cls_id = int(dimension_id)
        cls = db.query(models.Class).filter(models.Class.id == cls_id).first()

        if not cls:
            raise HTTPException(status_code=404, detail="Class not found")
        enforce_kindergarten_scope(current_user, cls.kindergarten_id, db)

        # Get children in class
        enrollments = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.class_id == cls_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()

        children_list = []
        for enrollment in enrollments:
            child = enrollment.child
            if child:
                # Get attendance for this child
                attendance_count = db.query(func.count(models.AttendanceLog.id)).filter(
                    models.AttendanceLog.child_id == child.id,
                    models.AttendanceLog.date >= period_start,
                    models.AttendanceLog.date <= period_end
                ).scalar() or 0

                days_in_period = (period_end - period_start).days + 1
                attendance_rate = (attendance_count / days_in_period * 100) if days_in_period > 0 else 0

                children_list.append({
                    "id": child.id,
                    "name": f"{child.first_name} {child.last_name}",
                    "attendance_rate": round(attendance_rate, 2),
                    "attendance_days": attendance_count
                })

        # Compute age group from min/max months
        cls_age_group = f"{cls.min_age_months}-{cls.max_age_months} شهر"

        return DrilldownResponse(
            dimension_type="CLASS",
            dimension_id=dimension_id,
            dimension_name=cls.name_ar,
            period_start=period_start,
            period_end=period_end,
            metrics={
                "capacity": cls.capacity_total,
                "children_count": len(children_list),
                "age_group": cls_age_group
            },
            children=children_list
        )

    raise HTTPException(status_code=400, detail="Invalid dimension type")


@router.get("/time-series")
def get_time_series_data(
    metric: str = Query(..., description="Metric to chart: attendance_rate, incident_count, enrollment_count"),
    dimension_type: str = Query("NETWORK"),
    dimension_id: Optional[str] = Query(None),
    granularity: str = Query("daily", description="daily, weekly, monthly"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get time series data for charts (admin only)"""
    validators.validate_admin_role(current_user)
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    allowed_govs = _allowed_governorates(current_user, db) or []

    # Scope enforcement by dimension
    dim_upper = dimension_type.upper()
    if dim_upper == "KINDERGARTEN":
        enforced = enforce_kindergarten_scope(current_user, int(dimension_id) if dimension_id else None, db)
        dimension_id = str(enforced) if enforced else None
        kg_scope = [int(dimension_id)] if dimension_id else allowed_kgs
    elif dim_upper == "GOVERNORATE":
        if current_user.role != models.UserRole.ADMIN:
            if not allowed_kgs:
                raise HTTPException(status_code=403, detail="Access denied")
            if dimension_id and dimension_id not in allowed_govs:
                raise HTTPException(status_code=403, detail="Governorate not allowed")
        kg_scope = _kg_ids_for_governorate(db, dimension_id) if dimension_id else None
        if allowed_kgs is not None and kg_scope is not None:
            kg_scope = [kg for kg in kg_scope if kg in allowed_kgs]
    else:  # NETWORK or others
        if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")
        kg_scope = allowed_kgs

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_time_series(
        db, metric, dimension_type, dimension_id, period_start, period_end, granularity, kg_scope
    )

    return {
        "metric": metric,
        "dimension_type": dimension_type,
        "dimension_id": dimension_id,
        "granularity": granularity,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "data": [p.model_dump() for p in data]
    }


@router.get("/compare")
def compare_kindergartens(
    kg_ids: str = Query(..., description="Comma-separated kindergarten IDs"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compare multiple kindergartens side by side"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    period_start, period_end = get_date_range(start_date, end_date)

    ids = [int(x.strip()) for x in kg_ids.split(",") if x.strip()]
    if allowed_kgs is not None:
        ids = [i for i in ids if i in allowed_kgs]
    if not ids:
        raise HTTPException(status_code=403, detail="No permitted kindergartens to compare")

    comparisons = []
    for kg_id in ids:
        try:
            metrics = AnalyticsService.get_kindergarten_metrics(
                db, kg_id, period_start, period_end
            )
            comparisons.append(metrics.model_dump())
        except HTTPException:
            continue

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergartens": comparisons
    }


@router.get("/rankings/{metric}")
def get_metric_rankings(
    metric: str,
    top_n: int = Query(10, ge=1, le=50),
    bottom: bool = Query(False),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get kindergarten rankings by a specific metric"""
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    rankings = AnalyticsService.get_rankings(
        db, metric, period_start, period_end, top_n, bottom, kg_filter
    )

    return {
        "metric": metric,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "order": "bottom" if bottom else "top",
        "rankings": [r.model_dump() for r in rankings]
    }


@router.get("/governance-distribution", response_model=GovernanceDistribution)
def get_governance_distribution_endpoint(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the distribution of kindergartens by governance band."""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")
    period_start, period_end = get_date_range(start_date, end_date)
    return AnalyticsService.get_governance_distribution(db, period_start, period_end, allowed_kgs)


# =============================================================================
# Missing High-Priority Endpoints
# =============================================================================

@router.get("/kpi")
def get_kpi_analytics(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get KPI analytics summary for dashboard displays."""
    period_start, period_end = get_date_range(start_date, end_date)
    
    # Scope by user role
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        kg_id = current_user.kindergarten_id
    
    # Get attendance rate
    attendance_rate = 0.0
    try:
        total_logs = db.query(models.AttendanceLog).join(
            models.Class, models.AttendanceLog.class_id == models.Class.id
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        )
        if kg_id:
            total_logs = total_logs.filter(models.Class.kindergarten_id == kg_id)
        attendance_count = total_logs.count()
        
        children_query = db.query(models.Child)
        if kg_id:
            children_query = children_query.join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id,
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.is_active.is_(True),
            ).distinct()
        total_children = children_query.count()
        
        days_in_period = (period_end - period_start).days + 1
        expected_logs = total_children * days_in_period
        if expected_logs > 0:
            attendance_rate = round((attendance_count / expected_logs) * 100, 2)
    except SQLAlchemyError as e:
        logger.error(
            "Failed to compute attendance rate KPI for kg_id=%s period=[%s,%s]: %s",
            kg_id, period_start, period_end, str(e),
            exc_info=True
        )
    except ZeroDivisionError as e:
        logger.warning("Division by zero in attendance rate calculation: %s", str(e))
    except (TypeError, ValueError) as e:
        logger.error(
            "Invalid data computing attendance rate KPI: %s", str(e),
            exc_info=True, extra={"kg_id": kg_id, "period_start": period_start, "period_end": period_end}
        )
    
    # Get governance score
    governance_score = 0.0
    try:
        scores_query = db.query(func.avg(models.GovernanceScore.final_governance_score)).filter(
            models.GovernanceScore.period_start <= period_end,
            models.GovernanceScore.period_end >= period_start,
        )
        if kg_id:
            scores_query = scores_query.filter(models.GovernanceScore.kindergarten_id == kg_id)
        avg_score = scores_query.scalar()
        governance_score = round(float(avg_score) if avg_score else 0.0, 2)
    except SQLAlchemyError as e:
        logger.error(
            "Failed to compute governance score KPI for kg_id=%s period=[%s,%s]: %s",
            kg_id, period_start, period_end, str(e),
            exc_info=True
        )
    except (TypeError, ValueError) as e:
        logger.warning("Invalid data in governance score calculation: %s", str(e))
    
    # Get incident rate
    incident_rate = 0.0
    try:
        incidents_query = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        )
        if kg_id:
            incidents_query = incidents_query.filter(models.Incident.kindergarten_id == kg_id)
        incident_count = incidents_query.count()
        
        attended_logs_q = db.query(models.AttendanceLog).join(
            models.Class, models.AttendanceLog.class_id == models.Class.id
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ])
        )
        if kg_id:
            attended_logs_q = attended_logs_q.filter(models.Class.kindergarten_id == kg_id)
        attended_child_days = attended_logs_q.count()
        if attended_child_days > 0:
            incident_rate = round((incident_count / attended_child_days) * 1000, 3)
    except SQLAlchemyError as e:
        logger.error(
            "Failed to compute incident rate KPI for kg_id=%s period=[%s,%s]: %s",
            kg_id, period_start, period_end, str(e),
            exc_info=True
        )
    except ZeroDivisionError as e:
        logger.warning("Division by zero in incident rate calculation: %s", str(e))
    except (TypeError, ValueError) as e:
        logger.error(
            "Invalid data computing incident rate KPI: %s", str(e),
            exc_info=True
        )
    
    # Get report completion rate
    report_completion = 0.0
    try:
        reports_query = db.query(models.DailyReport).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
        )
        if kg_id:
            reports_query = reports_query.filter(models.DailyReport.kindergarten_id == kg_id)
        total_reports = reports_query.count()
        completed_reports = reports_query.filter(
            models.DailyReport.status.in_([
                models.DailyReportStatus.APPROVED,
                models.DailyReportStatus.SENT_TO_PARENT,
            ])
        ).count()
        if total_reports > 0:
            report_completion = round((completed_reports / total_reports) * 100, 2)
    except SQLAlchemyError as e:
        logger.error(
            "Failed to compute report completion KPI for kg_id=%s period=[%s,%s]: %s",
            kg_id, period_start, period_end, str(e),
            exc_info=True
        )
    except ZeroDivisionError as e:
        logger.warning("Division by zero in report completion calculation: %s", str(e))
    except (TypeError, ValueError) as e:
        logger.error(
            "Invalid data computing report completion KPI: %s", str(e),
            exc_info=True
        )
    
    return {
        "attendance_rate": attendance_rate,
        "governance_score": governance_score,
        "incident_rate": incident_rate,
        "report_completion": report_completion,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat()
    }


@router.get("/attendance")
def get_analytics_attendance(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attendance analytics for dashboard displays."""
    period_start, period_end = get_date_range(start_date, end_date)
    
    # Scope by user role
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        kg_id = current_user.kindergarten_id
    
    today = _jordan_today()

    # Get total children
    children_query = db.query(models.Child)
    if kg_id:
        enrolled_parent_ids = db.query(models.EnrollmentApplication.parent_id).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ENROLLED
        ).subquery()
        children_query = children_query.filter(models.Child.parent_id.in_(enrolled_parent_ids))
    total_children = children_query.count()
    
    # Get present today
    present_today = db.query(models.AttendanceLog).join(
        models.Class, models.AttendanceLog.class_id == models.Class.id
    ).filter(
        models.AttendanceLog.date == today,
        models.AttendanceLog.check_out_at.is_(None)  # Still present
    )
    if kg_id:
        present_today = present_today.filter(models.Class.kindergarten_id == kg_id)
    present_count = present_today.count()
    
    # Calculate attendance rate over period
    attendance_logs = db.query(models.AttendanceLog).join(
        models.Class, models.AttendanceLog.class_id == models.Class.id
    ).filter(
        models.AttendanceLog.date >= period_start,
        models.AttendanceLog.date <= period_end
    )
    if kg_id:
        attendance_logs = attendance_logs.filter(models.Class.kindergarten_id == kg_id)
    
    days_in_period = (period_end - period_start).days + 1
    expected_logs = total_children * days_in_period
    actual_logs = attendance_logs.count()
    
    attendance_rate = round((actual_logs / expected_logs * 100) if expected_logs > 0 else 0, 2)
    
    # Chronic absence rate (children absent more than 20% of days)
    chronic_threshold = days_in_period * 0.8  # Present less than 80%
    chronic_absence_rate = 0.0
    # Simplified - would need subquery in production
    
    return {
        "attendance_rate": attendance_rate,
        "chronic_absence_rate": chronic_absence_rate,
        "present_today": present_count,
        "total_children": total_children,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat()
    }


@router.get("/dashboard")
def get_analytics_dashboard(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get consolidated analytics dashboard data."""
    period_start, period_end = get_date_range(start_date, end_date)
    
    # Scope by user role
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        kg_id = current_user.kindergarten_id
    
    # Summary stats
    total_kindergartens = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).count()
    
    total_children = db.query(models.Child).count()
    
    total_staff = db.query(models.User).filter(
        models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
        models.User.status == models.UserStatus.ACTIVE
    ).count()
    
    # Get KPIs
    kpis = {
        "attendance_rate": 0.0,
        "governance_score": 0.0,
        "incident_rate": 0.0,
        "report_completion": 0.0
    }
    
    try:
        # Attendance rate
        attendance_logs = db.query(models.AttendanceLog).join(
            models.Class, models.AttendanceLog.class_id == models.Class.id
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        )
        if kg_id:
            attendance_logs = attendance_logs.filter(models.Class.kindergarten_id == kg_id)
        attendance_count = attendance_logs.count()
        
        days_in_period = (period_end - period_start).days + 1
        expected = total_children * days_in_period
        kpis["attendance_rate"] = round((attendance_count / expected * 100) if expected > 0 else 0, 2)
        
        # Governance score
        governance_query = db.query(func.avg(models.GovernanceScore.final_governance_score)).filter(
            models.GovernanceScore.period_start <= period_end,
            models.GovernanceScore.period_end >= period_start,
        )
        if kg_id:
            governance_query = governance_query.filter(models.GovernanceScore.kindergarten_id == kg_id)
        avg_governance = governance_query.scalar()
        kpis["governance_score"] = round(float(avg_governance) if avg_governance else 0, 2)
        
        # Incidents
        incidents = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        )
        if kg_id:
            incidents = incidents.filter(models.Incident.kindergarten_id == kg_id)
        incident_count = incidents.count()
        attended_q = db.query(models.AttendanceLog).join(
            models.Class, models.AttendanceLog.class_id == models.Class.id
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ])
        )
        if kg_id:
            attended_q = attended_q.filter(models.Class.kindergarten_id == kg_id)
        attended_child_days_gov = attended_q.count()
        kpis["incident_rate"] = round((incident_count / attended_child_days_gov * 1000) if attended_child_days_gov > 0 else 0, 3)
        
        # Report completion
        reports = db.query(models.DailyReport).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
        )
        if kg_id:
            reports = reports.filter(models.DailyReport.kindergarten_id == kg_id)
        total_reports = reports.count()
        completed = reports.filter(
            models.DailyReport.status.in_([
                models.DailyReportStatus.APPROVED,
                models.DailyReportStatus.SENT_TO_PARENT,
            ])
        ).count()
        kpis["report_completion"] = round((completed / total_reports * 100) if total_reports > 0 else 0, 2)
    except SQLAlchemyError:
        logger.exception("Failed to compute dashboard KPIs due to database error")
    except (ZeroDivisionError, TypeError, ValueError):
        logger.exception("Failed to compute dashboard KPIs due to invalid analytics data")
    
    return {
        "summary": {
            "total_kindergartens": total_kindergartens,
            "total_children": total_children,
            "total_staff": total_staff
        },
        "kpis": kpis,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat()
    }



@router.get("/enrollments/summary")
def get_enrollment_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    reviewer_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get enrollment analytics (admin only)"""
    validators.validate_admin_role(current_user)
    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_enrollment_analytics(
        db, period_start, period_end, kindergarten_id,
        status_filter=status, source_filter=source, reviewer_id=reviewer_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/registration/analytics")
def get_registration_analytics(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    reviewer_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive registration/enrollment analytics with multi-dimensional filtering."""
    validators.validate_admin_role(current_user)

    # Resolve governorate to kindergarten IDs if provided
    kg_ids = None
    if governorate:
        kg_ids = _kg_ids_for_governorate(db, governorate) or None
        if kg_ids is None and kindergarten_id:
            kg_ids = [kindergarten_id]
    elif kindergarten_id:
        kg_ids = None  # Let enforce_kindergarten_scope handle single ID

    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_enrollment_analytics(
        db, period_start, period_end,
        kindergarten_id=kindergarten_id if not kg_ids else None,
        kindergarten_ids=kg_ids,
        status_filter=status, source_filter=source, reviewer_id=reviewer_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        "filters_applied": {
            "status": status,
            "source": source,
            "reviewer_id": reviewer_id,
            "governorate": governorate,
        },
        **data
    }


@router.get("/registration/drilldown")
def get_registration_drilldown(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    reviewer_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get paginated enrollment records with multi-dimensional filtering for drill-down."""
    validators.validate_admin_role(current_user)

    # Resolve governorate to kindergarten IDs if provided
    kg_ids = None
    if governorate:
        kg_ids = _kg_ids_for_governorate(db, governorate) or None
        if kg_ids is None and kindergarten_id:
            kg_ids = [kindergarten_id]
    elif kindergarten_id:
        kg_ids = None

    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)
    offset = (page - 1) * page_size

    query = db.query(models.EnrollmentApplication).join(
        models.Child, models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.ParentProfile, models.Child.parent_id == models.ParentProfile.id
    ).join(
        models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    ).outerjoin(
        models.User, models.EnrollmentApplication.decision_by == models.User.id
    )

    if kg_ids:
        query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
    elif kindergarten_id:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

    if status:
        try:
            query = query.filter(models.EnrollmentApplication.status == models.EnrollmentStatus(status.upper()))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if source:
        query = query.filter(models.EnrollmentApplication.source == source)

    if reviewer_id:
        query = query.filter(models.EnrollmentApplication.decision_by == reviewer_id)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(or_(
            models.Child.first_name.ilike(search_term),
            models.Child.last_name.ilike(search_term),
            models.ParentProfile.first_name.ilike(search_term),
            models.ParentProfile.last_name.ilike(search_term),
            models.Kindergarten.name_ar.ilike(search_term),
            models.Kindergarten.name_en.ilike(search_term),
        ))

    total = query.count()
    records = query.order_by(models.EnrollmentApplication.created_at.desc()).offset(offset).limit(page_size).all()

    # Batch-fetch all related objects to avoid N+1 queries
    _child_ids = [ea.child_id for ea in records if ea.child_id]
    _kg_ids = list({ea.kindergarten_id for ea in records if ea.kindergarten_id})
    _reviewer_ids = list({ea.decision_by for ea in records if ea.decision_by})
    _children_map = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(_child_ids)).all()}
    _parent_ids = list({c.parent_id for c in _children_map.values() if c.parent_id})
    _parents_map = {p.id: p for p in db.query(models.ParentProfile).filter(models.ParentProfile.id.in_(_parent_ids)).all()}
    _kg_map = {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(_kg_ids)).all()}
    _reviewer_map = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(_reviewer_ids)).all()}

    items = []
    for ea in records:
        child = _children_map.get(ea.child_id)
        parent = _parents_map.get(child.parent_id) if child else None
        kg = _kg_map.get(ea.kindergarten_id)
        reviewer = _reviewer_map.get(ea.decision_by)

        items.append({
            "id": ea.id,
            "public_id": ea.public_id,
            "child_name": f"{child.first_name} {child.last_name}" if child else "N/A",
            "parent_name": f"{parent.first_name} {parent.last_name}" if parent else "N/A",
            "kindergarten_name": kg.name_ar or kg.name_en if kg else "N/A",
            "kindergarten_city": kg.district if kg else "N/A",
            "status": ea.status.value if hasattr(ea.status, 'value') else str(ea.status),
            "status_reason": ea.status_reason,
            "source": ea.source,
            "submitted_at": _to_jordan_iso(ea.submitted_at),
            "accepted_at": _to_jordan_iso(ea.accepted_at),
            "rejected_at": _to_jordan_iso(ea.rejected_at),
            "decision_at": _to_jordan_iso(ea.decision_at),
            "reviewer_name": f"{reviewer.full_name or reviewer.username}" if reviewer else None,
            "created_at": _to_jordan_iso(ea.created_at),
        })

    total_pages = (total + page_size - 1) // page_size
    return {
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "filters_applied": {
            "status": status,
            "source": source,
            "reviewer_id": reviewer_id,
            "search": search,
        },
    }


@router.get("/registration/quality-breakdown")
def get_registration_quality_breakdown(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Governorate-level registration breakdown, profile completeness, monthly trends."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)
    kg_ids_filter = _kg_ids_for_governorate(db, governorate) if governorate else None

    # ── Governorate breakdown ─────────────────────────────────────────────────
    gov_q = db.query(
        models.Kindergarten.governorate,
        func.count(models.Kindergarten.id).label("kg_total"),
    ).filter(models.Kindergarten.governorate.isnot(None))
    if kg_ids_filter:
        gov_q = gov_q.filter(models.Kindergarten.id.in_(kg_ids_filter))
    gov_rows_raw = (
        gov_q.group_by(models.Kindergarten.governorate)
             .order_by(desc("kg_total"))
             .limit(12)
             .all()
    )

    gov_rows: List[Dict[str, Any]] = []
    for gov_name, kg_total in gov_rows_raw:
        kg_gov_q = db.query(models.Kindergarten).filter(
            models.Kindergarten.governorate == gov_name
        )
        if kg_ids_filter:
            kg_gov_q = kg_gov_q.filter(models.Kindergarten.id.in_(kg_ids_filter))

        kg_active = kg_gov_q.filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).count()
        kg_draft = kg_gov_q.filter(
            models.Kindergarten.status == models.KindergartenStatus.DRAFT
        ).count()

        kg_ids_gov: List[int] = [r[0] for r in kg_gov_q.with_entities(models.Kindergarten.id).all()]

        if kg_ids_gov:
            ea_gov_q = db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids_gov)
            )
            total_enroll   = ea_gov_q.count()
            pending_enroll = ea_gov_q.filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW
            ).count()
            active_enroll  = ea_gov_q.filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).count()
        else:
            total_enroll = pending_enroll = active_enroll = 0

        completion_rate = round(active_enroll / max(total_enroll, 1) * 100, 1)
        gov_rows.append({
            "governorate":         gov_name,
            "kg_total":            kg_total,
            "kg_active":           kg_active,
            "kg_draft":            kg_draft,
            "enrollments_total":   total_enroll,
            "enrollments_pending": pending_enroll,
            "enrollments_active":  active_enroll,
            "completion_rate":     completion_rate,
        })

    # ── Profile completeness ───────────────────────────────────────────────────
    pp_q        = db.query(models.ParentProfile).filter(models.ParentProfile.deleted_at.is_(None))
    pp_total    = pp_q.count()
    pp_complete = pp_q.filter(models.ParentProfile.profile_complete == True).count()

    ch_q        = db.query(models.Child).filter(models.Child.deleted_at.is_(None))
    ch_total    = ch_q.count()
    ch_complete = ch_q.filter(models.Child.profile_complete == True).count()

    kg_all_q         = db.query(models.Kindergarten)
    if kg_ids_filter:
        kg_all_q = kg_all_q.filter(models.Kindergarten.id.in_(kg_ids_filter))
    kg_all_total     = kg_all_q.count()
    kg_with_license  = kg_all_q.filter(models.Kindergarten.license_number.isnot(None)).count()
    kg_with_location = kg_all_q.filter(
        models.Kindergarten.latitude.isnot(None),
        models.Kindergarten.longitude.isnot(None),
    ).count()

    staff_q = db.query(models.User).filter(
        models.User.deleted_at.is_(None),
        models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
    )
    if kg_ids_filter:
        staff_q = staff_q.filter(models.User.kindergarten_id.in_(kg_ids_filter))
    staff_total    = staff_q.count()
    staff_complete = staff_q.filter(
        models.User.full_name.isnot(None),
        models.User.full_name != "",
        models.User.phone_number.isnot(None),
    ).count()

    completeness = {
        "parent_profiles": {
            "total":    pp_total,
            "complete": pp_complete,
            "pct":      round(pp_complete / max(pp_total, 1) * 100, 1),
        },
        "children_profiles": {
            "total":    ch_total,
            "complete": ch_complete,
            "pct":      round(ch_complete / max(ch_total, 1) * 100, 1),
        },
        "kg_licensed": {
            "total":    kg_all_total,
            "complete": kg_with_license,
            "pct":      round(kg_with_license / max(kg_all_total, 1) * 100, 1),
        },
        "kg_geolocated": {
            "total":    kg_all_total,
            "complete": kg_with_location,
            "pct":      round(kg_with_location / max(kg_all_total, 1) * 100, 1),
        },
        "staff_profiles": {
            "total":    staff_total,
            "complete": staff_complete,
            "pct":      round(staff_complete / max(staff_total, 1) * 100, 1),
        },
    }

    # ── Monthly registration trends (last 6 months) ────────────────────────────
    def _next_month(d: date) -> date:
        return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)

    mo_labels: List[str] = []
    mo_ranges: List[tuple] = []
    cur = date(period_end.year, period_end.month, 1)
    for _ in range(6):
        nxt    = _next_month(cur)
        mo_end = nxt - timedelta(days=1)
        mo_labels.insert(0, cur.strftime("%Y-%m"))
        mo_ranges.insert(0, (cur, min(mo_end, period_end)))
        cur = date(cur.year - 1, 12, 1) if cur.month == 1 else date(cur.year, cur.month - 1, 1)

    monthly_users       : List[int] = []
    monthly_kgs         : List[int] = []
    monthly_enrollments : List[int] = []
    for mo_start, mo_end in mo_ranges:
        monthly_users.append(
            db.query(models.User).filter(
                func.date(models.User.created_at) >= mo_start,
                func.date(models.User.created_at) <= mo_end,
                models.User.deleted_at.is_(None),
            ).count()
        )
        kg_mo_q = db.query(models.Kindergarten).filter(
            func.date(models.Kindergarten.created_at) >= mo_start,
            func.date(models.Kindergarten.created_at) <= mo_end,
        )
        if kg_ids_filter:
            kg_mo_q = kg_mo_q.filter(models.Kindergarten.id.in_(kg_ids_filter))
        monthly_kgs.append(kg_mo_q.count())

        ea_mo_q = db.query(models.EnrollmentApplication).filter(
            func.date(models.EnrollmentApplication.created_at) >= mo_start,
            func.date(models.EnrollmentApplication.created_at) <= mo_end,
        )
        if kg_ids_filter:
            ea_mo_q = ea_mo_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids_filter))
        monthly_enrollments.append(ea_mo_q.count())

    return {
        "period_start":          period_start.isoformat(),
        "period_end":            period_end.isoformat(),
        "governorate_breakdown": gov_rows,
        "completeness":          completeness,
        "monthly_trends": {
            "labels":       mo_labels,
            "users":        monthly_users,
            "kindergartens": monthly_kgs,
            "enrollments":  monthly_enrollments,
        },
    }


@router.get("/registration/entity-summary")
def get_registration_entity_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Multi-entity registration status: users, kindergartens, enrollments, children, quality indicators."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)
    kg_ids = _kg_ids_for_governorate(db, governorate) if governorate else None

    # ── Users ──────────────────────────────────────────────────────────────────
    user_q = db.query(models.User).filter(models.User.deleted_at.is_(None))
    if kg_ids:
        user_q = user_q.filter(models.User.kindergarten_id.in_(kg_ids))

    users_total     = user_q.count()
    users_active    = user_q.filter(models.User.status == models.UserStatus.ACTIVE).count()
    users_suspended = user_q.filter(models.User.status == models.UserStatus.SUSPENDED).count()
    users_inactive  = user_q.filter(models.User.status == models.UserStatus.INACTIVE).count()
    users_by_role   = {r.value: user_q.filter(models.User.role == r).count() for r in models.UserRole}
    users_new       = user_q.filter(
        func.date(models.User.created_at) >= period_start,
        func.date(models.User.created_at) <= period_end,
    ).count()

    # ── Kindergartens ───────────────────────────────────────────────────────────
    kg_q = db.query(models.Kindergarten)
    if kg_ids:
        kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_ids))

    kg_total    = kg_q.count()
    kg_active   = kg_q.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).count()
    kg_inactive = kg_q.filter(models.Kindergarten.status == models.KindergartenStatus.INACTIVE).count()
    kg_draft    = kg_q.filter(models.Kindergarten.status == models.KindergartenStatus.DRAFT).count()
    kg_new      = kg_q.filter(
        func.date(models.Kindergarten.created_at) >= period_start,
        func.date(models.Kindergarten.created_at) <= period_end,
    ).count()

    # ── Enrollment applications ─────────────────────────────────────────────────
    ea_q = db.query(models.EnrollmentApplication)
    if kg_ids:
        ea_q = ea_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))

    ea_total      = ea_q.count()
    status_counts = {s.value: ea_q.filter(models.EnrollmentApplication.status == s).count()
                     for s in models.EnrollmentStatus}
    ea_new        = ea_q.filter(
        func.date(models.EnrollmentApplication.created_at) >= period_start,
        func.date(models.EnrollmentApplication.created_at) <= period_end,
    ).count()

    # Quality indicators
    now = _jordan_now()
    stalled_draft    = ea_q.filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.DRAFT,
        models.EnrollmentApplication.created_at < now - timedelta(days=30),
    ).count()
    overdue_pending  = ea_q.filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
        models.EnrollmentApplication.created_at < now - timedelta(days=7),
    ).count()
    long_submitted   = ea_q.filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.SUBMITTED,
        models.EnrollmentApplication.created_at < now - timedelta(days=14),
    ).count()

    ea_accepted      = status_counts.get("ACCEPTED", 0) + status_counts.get("ACTIVE", 0)
    conversion_rate  = round(ea_accepted / ea_total * 100, 1) if ea_total else 0.0
    rejection_rate   = round(status_counts.get("REJECTED", 0) / ea_total * 100, 1) if ea_total else 0.0

    # ── Children ────────────────────────────────────────────────────────────────
    child_q        = db.query(models.Child).filter(models.Child.deleted_at.is_(None))
    children_total = child_q.count()

    enrolled_ids = (
        db.query(models.EnrollmentApplication.child_id)
        .filter(models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
    )
    if kg_ids:
        enrolled_ids = enrolled_ids.filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
        )
    enrolled_ids = {r[0] for r in enrolled_ids.all()}

    pending_ids = (
        db.query(models.EnrollmentApplication.child_id)
        .filter(models.EnrollmentApplication.status.in_([
            models.EnrollmentStatus.PENDING_REVIEW,
            models.EnrollmentStatus.SUBMITTED,
        ]))
    )
    if kg_ids:
        pending_ids = pending_ids.filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
        )
    pending_ids = {r[0] for r in pending_ids.all()}

    children_enrolled         = len(enrolled_ids)
    children_pending          = len(pending_ids - enrolled_ids)
    children_without_enrollment = max(0, children_total - children_enrolled - children_pending)

    # ── Actions required ────────────────────────────────────────────────────────
    actions: List[Dict[str, Any]] = []
    if overdue_pending:
        actions.append({
            "type": "overdue_reviews", "count": overdue_pending, "priority": "high",
            "label_ar": "طلبات تأخرت في المراجعة (أكثر من 7 أيام)",
            "action_ar": "مراجعة الطلبات المعلقة",
            "url": "/enrollments?status=PENDING_REVIEW",
        })
    if long_submitted:
        actions.append({
            "type": "long_submitted", "count": long_submitted, "priority": "medium",
            "label_ar": "طلبات مقدمة دون مراجعة (أكثر من 14 يوم)",
            "action_ar": "بدء المراجعة",
            "url": "/enrollments?status=SUBMITTED",
        })
    if stalled_draft:
        actions.append({
            "type": "stalled_drafts", "count": stalled_draft, "priority": "low",
            "label_ar": "مسودات متوقفة (أكثر من 30 يوماً)",
            "action_ar": "تنظيف المسودات",
            "url": "/enrollments?status=DRAFT",
        })
    if kg_draft:
        actions.append({
            "type": "draft_kindergartens", "count": kg_draft, "priority": "medium",
            "label_ar": "روضات لا تزال في مرحلة المسودة",
            "action_ar": "مراجعة الروضات المعلقة",
            "url": "/admin/kindergartens?status=DRAFT",
        })
    if users_suspended:
        actions.append({
            "type": "suspended_users", "count": users_suspended, "priority": "low",
            "label_ar": "مستخدمون موقوفون يحتاجون مراجعة",
            "action_ar": "إدارة حسابات المستخدمين",
            "url": "/admin/users?status=SUSPENDED",
        })

    return {
        "period_start": period_start.isoformat(),
        "period_end":   period_end.isoformat(),
        "users": {
            "total":           users_total,
            "active":          users_active,
            "suspended":       users_suspended,
            "inactive":        users_inactive,
            "by_role":         users_by_role,
            "new_this_period": users_new,
        },
        "kindergartens": {
            "total":           kg_total,
            "active":          kg_active,
            "inactive":        kg_inactive,
            "draft":           kg_draft,
            "new_this_period": kg_new,
        },
        "enrollments": {
            "total":           ea_total,
            "by_status":       status_counts,
            "new_this_period": ea_new,
            "conversion_rate": conversion_rate,
            "rejection_rate":  rejection_rate,
        },
        "children": {
            "total":                children_total,
            "enrolled":             children_enrolled,
            "pending":              children_pending,
            "without_enrollment":   children_without_enrollment,
        },
        "quality": {
            "stalled_drafts":         stalled_draft,
            "overdue_pending_reviews": overdue_pending,
            "long_submitted":          long_submitted,
        },
        "actions_required": actions,
    }


@router.get("/attendance/summary")
def get_attendance_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attendance analytics (admin only)"""
    validators.validate_admin_role(current_user)
    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_attendance_analytics(db, period_start, period_end, kindergarten_id)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/daily-reports/summary")
def get_daily_reports_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get daily reports analytics (admin only)"""
    validators.validate_admin_role(current_user)
    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_daily_reports_analytics(db, period_start, period_end, kindergarten_id)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/safety/summary")
def get_safety_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get safety/incident analytics (admin only)"""
    validators.validate_admin_role(current_user)
    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_safety_analytics(db, period_start, period_end, kindergarten_id)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/staffing/summary")
def get_staffing_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get staffing analytics (admin only)"""
    validators.validate_admin_role(current_user)
    kindergarten_id = enforce_kindergarten_scope(current_user, kindergarten_id, db)

    period_start, period_end = get_date_range(start_date, end_date)

    data = get_staffing_analytics(db, period_start, period_end, kindergarten_id)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.post("/export")
def request_export(
    request_body: ExportRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request an async export job"""
    validators.validate_admin_role(current_user)

    if request_body.retry_job_id:
        orig_job = db.query(models.ExportJob).filter(
            models.ExportJob.id == request_body.retry_job_id,
            models.ExportJob.user_id == current_user.id
        ).first()
        if not orig_job:
            raise HTTPException(status_code=404, detail="Original job not found")
        job = models.ExportJob(
            user_id=current_user.id,
            export_format=orig_job.export_format,
            report_type=orig_job.report_type,
            filters=orig_job.filters,
            status=models.ExportStatus.PENDING
        )
    else:
        if not request_body.report_type:
            raise HTTPException(status_code=400, detail="report_type is required")
        try:
            export_format = models.ExportFormat(request_body.export_format.upper())
        except ValueError:
            _log_analytics_export_audit(
                db,
                action=AuditAction.ANALYTICS_EXPORT_REQUEST_FAILED,
                actor=current_user,
                report_type=request_body.report_type,
                export_format=request_body.export_format,
                filters=request_body.filters,
                status_value="failed",
                error_message=f"Unsupported export format: {request_body.export_format}",
                sensitivity_level=3,
            )
            raise HTTPException(status_code=400, detail="Unsupported export format")

        job = models.ExportJob(
            user_id=current_user.id,
            export_format=export_format,
            report_type=request_body.report_type,
            filters=request_body.filters,
            status=models.ExportStatus.PENDING
        )

    db.add(job)
    db.commit()
    db.refresh(job)

    _log_analytics_export_audit(
        db,
        action=AuditAction.ANALYTICS_EXPORT_REQUESTED,
        actor=current_user,
        report_type=job.report_type,
        export_format=job.export_format,
        filters=job.filters,
        job_id=job.id,
        status_value=job.status.value,
    )
    db.commit()  # release the write lock from the audit flush before background task runs

    background_tasks.add_task(_run_export_job_async, job.id)

    return ExportJobResponse(
        job_id=job.id,
        status=job.status.value,
        report_type=job.report_type,
        created_at=_to_jordan_iso(job.created_at)
    )


@router.get("/export/{job_id}")
def get_export_status(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check export job status"""
    job = db.query(models.ExportJob).filter(
        models.ExportJob.id == job_id,
        models.ExportJob.user_id == current_user.id
    ).first()

    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    # Mitigation: Fail orphaned pending jobs
    if job.status == models.ExportStatus.PENDING:
        from datetime import datetime, timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        # Ensure job.created_at is offset-aware before subtracting
        job_time = job.created_at
        if job_time.tzinfo is None:
            job_time = job_time.replace(tzinfo=timezone.utc)
        age = now_utc - job_time
        if age > timedelta(hours=1):
            job.status = models.ExportStatus.FAILED
            db.commit()
            db.refresh(job)

    return ExportJobResponse(
        job_id=job.id,
        status=job.status.value,
        report_type=job.report_type,
        created_at=_to_jordan_iso(job.created_at),
        file_path=job.file_path,
        error=job.error_message if job.status == models.ExportStatus.FAILED else None,
        trace_url=f"/admin/logs?job_id={job.id}" if job.status == models.ExportStatus.FAILED else None,
    )


import pandas as pd
import json

@router.get("/export/{job_id}/file")
def download_export_file(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download a completed export file"""
    job = db.query(models.ExportJob).filter(
        models.ExportJob.id == job_id,
        models.ExportJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.status != models.ExportStatus.COMPLETED or not job.file_path:
        raise HTTPException(status_code=400, detail="Export not ready")
    file_path = Path(job.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")

    _log_analytics_export_audit(
        db,
        action=AuditAction.ANALYTICS_EXPORT_DOWNLOADED,
        actor=current_user,
        report_type=job.report_type,
        export_format=job.export_format,
        filters=job.filters,
        job_id=job.id,
        status_value=job.status.value,
        file_path=str(file_path),
        file_size=job.file_size,
    )

    media_type = "text/csv"
    if job.export_format == models.ExportFormat.EXCEL:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif job.export_format == models.ExportFormat.JSON:
        media_type = "application/json"
    elif job.export_format == models.ExportFormat.PDF:
        media_type = "application/pdf"

    if job.export_format in [models.ExportFormat.EXCEL, models.ExportFormat.PDF]:
        return Response(
            content=file_path.read_bytes(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'}
        )
    else:
        return Response(
            content=file_path.read_text(encoding="utf-8"),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'}
        )

EXPORT_DIR = Path("data") / "exports"



async def _run_export_job_async(job_id: int) -> None:
    """Runs sync process_export_job in a thread pool to avoid blocking the event loop."""
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, process_export_job, job_id)


def process_export_job(job_id: int):
    """Background processor for export jobs"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        job = db.query(models.ExportJob).filter(models.ExportJob.id == job_id).first()
        if not job:
            return
        job.started_at = _utcnow_naive()
        job.status = models.ExportStatus.PROCESSING
        db.commit()

        if job.export_format not in [models.ExportFormat.CSV, models.ExportFormat.EXCEL, models.ExportFormat.JSON, models.ExportFormat.PDF]:
            job.status = models.ExportStatus.FAILED
            job.error_message = "Supported formats: CSV, EXCEL, JSON, PDF"
            db.commit()
            return

        filters = job.filters or {}
        start_str = filters.get("period_start")
        end_str = filters.get("period_end")
        if start_str and end_str:
            period_start = datetime.strptime(start_str, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_str, "%Y-%m-%d").date()
        else:
            period_end = _jordan_today()
            period_start = period_end - timedelta(days=30)

        data_list = []
        if job.report_type == "attendance":
            data = AnalyticsService.get_governorate_breakdown(db, period_start, period_end)
            for item in data:
                data_list.append({
                    "Kindergarten": item["kindergarten_name"],
                    "Children Count": item["children_count"],
                    "Capacity": item["capacity"],
                    "Attendance Rate %": round(item["attendance_rate"] * 100, 1)
                })
        elif job.report_type == "incidents":
            data = AnalyticsService.get_incidents_timeline(db, period_start, period_end)
            for date_key, count in data.items():
                data_list.append({"Date": date_key, "Incident Count": count})
        else:
            data_list.append({"Status": "Demo Data Export", "Message": "This export contains placeholder structural data."})

        import uuid
        filename = f"{job.report_type}_{job.id}_{uuid.uuid4().hex[:8]}"
        
        df = pd.DataFrame(data_list)

        if job.export_format == models.ExportFormat.CSV:
            ext = ".csv"
            out_path = EXPORT_DIR / f"{filename}{ext}"
            df.to_csv(out_path, index=False, encoding="utf-8")
        elif job.export_format == models.ExportFormat.EXCEL:
            ext = ".xlsx"
            out_path = EXPORT_DIR / f"{filename}{ext}"
            df.to_excel(out_path, index=False)
        elif job.export_format == models.ExportFormat.JSON:
            ext = ".json"
            out_path = EXPORT_DIR / f"{filename}{ext}"
            out_path.write_text(json.dumps(data_list, ensure_ascii=False, indent=2), encoding="utf-8")
        elif job.export_format == models.ExportFormat.PDF:
            ext = ".pdf"
            out_path = EXPORT_DIR / f"{filename}{ext}"
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            doc = SimpleDocTemplate(str(out_path), pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontSize=18,
                leading=22,
                textColor=colors.HexColor('#0d6efd')
            )
            elements.append(Paragraph(f"KinJo Analytics Report - {job.report_type.upper()}", title_style))
            elements.append(Spacer(1, 15))
            if data_list:
                headers = list(data_list[0].keys())
                table_data = [headers]
                for row in data_list:
                    table_data.append([str(row[h]) for h in headers])
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0d6efd')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8f9fa')),
                    ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dee2e6')),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                ]))
                elements.append(t)
            else:
                elements.append(Paragraph("No records found", styles['Normal']))
            doc.build(elements)

        job.status = models.ExportStatus.COMPLETED
        job.file_path = str(out_path)
        job.file_size = out_path.stat().st_size
        job.completed_at = _utcnow_naive()
        db.commit()

        actor = db.query(models.User).filter(models.User.id == job.user_id).first()
        _log_analytics_export_audit(
            db,
            action=AuditAction.ANALYTICS_EXPORT_JOB_COMPLETED,
            actor=actor,
            report_type=job.report_type,
            export_format=job.export_format,
            filters=job.filters,
            job_id=job.id,
            status_value=job.status.value,
            file_path=job.file_path,
            file_size=job.file_size,
        )
    except (SQLAlchemyError, OSError, ValueError, TypeError, AttributeError, RuntimeError, ImportError, csv.Error) as exc:
        try:
            db.rollback()
        except Exception:
            pass
        job = db.query(models.ExportJob).filter(models.ExportJob.id == job_id).first()
        if job:
            job.status = models.ExportStatus.FAILED
            job.error_message = str(exc)
            db.commit()

            actor = db.query(models.User).filter(models.User.id == job.user_id).first()
            _log_analytics_export_audit(
                db,
                action=AuditAction.ANALYTICS_EXPORT_JOB_FAILED,
                actor=actor,
                report_type=job.report_type,
                export_format=job.export_format,
                filters=job.filters,
                job_id=job.id,
                status_value=job.status.value,
                error_message=job.error_message,
                sensitivity_level=3,
            )
    finally:
        db.close()

class ReportTypeDefinition(BaseModel):
    id: str
    name_ar: str
    name_en: str
    description_ar: str
    description_en: str
    required_filters: List[str] = []
    optional_filters: List[str] = []
    kpis: List[Dict[str, Any]] = []
    charts: List[Dict[str, Any]] = []
    columns: List[Dict[str, Any]] = []


class ReportPreviewResponse(BaseModel):
    report_type: str
    period_start: date
    period_end: date
    filters_applied: Dict[str, Any]
    total_records: int
    kpis: List[Dict[str, Any]] = []
    charts: List[Dict[str, Any]] = []
    sample_data: List[Dict[str, Any]] = []
    data_quality: Dict[str, Any]
    warnings: List[Any] = []
    insights: List[Any] = []


class ReportHistoryItem(BaseModel):
    id: int
    report_type: str
    report_name: str
    generated_by: str
    generated_at: Optional[str] = None  # ISO-8601 with Jordan +03:00 offset
    period_start: date
    period_end: date
    format: str
    status: str
    file_size: Optional[int] = None
    filters: Dict[str, Any] = {}


class ReportTemplateCreate(BaseModel):
    name: str
    report_type: str
    filters: Dict[str, Any] = {}
    export_format: str = "CSV"
    include_charts: bool = True
    include_summary: bool = True


class ReportTemplateResponse(BaseModel):
    id: int
    name: str
    report_type: str
    filters: Dict[str, Any] = {}
    export_format: str
    include_charts: bool
    include_summary: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime


class ScheduledReportCreate(BaseModel):
    name: str
    report_type: str
    filters: Dict[str, Any] = {}
    export_format: str = "CSV"
    frequency: str  # daily, weekly, monthly, quarterly, once
    recipients: List[str] = []
    next_run: Optional[datetime] = None


class ScheduledReportResponse(BaseModel):
    id: int
    name: str
    report_type: str
    filters: Dict[str, Any] = {}
    export_format: str
    frequency: str
    recipients: List[str] = []
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    is_active: bool
    created_at: datetime


# =============================================================================
# KG Overview Response Models
# =============================================================================

class KgOverviewKPI(BaseModel):
    key: str
    label_ar: str
    label_en: str
    value: Any
    unit: str
    delta_percent: Optional[float] = None
    delta_dir: str = "flat"
    target: Optional[float] = None
    risk_label_ar: Optional[str] = None
    risk_label_en: Optional[str] = None
    risk_count: Optional[int] = None


class KgOverviewAlert(BaseModel):
    id: int
    severity: str
    metric_type: str
    scope_type: str
    scope_id: Optional[str] = None
    kindergarten_name: Optional[str] = None
    governorate: Optional[str] = None
    message: str
    current_value: Optional[float] = None
    triggered_at: datetime
    age_hours: float
    status: str
    recommended_action_ar: Optional[str] = None
    recommended_action_en: Optional[str] = None


class KgOverviewKindergarten(BaseModel):
    id: int
    name: str
    name_ar: str
    governorate: str
    children_count: int
    capacity: int
    occupancy_percent: float
    attendance_percent: float
    teachers_count: int
    open_alerts: int
    health_score: str  # excellent, good, needs_attention, at_risk, critical
    health_label_ar: str
    health_label_en: str
    recommended_action_ar: Optional[str] = None
    recommended_action_en: Optional[str] = None
    last_report_at: Optional[datetime] = None
    teacher_data_status: str  # updated, stale, missing


class KgOverviewGovernorate(BaseModel):
    name: str
    kindergarten_count: int
    children_count: int
    avg_attendance: float
    avg_occupancy: float
    alert_count: int
    risk_level: str


class KgOverviewSummary(BaseModel):
    period_start: date
    period_end: date
    kpis: List[KgOverviewKPI]
    total_alerts: int
    high_alerts: int
    medium_alerts: int
    low_alerts: int
    critical_kindergartens: int
    kindergartens_below_attendance_target: int
    kindergartens_near_capacity: int


# =============================================================================
# KG Overview API Endpoints
# =============================================================================

@router.get("/kg-overview/summary", response_model=KgOverviewSummary)
def get_kg_overview_summary(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get KPI summary for KG Overview dashboard."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)

    # Count alerts by severity
    alert_query = db.query(models.ActiveAlert).filter(models.ActiveAlert.status == models.AlertStatus.ACTIVE)
    if kg_filter:
        alert_query = alert_query.filter(
            or_(
                models.ActiveAlert.scope_type == "NETWORK",
                models.ActiveAlert.scope_id.in_([str(kg) for kg in kg_filter]),
            )
        )
    alerts = alert_query.all()
    high = sum(1 for a in alerts if a.severity == models.SeverityLevel.HIGH)
    medium = sum(1 for a in alerts if a.severity == models.SeverityLevel.MEDIUM)
    low = sum(1 for a in alerts if a.severity == models.SeverityLevel.LOW)

    # Count kindergartens below attendance target (70%)
    below_target = 0
    near_capacity = 0
    critical_kgs = 0
    try:
        breakdown = AnalyticsService.get_governorate_breakdown(db, period_start, period_end, governorate, kg_filter, None)
        for b in breakdown:
            if b.attendance_rate < 70:
                below_target += 1
            if b.enrollment_rate >= 90:
                near_capacity += 1
            if b.attendance_rate < 60 or b.incident_rate > 5:
                critical_kgs += 1
    except Exception:
        pass

    # Previous period — compute real deltas instead of hardcoded values
    def _pct_delta(current: float, previous: Optional[float]) -> Optional[float]:
        if previous is None or previous == 0:
            return None
        return round((current - previous) / abs(previous) * 100, 1)

    prev_summary = None
    prev_alert_count: Optional[int] = None
    _prev = _previous_period_bounds(period_start, period_end)
    if _prev:
        try:
            prev_summary = AnalyticsService.get_network_summary(db, _prev[0], _prev[1], kg_filter)
        except Exception:
            prev_summary = None
        try:
            _paq = db.query(func.count(models.ActiveAlert.id)).filter(
                models.ActiveAlert.triggered_at.isnot(None),
                func.date(models.ActiveAlert.triggered_at) >= _prev[0],
                func.date(models.ActiveAlert.triggered_at) <= _prev[1],
            )
            if kg_filter:
                _paq = _paq.filter(
                    or_(
                        models.ActiveAlert.scope_type == "NETWORK",
                        models.ActiveAlert.scope_id.in_([str(k) for k in kg_filter]),
                    )
                )
            prev_alert_count = int(_paq.scalar() or 0)
        except Exception:
            prev_alert_count = None

    children_delta = _pct_delta(
        float(summary.total_children),
        float(prev_summary.total_children) if prev_summary else None,
    )
    attendance_delta = _pct_delta(
        float(summary.attendance_rate),
        float(prev_summary.attendance_rate) if prev_summary else None,
    )
    staff_delta = _pct_delta(
        float(summary.total_staff),
        float(prev_summary.total_staff) if prev_summary else None,
    )
    alerts_delta = _pct_delta(float(len(alerts)), float(prev_alert_count) if prev_alert_count is not None else None)

    kpis = [
        KgOverviewKPI(
            key="children",
            label_ar="إجمالي الأطفال",
            label_en="Total Children",
            value=summary.total_children,
            unit="",
            delta_percent=children_delta,
            delta_dir="up" if (children_delta or 0) >= 0 else "down",
            target=None,
            risk_label_ar=None,
            risk_label_en=None,
            risk_count=None,
        ),
        KgOverviewKPI(
            key="attendance",
            label_ar="نسبة الحضور",
            label_en="Attendance Rate",
            value=round(summary.attendance_rate, 1),
            unit="%",
            delta_percent=attendance_delta,
            delta_dir="up" if (attendance_delta or 0) >= 0 else "down",
            target=70.0,
            risk_label_ar=f"{below_target} روضات أقل من الحد الأدنى",
            risk_label_en=f"{below_target} kindergartens below target",
            risk_count=below_target,
        ),
        KgOverviewKPI(
            key="teachers",
            label_ar="المعلمات",
            label_en="Teachers",
            value=summary.total_staff,
            unit="",
            delta_percent=staff_delta,
            delta_dir="up" if (staff_delta or 0) >= 0 else "down",
            target=None,
            risk_label_ar=None,
            risk_label_en=None,
            risk_count=None,
        ),
        KgOverviewKPI(
            key="alerts",
            label_ar="التنبيهات",
            label_en="Alerts",
            value=summary.risk_radar.__len__() if hasattr(summary, 'risk_radar') else len(alerts),
            unit="",
            delta_percent=alerts_delta,
            delta_dir="up" if (alerts_delta or 0) >= 0 else "down",
            target=0,
            risk_label_ar=f"{high} حرجة، {medium} متوسطة",
            risk_label_en=f"{high} high, {medium} medium",
            risk_count=len(alerts),
        ),
    ]

    return KgOverviewSummary(
        period_start=period_start,
        period_end=period_end,
        kpis=kpis,
        total_alerts=len(alerts),
        high_alerts=high,
        medium_alerts=medium,
        low_alerts=low,
        critical_kindergartens=critical_kgs,
        kindergartens_below_attendance_target=below_target,
        kindergartens_near_capacity=near_capacity,
    )


@router.get("/kg-overview/kindergartens", response_model=List[KgOverviewKindergarten])
def get_kg_overview_kindergartens(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get kindergarten list with health scores for KG Overview."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    query = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
    if kg_filter:
        query = query.filter(models.Kindergarten.id.in_(kg_filter))

    kindergartens = query.all()

    # Batch-load last report date per kindergarten (avoids N+1)
    _kg_ids = [kg.id for kg in kindergartens]
    _last_report_by_kg: dict[int, object] = {}
    if _kg_ids:
        _last_report_rows = (
            db.query(models.DailyReport.kindergarten_id, func.max(models.DailyReport.submitted_at))
            .filter(models.DailyReport.kindergarten_id.in_(_kg_ids))
            .group_by(models.DailyReport.kindergarten_id)
            .all()
        )
        _last_report_by_kg = {kg_id: ts for kg_id, ts in _last_report_rows}

    result = []
    for kg in kindergartens:
        try:
            metrics = AnalyticsService.get_kindergarten_metrics(db, kg.id, period_start, period_end)
            attendance = metrics.attendance_rate or 0
            capacity = metrics.capacity or 0
            children = metrics.children_count or 0
            occupancy = (children / capacity * 100) if capacity > 0 else 0
            teachers = metrics.staff_count if hasattr(metrics, 'staff_count') else 0

            # Health score logic
            if attendance >= 80 and occupancy < 90:
                health = "excellent"
                health_ar = "ممتاز"
                health_en = "Excellent"
                action_ar = None
                action_en = None
            elif attendance >= 70 and occupancy < 95:
                health = "good"
                health_ar = "جيد"
                health_en = "Good"
                action_ar = None
                action_en = None
            elif attendance >= 60 or occupancy >= 95:
                health = "needs_attention"
                health_ar = "يحتاج متابعة"
                health_en = "Needs Attention"
                action_ar = "مراجعة البيانات والتأكد من صحة الحضور"
                action_en = "Review data and verify attendance accuracy"
            elif attendance >= 50 or occupancy >= 100:
                health = "at_risk"
                health_ar = "معرّض للخطر"
                health_en = "At Risk"
                action_ar = "يتطلب تدخل إداري عاجل"
                action_en = "Requires urgent administrative intervention"
            else:
                health = "critical"
                health_ar = "حرج"
                health_en = "Critical"
                action_ar = "إجراء فوريRequired"
                action_en = "Immediate action required"

            # Open alerts count
            open_alerts = db.query(func.count(models.ActiveAlert.id)).filter(
                models.ActiveAlert.scope_type == "KINDERGARTEN",
                models.ActiveAlert.scope_id == str(kg.id),
                models.ActiveAlert.status == models.AlertStatus.ACTIVE,
            ).scalar() or 0

            # Teacher data status
            teacher_data_status = "updated"
            try:
                last_teacher_update = db.query(func.max(models.User.updated_at)).filter(
                    models.User.kindergarten_id == kg.id,
                    models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
                ).scalar()
                if last_teacher_update and (datetime.now(timezone.utc) - last_teacher_update).days > 30:
                    teacher_data_status = "stale"
            except Exception:
                teacher_data_status = "missing"

            result.append(KgOverviewKindergarten(
                id=kg.id,
                name=kg.name_ar or kg.name_en,
                name_ar=kg.name_ar or "",
                governorate=kg.governorate or "",
                children_count=children,
                capacity=capacity,
                occupancy_percent=round(occupancy, 1),
                attendance_percent=round(attendance, 1),
                teachers_count=teachers,
                open_alerts=open_alerts,
                health_score=health,
                health_label_ar=health_ar,
                health_label_en=health_en,
                recommended_action_ar=action_ar,
                recommended_action_en=action_en,
                last_report_at=_last_report_by_kg.get(kg.id),
                teacher_data_status=teacher_data_status,
            ))
        except Exception:
            continue

    return result


@router.get("/kg-overview/alerts", response_model=List[KgOverviewAlert])
def get_kg_overview_alerts(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    severity: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get smart alerts for KG Overview with enriched context."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    query = db.query(models.ActiveAlert).filter(models.ActiveAlert.status == models.AlertStatus.ACTIVE)
    if severity:
        try:
            query = query.filter(models.ActiveAlert.severity == models.SeverityLevel(severity.upper()))
        except ValueError:
            pass
    if allowed_kgs is not None:
        query = query.filter(
            or_(
                models.ActiveAlert.scope_type == "NETWORK",
                models.ActiveAlert.scope_id.in_([str(kg) for kg in allowed_kgs]),
            )
        )

    alerts = query.order_by(models.ActiveAlert.triggered_at.desc()).limit(100).all()

    # Batch-fetch kindergartens referenced by scoped alerts
    _scoped_kg_ids = []
    for _a in alerts:
        if _a.scope_type == "KINDERGARTEN" and _a.scope_id:
            try:
                _scoped_kg_ids.append(int(_a.scope_id))
            except Exception:
                pass
    _alert_kg_map = {k.id: k for k in db.query(models.Kindergarten).filter(
        models.Kindergarten.id.in_(_scoped_kg_ids)
    ).all()} if _scoped_kg_ids else {}

    result = []
    for alert in alerts:
        kg_name = None
        gov = None
        if alert.scope_type == "KINDERGARTEN" and alert.scope_id:
            try:
                kg = _alert_kg_map.get(int(alert.scope_id))
                if kg:
                    kg_name = kg.name_ar or kg.name_en
                    gov = kg.governorate
            except Exception:
                pass

        age_hours = round((datetime.now(timezone.utc) - alert.triggered_at).total_seconds() / 3600, 1)

        # Recommended actions based on metric type
        rec_ar = "مراجعة الحالة وتحديد الإجراء المناسب"
        rec_en = "Review status and determine appropriate action"
        if alert.metric_type == "attendance_rate":
            rec_ar = "مراجعة سياسات الحضور والغياب للروضة"
            rec_en = "Review attendance policies for this kindergarten"
        elif alert.metric_type == "incident_rate":
            rec_ar = "التحقيق في الحوادث وتطبيق إجراءات السلامة"
            rec_en = "Investigate incidents and apply safety measures"
        elif alert.metric_type == "enrollment_rate":
            rec_ar = "مراجعة حالة الطاقة الاستيعابية وطلبات التسجيل"
            rec_en = "Review capacity status and enrollment requests"

        result.append(KgOverviewAlert(
            id=alert.id,
            severity=alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
            metric_type=alert.metric_type,
            scope_type=alert.scope_type,
            scope_id=alert.scope_id,
            kindergarten_name=kg_name,
            governorate=gov,
            message=alert.message,
            current_value=alert.current_value,
            triggered_at=alert.triggered_at,
            age_hours=age_hours,
            status=alert.status.value if hasattr(alert.status, "value") else str(alert.status),
            recommended_action_ar=rec_ar,
            recommended_action_en=rec_en,
        ))
    return result


@router.get("/kg-overview/trends")
def get_kg_overview_trends(
    metric: str = Query("attendance", pattern="^(attendance|enrollment|incidents)$"),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get trend data for KG Overview charts."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    trend = AnalyticsService.get_network_trends(db, metric, period_start, period_end, kg_filter)
    return {
        "metric": metric,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "data": [{"date": p.date, "value": p.value} for p in trend],
    }


@router.get("/kg-overview/governorates", response_model=List[KgOverviewGovernorate])
def get_kg_overview_governorates(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get governorate comparison for KG Overview."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(period_start, period_end)

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    breakdown = AnalyticsService.get_governorate_breakdown(db, period_start, period_end, None, allowed_kgs, None)

    # Batch-count active alerts per governorate via two lean queries
    gov_alert_counts: dict[str, int] = {}
    try:
        from collections import Counter
        _alert_scope_ids = [
            r.scope_id for r in
            db.query(models.ActiveAlert.scope_id)
            .filter(
                models.ActiveAlert.scope_type == "KINDERGARTEN",
                models.ActiveAlert.status == models.AlertStatus.ACTIVE,
            )
            .all()
            if str(r.scope_id).isdigit()
        ]
        if _alert_scope_ids:
            _alert_by_kg = Counter(int(s) for s in _alert_scope_ids)
            _kg_gov_rows = (
                db.query(models.Kindergarten.id, models.Kindergarten.governorate)
                .filter(models.Kindergarten.id.in_(list(_alert_by_kg.keys())))
                .all()
            )
            for _kg_id, _gov in _kg_gov_rows:
                gov_alert_counts[_gov] = gov_alert_counts.get(_gov, 0) + _alert_by_kg[_kg_id]
    except Exception:
        gov_alert_counts = {}

    result = []
    for b in breakdown:
        risk = "low"
        if b.attendance_rate < 60 or b.incident_rate > 5:
            risk = "high"
        elif b.attendance_rate < 70 or b.incident_rate > 3:
            risk = "medium"

        result.append(KgOverviewGovernorate(
            name=b.governorate,
            kindergarten_count=b.kindergarten_count,
            children_count=b.children_count,
            avg_attendance=round(b.attendance_rate, 1),
            avg_occupancy=round(b.enrollment_rate, 1),
            alert_count=gov_alert_counts.get(b.governorate, 0),
            risk_level=risk,
        ))
    return result


_REPORT_TYPES = [
    ReportTypeDefinition(
        id="attendance",
        name_ar="تقرير الحضور والغياب",
        name_en="Attendance & Absence Report",
        description_ar="ملخص الحضور والغياب لجميع الروضات",
        description_en="Attendance and absence summary for all kindergartens",
        required_filters=["period_start", "period_end"],
        optional_filters=["governorate", "kindergarten_id", "child_id"],
        kpis=[
            {"id": "total_present", "label_ar": "إجمالي الحضور", "label_en": "Total Present", "type": "number"},
            {"id": "total_absent", "label_ar": "إجمالي الغياب", "label_en": "Total Absent", "type": "number"},
            {"id": "attendance_rate", "label_ar": "معدل الحضور", "label_en": "Attendance Rate", "type": "percent"},
            {"id": "absence_rate", "label_ar": "معدل الغياب", "label_en": "Absence Rate", "type": "percent"},
            {"id": "late_arrivals", "label_ar": "حالات التأخير", "label_en": "Late Arrivals", "type": "number"},
        ],
        charts=[
            {"id": "attendance_trend", "type": "line", "label_ar": "اتجاه الحضور", "label_en": "Attendance Trend"},
            {"id": "absence_by_kg", "type": "bar", "label_ar": "الغياب حسب الروضة", "label_en": "Absence by Kindergarten"},
        ],
        columns=[
            {"key": "date", "label_ar": "التاريخ", "label_en": "Date"},
            {"key": "kindergarten", "label_ar": "الروضة", "label_en": "Kindergarten"},
            {"key": "child_name", "label_ar": "الطفل", "label_en": "Child"},
            {"key": "status", "label_ar": "الحالة", "label_en": "Status"},
            {"key": "check_in", "label_ar": "وقت الدخول", "label_en": "Check In"},
            {"key": "check_out", "label_ar": "وقت الخروج", "label_en": "Check Out"},
        ],
    ),
    ReportTypeDefinition(
        id="incidents",
        name_ar="تقرير الحوادث",
        name_en="Incidents Report",
        description_ar="تحليل الحوادث ومعدلاتها",
        description_en="Incident analysis and rates",
        required_filters=["period_start", "period_end"],
        optional_filters=["governorate", "kindergarten_id", "incident_type", "severity", "status"],
        kpis=[
            {"id": "total_incidents", "label_ar": "إجمالي الحوادث", "label_en": "Total Incidents", "type": "number"},
            {"id": "incident_rate", "label_ar": "معدل الحوادث", "label_en": "Incident Rate", "type": "rate"},
            {"id": "open_incidents", "label_ar": "الحوادث المفتوحة", "label_en": "Open Incidents", "type": "number"},
            {"id": "critical_incidents", "label_ar": "حوادث حرجة", "label_en": "Critical Incidents", "type": "number"},
            {"id": "avg_resolution_hours", "label_ar": "متوسط وقت المعالجة", "label_en": "Avg Resolution Time", "type": "duration"},
        ],
        charts=[
            {"id": "incidents_over_time", "type": "line", "label_ar": "الحوادث عبر الزمن", "label_en": "Incidents Over Time"},
            {"id": "incidents_by_severity", "type": "doughnut", "label_ar": "حسب الخطورة", "label_en": "By Severity"},
            {"id": "incidents_by_type", "type": "bar", "label_ar": "حسب النوع", "label_en": "By Type"},
        ],
        columns=[
            {"key": "date", "label_ar": "التاريخ", "label_en": "Date"},
            {"key": "kindergarten", "label_ar": "الروضة", "label_en": "Kindergarten"},
            {"key": "type", "label_ar": "النوع", "label_en": "Type"},
            {"key": "severity", "label_ar": "الخطورة", "label_en": "Severity"},
            {"key": "status", "label_ar": "الحالة", "label_en": "Status"},
            {"key": "description", "label_ar": "الوصف", "label_en": "Description"},
        ],
    ),
    ReportTypeDefinition(
        id="compliance",
        name_ar="تقرير الامتثال والحوكمة",
        name_en="Compliance & Governance Report",
        description_ar="مؤشرات الأداء والتقييم",
        description_en="Performance and evaluation indicators",
        required_filters=["period_start", "period_end"],
        optional_filters=["governorate", "kindergarten_id"],
        kpis=[
            {"id": "compliance_score", "label_ar": "درجة الامتثال", "label_en": "Compliance Score", "type": "score"},
            {"id": "governance_score", "label_ar": "درجة الحوكمة", "label_en": "Governance Score", "type": "score"},
            {"id": "inspection_completion", "label_ar": "معدل إكمال التفتيش", "label_en": "Inspection Completion", "type": "percent"},
            {"id": "non_compliant_count", "label_ar": "الجهات غير الممتثلة", "label_en": "Non-Compliant Entities", "type": "number"},
        ],
        charts=[
            {"id": "governance_distribution", "type": "pie", "label_ar": "توزيع الحوكمة", "label_en": "Governance Distribution"},
            {"id": "compliance_by_governorate", "type": "bar", "label_ar": "الامتثال حسب المحافظة", "label_en": "Compliance by Governorate"},
        ],
        columns=[
            {"key": "kindergarten", "label_ar": "الروضة", "label_en": "Kindergarten"},
            {"key": "governorate", "label_ar": "المحافظة", "label_en": "Governorate"},
            {"key": "compliance_score", "label_ar": "درجة الامتثال", "label_en": "Compliance Score"},
            {"key": "governance_score", "label_ar": "درجة الحوكمة", "label_en": "Governance Score"},
            {"key": "risk_level", "label_ar": "مستوى المخاطر", "label_en": "Risk Level"},
        ],
    ),
    ReportTypeDefinition(
        id="enrollment",
        name_ar="تقرير التسجيل",
        name_en="Enrollment Report",
        description_ar="طلبات التسجيل والقبول",
        description_en="Enrollment applications and approvals",
        required_filters=["period_start", "period_end"],
        optional_filters=["governorate", "kindergarten_id", "status", "source"],
        kpis=[
            {"id": "total_applications", "label_ar": "إجمالي الطلبات", "label_en": "Total Applications", "type": "number"},
            {"id": "approved", "label_ar": "موافق عليه", "label_en": "Approved", "type": "number"},
            {"id": "rejected", "label_ar": "مرفوض", "label_en": "Rejected", "type": "number"},
            {"id": "conversion_rate", "label_ar": "معدل التحويل", "label_en": "Conversion Rate", "type": "percent"},
        ],
        charts=[
            {"id": "enrollment_funnel", "type": "bar", "label_ar": "قمع التسجيل", "label_en": "Enrollment Funnel"},
            {"id": "source_breakdown", "type": "doughnut", "label_ar": "توزيع المصادر", "label_en": "Source Breakdown"},
        ],
        columns=[
            {"key": "child_name", "label_ar": "الطفل", "label_en": "Child"},
            {"key": "parent_name", "label_ar": "الوصي", "label_en": "Parent"},
            {"key": "kindergarten", "label_ar": "الروضة", "label_en": "Kindergarten"},
            {"key": "status", "label_ar": "الحالة", "label_en": "Status"},
            {"key": "source", "label_ar": "المصدر", "label_en": "Source"},
            {"key": "submitted_at", "label_ar": "تاريخ التقديم", "label_en": "Submitted At"},
        ],
    ),
    ReportTypeDefinition(
        id="full_audit",
        name_ar="سجل التدقيق الشامل",
        name_en="Comprehensive Audit Log",
        description_ar="كافة العمليات والنشاطات",
        description_en="All operations and activities",
        required_filters=["period_start", "period_end"],
        optional_filters=["user_id", "action", "module", "sensitivity_level"],
        kpis=[
            {"id": "total_actions", "label_ar": "إجمالي الإجراءات", "label_en": "Total Actions", "type": "number"},
            {"id": "failed_actions", "label_ar": "إجراءات فاشلة", "label_en": "Failed Actions", "type": "number"},
            {"id": "high_risk_actions", "label_ar": "إجراءات عالية الخطورة", "label_en": "High Risk Actions", "type": "number"},
        ],
        charts=[
            {"id": "actions_by_module", "type": "bar", "label_ar": "حسب الوحدة", "label_en": "By Module"},
            {"id": "actions_by_hour", "type": "line", "label_ar": "حسب الساعة", "label_en": "By Hour"},
        ],
        columns=[
            {"key": "timestamp", "label_ar": "التوقيت", "label_en": "Timestamp"},
            {"key": "user", "label_ar": "المستخدم", "label_en": "User"},
            {"key": "role", "label_ar": "الدور", "label_en": "Role"},
            {"key": "action", "label_ar": "الإجراء", "label_en": "Action"},
            {"key": "module", "label_ar": "الوحدة", "label_en": "Module"},
            {"key": "result", "label_ar": "النتيجة", "label_en": "Result"},
            {"key": "risk_level", "label_ar": "مستوى الخطورة", "label_en": "Risk Level"},
        ],
    ),
]


@router.get("/reports/types", response_model=List[ReportTypeDefinition])
def get_report_types(lang: str = Query("ar", pattern="^(ar|en)$")):
    """Return catalog of available report types with their filter and output definitions."""
    result = []
    for rt in _REPORT_TYPES:
        item = rt.model_dump()
        if lang == "en":
            item["name"] = rt.name_en
            item["description"] = rt.description_en
            for kpi in item.get("kpis", []):
                kpi["label"] = kpi.get("label_en", kpi.get("label_ar"))
            for chart in item.get("charts", []):
                chart["label"] = chart.get("label_en", chart.get("label_ar"))
            for col in item.get("columns", []):
                col["label"] = col.get("label_en", col.get("label_ar"))
        else:
            item["name"] = rt.name_ar
            item["description"] = rt.description_ar
            for kpi in item.get("kpis", []):
                kpi["label"] = kpi.get("label_ar", kpi.get("label_en"))
            for chart in item.get("charts", []):
                chart["label"] = chart.get("label_ar", chart.get("label_en"))
            for col in item.get("columns", []):
                col["label"] = col.get("label_ar", col.get("label_en"))
        result.append(item)
    return result


@router.post("/reports/preview", response_model=ReportPreviewResponse)
def preview_report(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a preview payload for the requested report configuration."""
    validators.validate_admin_role(current_user)
    report_type = payload.get("report_type")
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    filters = payload.get("filters", {}) or {}

    if not report_type or not period_start or not period_end:
        raise HTTPException(status_code=400, detail="report_type, period_start, and period_end are required")

    from datetime import datetime, timezone
    import zoneinfo
    
    if isinstance(period_start, str):
        try:
            period_start = datetime.strptime(period_start, "%Y-%m-%d").date()
        except ValueError:
            period_start = datetime.strptime(period_start[:10], "%Y-%m-%d").date()
            
    if isinstance(period_end, str):
        try:
            period_end = datetime.strptime(period_end, "%Y-%m-%d").date()
        except ValueError:
            period_end = datetime.strptime(period_end[:10], "%Y-%m-%d").date()

    from utils.time_utils import get_amman_tz
    amman_tz = get_amman_tz()

    utc_start = datetime.combine(period_start, datetime.min.time()).replace(tzinfo=amman_tz).astimezone(timezone.utc)
    utc_end = datetime.combine(period_end, datetime.max.time()).replace(tzinfo=amman_tz).astimezone(timezone.utc)

    # Resolve scope
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    kg_filter = None
    if allowed_kgs is not None:
        kg_filter = allowed_kgs
    gov_filters = filters.get("governorates", [])
    if gov_filters:
        gov_kgs = []
        for g in gov_filters:
            gov_kgs.extend(_kg_ids_for_governorate(db, g) or [])
        if kg_filter is not None:
            kg_filter = [kg for kg in kg_filter if kg in gov_kgs] or None
        else:
            kg_filter = gov_kgs or None

    user_kg_filters = filters.get("kindergarten_ids", [])
    if user_kg_filters:
        if kg_filter is not None:
            kg_filter = [kg for kg in kg_filter if kg in user_kg_filters] or None
        else:
            kg_filter = user_kg_filters or None

    warnings = []
    insights = []
    kpis = []
    charts = []
    sample_data = []
    total_records = 0
    data_quality = {
        "total_records": 0,
        "missing_fields": 0,
        "duplicate_records": 0,
        "incomplete_records": 0,
        "completeness_percent": 100.0,
        "last_refresh": _jordan_now().isoformat(),
    }

    if report_type == "attendance":
        kpis = [
            {"id": "total_present", "label_ar": "إجمالي الحضور", "label_en": "Total Present", "value": 0, "unit": ""},
            {"id": "total_absent", "label_ar": "إجمالي الغياب", "label_en": "Total Absent", "value": 0, "unit": ""},
            {"id": "attendance_rate", "label_ar": "معدل الحضور", "label_en": "Attendance Rate", "value": 0, "unit": "%"},
            {"id": "absence_rate", "label_ar": "معدل الغياب", "label_en": "Absence Rate", "value": 0, "unit": "%"},
        ]
        charts = [
            {"id": "attendance_trend", "type": "line", "label_ar": "اتجاه الحضور", "label_en": "Attendance Trend"},
            {"id": "absence_by_governorate", "type": "bar", "label_ar": "الغياب حسب المحافظة", "label_en": "Absence by Governorate"},
        ]
        # Use existing analytics functions for preview data
        try:
            summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)
            
            # Query true attendance counts
            base_query = db.query(models.AttendanceLog.id).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            )
            if kg_filter:
                base_query = base_query.join(models.Child).join(models.EnrollmentApplication).filter(
                    models.EnrollmentApplication.kindergarten_id.in_(kg_filter),
                    models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
                )
                
            total_present = base_query.filter(models.AttendanceLog.status == models.AttendanceStatus.PRESENT).count()
            total_absent = base_query.filter(models.AttendanceLog.status == models.AttendanceStatus.ABSENT).count()
            
            kpis[0]["value"] = total_present
            kpis[1]["value"] = total_absent
            kpis[2]["value"] = summary.attendance_rate
            kpis[3]["value"] = round(100 - summary.attendance_rate, 2)
            total_records = total_present + total_absent
            
            from sqlalchemy import func
            trend_q = db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT
            )
            if kg_filter:
                trend_q = trend_q.join(models.Class).filter(models.Class.kindergarten_id.in_(kg_filter))
            trend_data = trend_q.group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()
            charts[0]["data"] = {
                "labels": [str(row[0]) for row in trend_data],
                "datasets": [{"label": {"ar": "حاضر", "en": "Present"}, "data": [row[1] for row in trend_data], "borderColor": "#0d6efd", "backgroundColor": "rgba(13, 110, 253, 0.1)", "fill": True}]
            }
            
            gov_q = db.query(models.Kindergarten.governorate, func.count(models.AttendanceLog.id)).join(
                models.Class, models.AttendanceLog.class_id == models.Class.id
            ).join(models.Kindergarten, models.Class.kindergarten_id == models.Kindergarten.id).filter(
                models.AttendanceLog.date >= period_start, models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status == models.AttendanceStatus.ABSENT
            )
            if kg_filter: gov_q = gov_q.filter(models.Kindergarten.id.in_(kg_filter))
            gov_data = gov_q.group_by(models.Kindergarten.governorate).all()
            from config import settings
            def get_gov_bilingual(val):
                if not val: return {"ar": "غير معروف", "en": "Unknown"}
                ar_val = settings.JORDAN_GOVERNORATE_ALIASES.get(val.lower(), val)
                idx = settings.JORDAN_GOVERNORATES.index(ar_val) if ar_val in settings.JORDAN_GOVERNORATES else -1
                en_val = settings.JORDAN_GOVERNORATES_ENGLISH[idx] if idx >= 0 else ar_val
                return {"ar": ar_val, "en": en_val}

            charts[1]["data"] = {
                "labels": [get_gov_bilingual(row[0]) for row in gov_data],
                "datasets": [{"label": {"ar": "الغياب", "en": "Absences"}, "data": [row[1] for row in gov_data], "backgroundColor": "#dc3545"}]
            }
        except Exception as e:
            logger.error(f"Failed to load attendance data: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الحضور", "en": "Failed to load attendance data"})
            insights.append({"ar": "لا توجد بيانات كافية للحضور في الفترة المحددة", "en": "Insufficient attendance data for the selected period"})

    elif report_type == "incidents":
        kpis = [
            {"id": "total_incidents", "label_ar": "إجمالي الحوادث", "label_en": "Total Incidents", "value": 0, "unit": ""},
            {"id": "open_incidents", "label_ar": "الحوادث المفتوحة", "label_en": "Open Incidents", "value": 0, "unit": ""},
            {"id": "critical_incidents", "label_ar": "حوادث حرجة", "label_en": "Critical Incidents", "value": 0, "unit": ""},
        ]
        charts = [
            {"id": "incidents_over_time", "type": "line", "label_ar": "الحوادث عبر الزمن", "label_en": "Incidents Over Time"},
            {"id": "incidents_by_severity", "type": "doughnut", "label_ar": "حسب الخطورة", "label_en": "By Severity"},
        ]
        try:
            from sqlalchemy import func
            inc_base = db.query(models.Incident).filter(
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) >= period_start,
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) <= period_end
            )
            if kg_filter: inc_base = inc_base.filter(models.Incident.kindergarten_id.in_(kg_filter))
            
            statuses = filters.get("statuses", [])
            if statuses:
                inc_base = inc_base.filter(models.Incident.status.in_(statuses))
                
            severities = filters.get("severities", [])
            if severities:
                inc_base = inc_base.filter(models.Incident.severity_level.in_(severities))

            kpis[0]["value"] = inc_base.count()
            kpis[1]["value"] = inc_base.filter(models.Incident.status == models.IncidentStatus.OPEN).count()
            kpis[2]["value"] = inc_base.filter(models.Incident.severity_level == models.SeverityLevel.CRITICAL).count()
            total_records = kpis[0]["value"]

            trend_data = db.query(func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)).label("d"), func.count(models.Incident.id)).filter(
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) >= period_start,
                func.date(func.timezone('Asia/Amman', models.Incident.occurred_at)) <= period_end
            )
            if kg_filter: trend_data = trend_data.filter(models.Incident.kindergarten_id.in_(kg_filter))
            trend_data = trend_data.group_by("d").order_by("d").all()
            charts[0]["data"] = {
                "labels": [str(row[0]) for row in trend_data],
                "datasets": [{"label": {"ar": "الحوادث", "en": "Incidents"}, "data": [row[1] for row in trend_data], "borderColor": "#dc3545", "backgroundColor": "rgba(220, 53, 69, 0.1)", "fill": True}]
            }

            sev_data = inc_base.with_entities(models.Incident.severity_level, func.count(models.Incident.id)).group_by(models.Incident.severity_level).all()
            charts[1]["data"] = {
                "labels": [{"ar": row[0].value if hasattr(row[0], 'value') else str(row[0]), "en": row[0].value if hasattr(row[0], 'value') else str(row[0])} for row in sev_data],
                "datasets": [{"label": {"ar": "الخطورة", "en": "Severity"}, "data": [row[1] for row in sev_data], "backgroundColor": ["#0d6efd", "#ffc107", "#fd7e14", "#dc3545"]}]
            }
        except Exception:
            warnings.append({"ar": "تعذر تحميل بيانات الحوادث", "en": "Failed to load incident data"})

    elif report_type == "compliance":
        kpis = [
            {"id": "compliance_score", "label_ar": "درجة الامتثال", "label_en": "Compliance Score", "value": 0, "unit": "%"},
            {"id": "governance_score", "label_ar": "درجة الحوكمة", "label_en": "Governance Score", "value": 0, "unit": "/ 100"},
        ]
        charts = [
            {"id": "governance_distribution", "type": "pie", "label_ar": "توزيع الحوكمة", "label_en": "Governance Distribution"},
        ]
        try:
            from kpi_service import KPIService
            
            # Genuine Governance Distribution
            dist = AnalyticsService.get_governance_distribution(db, period_start, period_end, kg_filter)
            
            # Genuine Network Governance Score
            gov_score = AnalyticsService._compute_network_governance_score(db, period_start, period_end)
            kpis[1]["value"] = gov_score
            
            # Genuine Ratio Compliance Score
            kindergartens = db.query(models.Kindergarten.id).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
            if kg_filter:
                kindergartens = kindergartens.filter(models.Kindergarten.id.in_(kg_filter))
            kg_ids = [k[0] for k in kindergartens.all()]
            
            total_ratio = 0
            count = 0
            for k_id in kg_ids:
                rc = KPIService.compute_ratio_compliance(db, k_id, period_start, period_end)
                if rc > 0:
                    total_ratio += rc
                    count += 1
            
            kpis[0]["value"] = round(total_ratio / count, 1) if count > 0 else 0.0
            
            total = max(dist.green + dist.amber + dist.red, 1)
            total_records = total
            
            charts[0]["data"] = {
                "labels": [{"ar": "أخضر", "en": "Green"}, {"ar": "أصفر", "en": "Amber"}, {"ar": "أحمر", "en": "Red"}],
                "datasets": [{"label": {"ar": "الحوكمة", "en": "Governance"}, "data": [dist.green, dist.amber, dist.red], "backgroundColor": ["#198754", "#ffc107", "#dc3545"]}]
            }
            
            # Use dynamic quality evaluation
            data_quality["completeness_percent"] = 100.0 if count > 0 else 0.0
        except Exception as e:
            logging.getLogger(__name__).error("Failed to load governance data in preview_report", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الحوكمة", "en": "Failed to load governance data"})

    elif report_type == "enrollment":
        kpis = [
            {"id": "total_applications", "label_ar": "إجمالي الطلبات", "label_en": "Total Applications", "value": 0, "unit": ""},
            {"id": "approved", "label_ar": "موافق عليه", "label_en": "Approved", "value": 0, "unit": ""},
            {"id": "rejected", "label_ar": "مرفوض", "label_en": "Rejected", "value": 0, "unit": ""},
        ]
        charts = [
            {"id": "enrollment_funnel", "type": "bar", "label_ar": "قمع التسجيل", "label_en": "Enrollment Funnel"},
            {"id": "source_breakdown", "type": "doughnut", "label_ar": "توزيع المصادر", "label_en": "Source Breakdown"},
        ]
        try:
            analytics = get_enrollment_analytics(
                db, period_start, period_end,
                kindergarten_ids=kg_filter,
                status_filter=filters.get("status"),
                source_filter=filters.get("source"),
                reviewer_id=filters.get("reviewer_id"),
            )
            kpis[0]["value"] = analytics.get("total_applications", 0)
            kpis[1]["value"] = analytics.get("status_breakdown", {}).get("ACCEPTED", 0)
            kpis[2]["value"] = analytics.get("status_breakdown", {}).get("REJECTED", 0)
            total_records = analytics.get("total_applications", 0)
            
            charts[0]["data"] = {
                "labels": [{"ar": "الإجمالي", "en": "Total"}, {"ar": "موافق عليه", "en": "Approved"}, {"ar": "مرفوض", "en": "Rejected"}],
                "datasets": [{"label": {"ar": "الطلبات", "en": "Applications"}, "data": [total_records, kpis[1]["value"], kpis[2]["value"]], "backgroundColor": ["#0d6efd", "#198754", "#dc3545"]}]
            }
            
            from sqlalchemy import func
            source_q = db.query(models.EnrollmentApplication.source, func.count(models.EnrollmentApplication.id)).filter(
                func.date(models.EnrollmentApplication.created_at) >= period_start,
                func.date(models.EnrollmentApplication.created_at) <= period_end
            )
            if kg_filter: source_q = source_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
            source_data = source_q.group_by(models.EnrollmentApplication.source).all()
            charts[1]["data"] = {
                "labels": [{"ar": row[0].value if hasattr(row[0], 'value') else str(row[0]), "en": row[0].value if hasattr(row[0], 'value') else str(row[0])} for row in source_data],
                "datasets": [{"label": {"ar": "المصدر", "en": "Source"}, "data": [row[1] for row in source_data], "backgroundColor": ["#6610f2", "#0dcaf0", "#ffc107", "#20c997"]}]
            }
        except Exception:
            warnings.append({"ar": "تعذر تحميل بيانات التسجيل", "en": "Failed to load enrollment data"})

    elif report_type == "full_audit":
        kpis = [
            {"id": "total_actions", "label_ar": "إجمالي الإجراءات", "label_en": "Total Actions", "value": 0, "unit": ""},
            {"id": "failed_actions", "label_ar": "إجراءات فاشلة", "label_en": "Failed Actions", "value": 0, "unit": ""},
        ]
        charts = [
            {"id": "actions_by_module", "type": "bar", "label_ar": "حسب الوحدة", "label_en": "By Module"},
        ]
        try:
            query = db.query(models.AuditLog).filter(
                models.AuditLog.created_at >= utc_start,
                models.AuditLog.created_at <= utc_end,
            )
            if kg_filter:
                # AuditLog doesn't have direct kindergarten_id; skip kindergarten filtering for audit preview
                pass
            total_records = query.count()
            kpis[0]["value"] = total_records
            # Count high sensitivity as "failed" proxy
            high_risk = query.filter(models.AuditLog.sensitivity_level >= 3).count()
            kpis[1]["value"] = high_risk
        except Exception:
            warnings.append({"ar": "تعذر تحميل سجل التدقيق", "en": "Failed to load audit log data"})

    elif report_type == "staff_training":
        kpis = [
            {"id": "trained_count", "label_ar": "موظفون مدرَّبون", "label_en": "Trained Staff", "value": 0, "unit": ""},
            {"id": "training_rate", "label_ar": "معدل التدريب", "label_en": "Training Rate", "value": 0, "unit": "%"},
            {"id": "ratio_compliant", "label_ar": "روضات ملتزمة بالنسب", "label_en": "Ratio-Compliant KGs", "value": 0, "unit": ""},
            {"id": "ratio_violations", "label_ar": "مخالفات النسب", "label_en": "Ratio Violations", "value": 0, "unit": ""},
            {"id": "avg_compliance_score", "label_ar": "متوسط درجة الامتثال", "label_en": "Avg Compliance Score", "value": 0, "unit": "%"},
        ]
        charts = [
            {"id": "training_by_kg", "type": "bar", "label_ar": "التدريب حسب الروضة", "label_en": "Training by KG"},
            {"id": "ratio_compliance_dist", "type": "doughnut", "label_ar": "توزيع امتثال النسب", "label_en": "Ratio Compliance Distribution"},
        ]
        try:
            from sqlalchemy import func
            stc_q = db.query(func.count(models.StaffTrainingCompletion.id)).filter(
                models.StaffTrainingCompletion.completed_at >= utc_start,
                models.StaffTrainingCompletion.completed_at <= utc_end,
                models.StaffTrainingCompletion.passed == True,
            )
            kpis[0]["value"] = stc_q.scalar() or 0

            # Total staff (users with SUPERVISOR role)
            total_supervisors = db.query(func.count(models.User.id)).filter(
                models.User.role == models.UserRole.SUPERVISOR,
                models.User.deleted_at.is_(None),
            ).scalar() or 0
            kpis[1]["value"] = round(kpis[0]["value"] / total_supervisors * 100, 1) if total_supervisors > 0 else 0.0

            rc_q = db.query(models.RatioCompliance)
            if kg_filter:
                rc_q = rc_q.filter(models.RatioCompliance.kindergarten_id.in_(kg_filter))
            rc_q = rc_q.filter(
                models.RatioCompliance.checked_at >= utc_start,
                models.RatioCompliance.checked_at <= utc_end,
            )
            rc_rows = rc_q.all()
            total_rc = len(rc_rows)
            compliant = sum(1 for r in rc_rows if getattr(r, 'is_compliant', False))
            kpis[2]["value"] = compliant
            kpis[3]["value"] = total_rc - compliant
            scores = [float(getattr(r, 'compliance_score', 0) or 0) for r in rc_rows]
            kpis[4]["value"] = round(sum(scores) / len(scores), 1) if scores else 0.0
            total_records = kpis[0]["value"]

            # Training by KG
            tby_kg = db.query(
                models.Kindergarten.name_ar,
                func.count(models.StaffTrainingCompletion.id)
            ).join(
                models.StaffTrainingCompletion,
                models.StaffTrainingCompletion.kindergarten_id == models.Kindergarten.id,
                isouter=True,
            ).filter(
                models.StaffTrainingCompletion.completed_at >= utc_start,
                models.StaffTrainingCompletion.completed_at <= utc_end,
            )
            if kg_filter:
                tby_kg = tby_kg.filter(models.Kindergarten.id.in_(kg_filter))
            tby_kg_data = tby_kg.group_by(models.Kindergarten.name_ar).limit(15).all()
            charts[0]["data"] = {
                "labels": [{"ar": row[0] or "—", "en": row[0] or "—"} for row in tby_kg_data],
                "datasets": [{"label": {"ar": "التدريب", "en": "Training"}, "data": [row[1] for row in tby_kg_data], "backgroundColor": "#4F46E5"}],
            }
            charts[1]["data"] = {
                "labels": [{"ar": "ملتزم", "en": "Compliant"}, {"ar": "غير ملتزم", "en": "Non-Compliant"}],
                "datasets": [{"data": [compliant, total_rc - compliant], "backgroundColor": ["#198754", "#dc3545"]}],
            }
        except Exception as e:
            logger.error(f"staff_training preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الموظفين", "en": "Failed to load staff data"})

    elif report_type == "welfare":
        kpis = [
            {"id": "open_incidents", "label_ar": "حوادث مفتوحة", "label_en": "Open Incidents", "value": 0, "unit": ""},
            {"id": "overdue_sla", "label_ar": "SLA متأخرة", "label_en": "Overdue SLA", "value": 0, "unit": ""},
            {"id": "parent_informed_rate", "label_ar": "معدل إخطار الوالدين", "label_en": "Parent Informed Rate", "value": 0, "unit": "%"},
            {"id": "avg_resolution_days", "label_ar": "متوسط أيام الحل", "label_en": "Avg Resolution Days", "value": 0, "unit": "days"},
            {"id": "safeguarding_cases", "label_ar": "قضايا الحماية", "label_en": "Safeguarding Cases", "value": 0, "unit": ""},
        ]
        charts = [
            {"id": "incidents_by_type", "type": "doughnut", "label_ar": "الحوادث حسب النوع", "label_en": "Incidents by Type"},
            {"id": "welfare_trend", "type": "line", "label_ar": "اتجاه الرفاهية", "label_en": "Welfare Trend"},
        ]
        try:
            from sqlalchemy import func
            now_dt = _jordan_now()
            inc_q = db.query(models.Incident).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
                models.Incident.deleted_at.is_(None),
            )
            if kg_filter:
                inc_q = inc_q.filter(models.Incident.kindergarten_id.in_(kg_filter))

            all_incs = inc_q.all()
            total_records = len(all_incs)
            open_incs = [i for i in all_incs if i.closed_at is None]
            kpis[0]["value"] = len(open_incs)

            overdue = [i for i in open_incs if i.followup_sla_deadline and i.followup_sla_deadline < now_dt]
            kpis[1]["value"] = len(overdue)

            informed = [i for i in all_incs if i.parent_informed]
            kpis[2]["value"] = round(len(informed) / len(all_incs) * 100, 1) if all_incs else 0.0

            closed_incs = [i for i in all_incs if i.closed_at]
            if closed_incs:
                avg_days = sum(
                    (i.closed_at - i.occurred_at).days for i in closed_incs
                ) / len(closed_incs)
                kpis[3]["value"] = round(avg_days, 1)

            sg_q = db.query(func.count(models.SafeguardingCase.id)).filter(
                models.SafeguardingCase.created_at >= utc_start,
                models.SafeguardingCase.created_at <= utc_end,
            )
            if kg_filter:
                sg_q = sg_q.filter(models.SafeguardingCase.kindergarten_id.in_(kg_filter))
            kpis[4]["value"] = sg_q.scalar() or 0

            # By type
            type_data = {}
            for i in all_incs:
                t = i.type.value if hasattr(i.type, 'value') else str(i.type)
                type_data[t] = type_data.get(t, 0) + 1
            charts[0]["data"] = {
                "labels": [{"ar": k, "en": k} for k in type_data],
                "datasets": [{"data": list(type_data.values()), "backgroundColor": ["#4F46E5","#dc3545","#ffc107","#198754","#0dcaf0"]}],
            }

            # Trend by month
            from collections import Counter
            month_counts: Counter = Counter()
            for i in all_incs:
                key = i.occurred_at.strftime("%Y-%m") if i.occurred_at else "unknown"
                month_counts[key] += 1
            sorted_months = sorted(month_counts.keys())
            charts[1]["data"] = {
                "labels": [{"ar": m, "en": m} for m in sorted_months],
                "datasets": [{"label": {"ar": "الحوادث", "en": "Incidents"}, "data": [month_counts[m] for m in sorted_months], "borderColor": "#dc3545", "fill": False}],
            }
        except Exception as e:
            logger.error(f"welfare preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الرفاهية", "en": "Failed to load welfare data"})

    elif report_type == "trends":
        kpis = [
            {"id": "attendance_change", "label_ar": "تغير الحضور", "label_en": "Attendance Change", "value": 0, "unit": "%"},
            {"id": "incident_change", "label_ar": "تغير الحوادث", "label_en": "Incident Change", "value": 0, "unit": "%"},
            {"id": "enrollment_change", "label_ar": "تغير التسجيل", "label_en": "Enrollment Change", "value": 0, "unit": "%"},
            {"id": "report_submission_change", "label_ar": "تغير نسبة التقارير", "label_en": "Report Submission Change", "value": 0, "unit": "%"},
        ]
        charts = [
            {"id": "multi_metric_trend", "type": "line", "label_ar": "اتجاه متعدد المقاييس", "label_en": "Multi-Metric Trend"},
        ]
        try:
            from sqlalchemy import func
            # Attendance trend
            att_q = db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            if kg_filter:
                att_q = att_q.join(models.Class).filter(models.Class.kindergarten_id.in_(kg_filter))
            att_data = att_q.group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()

            # Incident trend
            inc_q = db.query(
                func.date(models.Incident.occurred_at).label("d"),
                func.count(models.Incident.id),
            ).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
                models.Incident.deleted_at.is_(None),
            )
            if kg_filter:
                inc_q = inc_q.filter(models.Incident.kindergarten_id.in_(kg_filter))
            inc_data = inc_q.group_by("d").order_by("d").all()

            # Report submission trend
            rep_q = db.query(models.DailyReport.date, func.count(models.DailyReport.id)).filter(
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
            )
            if kg_filter:
                rep_q = rep_q.filter(models.DailyReport.kindergarten_id.in_(kg_filter))
            rep_data = rep_q.group_by(models.DailyReport.date).order_by(models.DailyReport.date).all()

            # Build combined labels from all unique dates
            all_dates = sorted(set(
                [str(r[0]) for r in att_data] +
                [str(r[0]) for r in inc_data] +
                [str(r[0]) for r in rep_data]
            ))
            att_map = {str(r[0]): r[1] for r in att_data}
            inc_map = {str(r[0]): r[1] for r in inc_data}
            rep_map = {str(r[0]): r[1] for r in rep_data}

            charts[0]["data"] = {
                "labels": [{"ar": d, "en": d} for d in all_dates],
                "datasets": [
                    {"label": {"ar": "الحضور", "en": "Attendance"}, "data": [att_map.get(d, 0) for d in all_dates], "borderColor": "#4F46E5", "fill": False},
                    {"label": {"ar": "الحوادث", "en": "Incidents"}, "data": [inc_map.get(d, 0) for d in all_dates], "borderColor": "#dc3545", "fill": False},
                    {"label": {"ar": "التقارير", "en": "Reports"}, "data": [rep_map.get(d, 0) for d in all_dates], "borderColor": "#198754", "fill": False},
                ],
            }
            total_records = len(all_dates)

            # Period-over-period % changes
            half = len(all_dates) // 2
            if half > 0:
                att_vals = [att_map.get(d, 0) for d in all_dates]
                first_att = sum(att_vals[:half]) or 1
                last_att = sum(att_vals[half:])
                kpis[0]["value"] = round((last_att - first_att) / first_att * 100, 1)

                inc_vals = [inc_map.get(d, 0) for d in all_dates]
                first_inc = sum(inc_vals[:half]) or 1
                last_inc = sum(inc_vals[half:])
                kpis[1]["value"] = round((last_inc - first_inc) / first_inc * 100, 1)

                rep_vals = [rep_map.get(d, 0) for d in all_dates]
                first_rep = sum(rep_vals[:half]) or 1
                last_rep = sum(rep_vals[half:])
                kpis[3]["value"] = round((last_rep - first_rep) / first_rep * 100, 1)

        except Exception as e:
            logger.error(f"trends preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الاتجاهات", "en": "Failed to load trends data"})

    elif report_type == "capacity":
        kpis = [
            {"id": "total_capacity", "label_ar": "السعة الإجمالية", "label_en": "Total Capacity", "value": 0, "unit": ""},
            {"id": "enrolled_count", "label_ar": "المسجلون", "label_en": "Enrolled", "value": 0, "unit": ""},
            {"id": "utilization_rate", "label_ar": "معدل الاستخدام", "label_en": "Utilization Rate", "value": 0, "unit": "%"},
            {"id": "waitlist_count", "label_ar": "قائمة الانتظار", "label_en": "Waitlist", "value": 0, "unit": ""},
            {"id": "available_slots", "label_ar": "مقاعد متاحة", "label_en": "Available Slots", "value": 0, "unit": ""},
        ]
        charts = [
            {"id": "capacity_by_gov", "type": "bar", "label_ar": "السعة حسب المحافظة", "label_en": "Capacity by Governorate"},
            {"id": "utilization_dist", "type": "doughnut", "label_ar": "توزيع نسبة الاستخدام", "label_en": "Utilization Distribution"},
        ]
        try:
            from sqlalchemy import func
            kg_q = db.query(models.Kindergarten).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            )
            if kg_filter:
                kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_filter))
            kgs = kg_q.all()

            total_cap = sum(getattr(kg, 'capacity', 0) or 0 for kg in kgs)
            kpis[0]["value"] = total_cap

            enrolled = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            )
            if kg_filter:
                enrolled = enrolled.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
            enrolled_cnt = enrolled.scalar() or 0
            kpis[1]["value"] = enrolled_cnt
            kpis[2]["value"] = round(enrolled_cnt / total_cap * 100, 1) if total_cap > 0 else 0.0
            kpis[4]["value"] = max(0, total_cap - enrolled_cnt)

            waitlist = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
            )
            if kg_filter:
                waitlist = waitlist.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
            kpis[3]["value"] = waitlist.scalar() or 0

            total_records = len(kgs)

            # Capacity by governorate
            gov_cap = {}
            for kg in kgs:
                gov = kg.governorate or "Other"
                gov_cap[gov] = gov_cap.get(gov, 0) + (getattr(kg, 'capacity', 0) or 0)
            charts[0]["data"] = {
                "labels": [{"ar": g, "en": g} for g in gov_cap],
                "datasets": [{"label": {"ar": "السعة", "en": "Capacity"}, "data": list(gov_cap.values()), "backgroundColor": "#4F46E5"}],
            }

            # Utilization distribution: low/medium/high
            low = sum(1 for kg in kgs if (getattr(kg, 'capacity', 1) or 1) > 0 and enrolled_cnt / (getattr(kg, 'capacity', 1) or 1) < 0.5)
            med = sum(1 for kg in kgs if 0.5 <= enrolled_cnt / (getattr(kg, 'capacity', 1) or 1) < 0.85)
            high = len(kgs) - low - med
            charts[1]["data"] = {
                "labels": [{"ar": "منخفض <50%", "en": "Low <50%"}, {"ar": "متوسط 50-85%", "en": "Medium 50-85%"}, {"ar": "مرتفع >85%", "en": "High >85%"}],
                "datasets": [{"data": [low, med, high], "backgroundColor": ["#198754", "#ffc107", "#dc3545"]}],
            }
        except Exception as e:
            logger.error(f"capacity preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات السعة", "en": "Failed to load capacity data"})

    elif report_type == "parent_engagement":
        kpis = [
            {"id": "total_reports_viewed", "label_ar": "تقارير مُشاهَدة", "label_en": "Reports Viewed", "value": 0, "unit": ""},
            {"id": "view_rate", "label_ar": "معدل المشاهدة", "label_en": "View Rate", "value": 0, "unit": "%"},
            {"id": "parent_informed_count", "label_ar": "أولياء مُبلَّغون", "label_en": "Parents Informed", "value": 0, "unit": ""},
            {"id": "avg_view_lag_hours", "label_ar": "متوسط تأخر المشاهدة (ساعات)", "label_en": "Avg View Lag (hours)", "value": 0, "unit": "h"},
        ]
        charts = [
            {"id": "daily_views", "type": "line", "label_ar": "المشاهدات اليومية", "label_en": "Daily Views"},
        ]
        try:
            from sqlalchemy import func
            view_q = db.query(models.DailyReportView).filter(
                models.DailyReportView.viewed_at >= utc_start,
                models.DailyReportView.viewed_at <= utc_end,
            )
            if kg_filter:
                view_q = view_q.join(
                    models.DailyReport,
                    models.DailyReportView.daily_report_id == models.DailyReport.id,
                ).filter(models.DailyReport.kindergarten_id.in_(kg_filter))

            total_viewed = view_q.count()
            kpis[0]["value"] = total_viewed

            total_reports = db.query(func.count(models.DailyReport.id)).filter(
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
            )
            if kg_filter:
                total_reports = total_reports.filter(models.DailyReport.kindergarten_id.in_(kg_filter))
            total_rep_cnt = total_reports.scalar() or 0
            kpis[1]["value"] = round(total_viewed / total_rep_cnt * 100, 1) if total_rep_cnt > 0 else 0.0

            informed_q = db.query(func.count(models.Incident.id)).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
                models.Incident.parent_informed == True,
                models.Incident.deleted_at.is_(None),
            )
            if kg_filter:
                informed_q = informed_q.filter(models.Incident.kindergarten_id.in_(kg_filter))
            kpis[2]["value"] = informed_q.scalar() or 0

            total_records = total_viewed

            daily_views = db.query(
                func.date(models.DailyReportView.viewed_at).label("d"),
                func.count(models.DailyReportView.id),
            ).filter(
                models.DailyReportView.viewed_at >= utc_start,
                models.DailyReportView.viewed_at <= utc_end,
            ).group_by("d").order_by("d").all()
            charts[0]["data"] = {
                "labels": [{"ar": str(r[0]), "en": str(r[0])} for r in daily_views],
                "datasets": [{"label": {"ar": "المشاهدات", "en": "Views"}, "data": [r[1] for r in daily_views], "borderColor": "#0dcaf0", "fill": True}],
            }
        except Exception as e:
            logger.error(f"parent_engagement preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات مشاركة الوالدين", "en": "Failed to load parent engagement data"})

    elif report_type == "data_quality":
        kpis = [
            {"id": "active_kgs", "label_ar": "الروضات الفعّالة", "label_en": "Active KGs", "value": 0, "unit": ""},
            {"id": "submission_rate", "label_ar": "نسبة تقديم التقارير", "label_en": "Report Submission Rate", "value": 0, "unit": "%"},
            {"id": "missing_reports", "label_ar": "تقارير مفقودة", "label_en": "Missing Reports", "value": 0, "unit": ""},
            {"id": "zero_attendance_days", "label_ar": "أيام بدون حضور", "label_en": "Zero-Attendance Days", "value": 0, "unit": ""},
            {"id": "data_completeness", "label_ar": "اكتمال البيانات", "label_en": "Data Completeness", "value": 0, "unit": "%"},
        ]
        charts = [
            {"id": "submission_by_gov", "type": "bar", "label_ar": "التقديم حسب المحافظة", "label_en": "Submission by Governorate"},
        ]
        try:
            from sqlalchemy import func
            kg_q = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)
            if kg_filter:
                kg_q = kg_q.filter(models.Kindergarten.id.in_(kg_filter))
            active_kgs = kg_q.all()
            kpis[0]["value"] = len(active_kgs)

            period_days = (period_end - period_start).days + 1
            expected = len(active_kgs) * period_days
            actual = db.query(func.count(models.DailyReport.id)).filter(
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
            )
            if kg_filter:
                actual = actual.filter(models.DailyReport.kindergarten_id.in_(kg_filter))
            actual_cnt = actual.scalar() or 0
            kpis[2]["value"] = max(0, expected - actual_cnt)
            kpis[1]["value"] = round(actual_cnt / expected * 100, 1) if expected > 0 else 0.0

            att_days_q = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            if kg_filter:
                att_days_q = att_days_q.join(models.Class).filter(models.Class.kindergarten_id.in_(kg_filter))
            if att_days_q.scalar() or 0 == 0:
                kpis[3]["value"] = period_days

            kpis[4]["value"] = kpis[1]["value"]
            total_records = actual_cnt

            # Submission by governorate
            gov_sub = db.query(
                models.Kindergarten.governorate,
                func.count(models.DailyReport.id)
            ).join(
                models.DailyReport,
                models.DailyReport.kindergarten_id == models.Kindergarten.id,
                isouter=True,
            ).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
            )
            if kg_filter:
                gov_sub = gov_sub.filter(models.Kindergarten.id.in_(kg_filter))
            gov_sub_data = gov_sub.group_by(models.Kindergarten.governorate).all()
            charts[0]["data"] = {
                "labels": [{"ar": r[0] or "—", "en": r[0] or "—"} for r in gov_sub_data],
                "datasets": [{"label": {"ar": "التقارير", "en": "Reports"}, "data": [r[1] for r in gov_sub_data], "backgroundColor": "#0d6efd"}],
            }
        except Exception as e:
            logger.error(f"data_quality preview failed: {e}", exc_info=True)
            warnings.append({"ar": "تعذر تحميل بيانات الجودة", "en": "Failed to load data quality metrics"})

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported report type: {report_type}")

    # Build sample rows from first available data
    if report_type == "attendance":
        try:
            logs = db.query(models.AttendanceLog).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
            )
            if kg_filter:
                logs = logs.join(models.Child).join(models.EnrollmentApplication).filter(
                    models.EnrollmentApplication.kindergarten_id.in_(kg_filter)
                )
            logs = logs.limit(10).all()
            for log in logs:
                sample_data.append({
                    "date": log.date.isoformat(),
                    "child_id": log.child_id,
                    "status": log.status.value if hasattr(log.status, "value") else str(log.status),
                    "check_in": _to_jordan_iso(log.check_in_at),
                    "check_out": _to_jordan_iso(log.check_out_at),
                })
        except Exception:
            pass
    elif report_type == "incidents":
        try:
            incs = db.query(models.Incident).filter(
                models.Incident.occurred_at >= datetime.combine(period_start, datetime.min.time()),
                models.Incident.occurred_at <= datetime.combine(period_end, datetime.max.time()),
            )
            if kg_filter:
                incs = incs.filter(models.Incident.kindergarten_id.in_(kg_filter))
            incs = incs.limit(10).all()
            _inc_kg_ids = list({inc.kindergarten_id for inc in incs if inc.kindergarten_id})
            _inc_kg_map = {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(_inc_kg_ids)).all()}
            for inc in incs:
                kg = _inc_kg_map.get(inc.kindergarten_id)
                sample_data.append({
                    "date": inc.occurred_at.date().isoformat(),
                    "kindergarten": kg.name_ar if kg else "",
                    "type": inc.type.value if hasattr(inc.type, "value") else str(inc.type),
                    "severity": inc.severity_level.value if hasattr(inc.severity_level, "value") else str(inc.severity_level),
                    "status": inc.status.value if hasattr(inc.status, "value") else str(inc.status),
                })
        except Exception:
            pass
    elif report_type == "enrollment":
        try:
            apps = db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.created_at >= datetime.combine(period_start, datetime.min.time()),
                models.EnrollmentApplication.created_at <= datetime.combine(period_end, datetime.max.time()),
            )
            if kg_filter:
                apps = apps.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
            apps = apps.limit(10).all()
            _app_cids = [a.child_id for a in apps if a.child_id]
            _app_kgids = list({a.kindergarten_id for a in apps if a.kindergarten_id})
            _app_children = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(_app_cids)).all()}
            _app_pids = list({c.parent_id for c in _app_children.values() if c.parent_id})
            _app_parents = {p.id: p for p in db.query(models.ParentProfile).filter(models.ParentProfile.id.in_(_app_pids)).all()}
            _app_kgs = {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(_app_kgids)).all()}
            for app in apps:
                child = _app_children.get(app.child_id)
                parent = _app_parents.get(child.parent_id) if child else None
                kg = _app_kgs.get(app.kindergarten_id)
                sample_data.append({
                    "child_name": f"{child.first_name} {child.last_name}" if child else "",
                    "parent_name": f"{parent.first_name} {parent.last_name}" if parent else "",
                    "kindergarten": kg.name_ar if kg else "",
                    "status": app.status.value if hasattr(app.status, "value") else str(app.status),
                    "source": app.source,
                    "submitted_at": _to_jordan_iso(app.submitted_at),
                })
        except Exception:
            pass
    elif report_type == "full_audit":
        try:
            logs = db.query(models.AuditLog).filter(
                models.AuditLog.created_at >= datetime.combine(period_start, datetime.min.time()),
                models.AuditLog.created_at <= datetime.combine(period_end, datetime.max.time()),
            ).limit(10).all()
            for log in logs:
                user = db.query(models.User).filter(models.User.id == log.user_id).first()
                sample_data.append({
                    "timestamp": _to_jordan_iso(log.created_at),
                    "user": user.full_name or user.username if user else "system",
                    "role": log.actor_role or (user.role.value if user else ""),
                    "action": log.action,
                    "entity_type": log.entity_type,
                    "sensitivity_level": log.sensitivity_level,
                })
        except Exception:
            pass

    if total_records == 0:
        warnings.append({"ar": "لا توجد سجلات مطابقة للفلاتر المحددة", "en": "No records match the selected filters"})

    data_quality = evaluate_data_quality(report_type, sample_data)
    if data_quality["completeness_percent"] < 90.0:
        warnings.append({"ar": "جودة البيانات منخفضة بسبب حقول مفقودة أو مكررة", "en": "Data quality is low due to missing or duplicate fields"})

    return ReportPreviewResponse(
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        filters_applied=filters,
        total_records=total_records,
        kpis=kpis,
        charts=charts,
        sample_data=sample_data,
        data_quality=data_quality,
        warnings=warnings,
        insights=insights,
    )



def evaluate_data_quality(report_type: str, sample_data: list) -> dict:
    if not sample_data:
        return {
            "total_records": 0,
            "missing_fields": 0,
            "duplicate_records": 0,
            "incomplete_records": 0,
            "completeness_percent": 100.0,
            "last_refresh": datetime.now(timezone.utc).isoformat(),
        }
    
    total_fields = 0
    missing_fields = 0
    duplicates = 0
    incomplete = 0
    
    seen_ids = set()
    for row in sample_data:
        # Check duplicates
        row_id = row.get("child_id") or row.get("id") or row.get("timestamp") or row.get("child_name")
        if row_id:
            if row_id in seen_ids:
                duplicates += 1
            seen_ids.add(row_id)
            
        # Check completeness
        for k, v in row.items():
            total_fields += 1
            if v is None or v == "" or (isinstance(v, list) and not v):
                missing_fields += 1
                
        # Incomplete row check
        if report_type == "attendance":
            if row.get("status") not in ["PRESENT", "ABSENT"]:
                incomplete += 1
        elif report_type == "incidents":
            if not row.get("type") or not row.get("severity"):
                incomplete += 1
                
    total_fields = max(total_fields, 1)
    completeness_percent = round(((total_fields - missing_fields) / total_fields) * 100.0, 2)
    
    return {
        "total_records": len(sample_data),
        "missing_fields": missing_fields,
        "duplicate_records": duplicates,
        "incomplete_records": incomplete,
        "completeness_percent": completeness_percent,
        "last_refresh": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/reports/stats")
def get_reports_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get metrics on generated and scheduled reports"""
    validators.validate_admin_role(current_user)
    created_count = db.query(models.ExportJob).filter(models.ExportJob.user_id == current_user.id).count()
    scheduled_count = db.query(models.ScheduledReport).filter(
        models.ScheduledReport.created_by == current_user.id,
        models.ScheduledReport.is_active == True
    ).count()
    failed_count = db.query(models.ExportJob).filter(
        models.ExportJob.user_id == current_user.id,
        models.ExportJob.status == models.ExportStatus.FAILED
    ).count()
    return {
        "created_count": created_count,
        "scheduled_count": scheduled_count,
        "failed_count": failed_count
    }


@router.get("/reports/history", response_model=List[ReportHistoryItem])
def get_report_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return recent export/report history for the current user."""
    jobs = db.query(models.ExportJob).filter(
        models.ExportJob.user_id == current_user.id,
    ).order_by(models.ExportJob.created_at.desc()).limit(limit).all()

    items = []
    for job in jobs:
        items.append(ReportHistoryItem(
            id=job.id,
            report_type=job.report_type,
            report_name=job.report_type.replace("_", " ").title(),
            generated_by=current_user.username,
            generated_at=_to_jordan_iso(job.created_at),
            period_start=_jordan_today() - timedelta(days=30),
            period_end=_jordan_today(),
            format=job.export_format.value if hasattr(job.export_format, "value") else str(job.export_format),
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            file_size=job.file_size,
            filters=job.filters or {},
        ))
    return items


@router.post("/reports/templates", response_model=ReportTemplateResponse)
def create_report_template(
    payload: ReportTemplateCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a report configuration as a reusable template."""
    validators.validate_admin_role(current_user)
    template = models.ReportTemplate(
        name=payload.name,
        report_type=payload.report_type,
        filters=payload.filters,
        export_format=payload.export_format,
        include_charts=payload.include_charts,
        include_summary=payload.include_summary,
        created_by=current_user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return ReportTemplateResponse(
        id=template.id,
        name=template.name,
        report_type=template.report_type,
        filters=template.filters or {},
        export_format=template.export_format,
        include_charts=template.include_charts,
        include_summary=template.include_summary,
        last_used_at=template.last_used_at,
        created_at=template.created_at,
    )


@router.get("/reports/templates", response_model=List[ReportTemplateResponse])
def list_report_templates(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List saved report templates for the current user."""
    templates = db.query(models.ReportTemplate).filter(
        models.ReportTemplate.created_by == current_user.id,
    ).order_by(models.ReportTemplate.created_at.desc()).all()
    return [
        ReportTemplateResponse(
            id=t.id,
            name=t.name,
            report_type=t.report_type,
            filters=t.filters or {},
            export_format=t.export_format,
            include_charts=t.include_charts,
            include_summary=t.include_summary,
            last_used_at=t.last_used_at,
            created_at=t.created_at,
        )
        for t in templates
    ]


@router.post("/reports/schedules", response_model=ScheduledReportResponse)
def create_scheduled_report(
    payload: ScheduledReportCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a scheduled report."""
    validators.validate_admin_role(current_user)
    schedule = models.ScheduledReport(
        name=payload.name,
        report_type=payload.report_type,
        filters=payload.filters,
        export_format=payload.export_format,
        frequency=payload.frequency,
        recipients=payload.recipients,
        next_run=payload.next_run,
        created_by=current_user.id,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return ScheduledReportResponse(
        id=schedule.id,
        name=schedule.name,
        report_type=schedule.report_type,
        filters=schedule.filters or {},
        export_format=schedule.export_format,
        frequency=schedule.frequency,
        recipients=schedule.recipients or [],
        next_run=schedule.next_run,
        last_run=schedule.last_run,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
    )


@router.get("/reports/schedules", response_model=List[ScheduledReportResponse])
def list_scheduled_reports(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List scheduled reports for the current user."""
    schedules = db.query(models.ScheduledReport).filter(
        models.ScheduledReport.created_by == current_user.id,
    ).order_by(models.ScheduledReport.created_at.desc()).all()
    return [
        ScheduledReportResponse(
            id=s.id,
            name=s.name,
            report_type=s.report_type,
            filters=s.filters or {},
            export_format=s.export_format,
            frequency=s.frequency,
            recipients=s.recipients or [],
            next_run=s.next_run,
            last_run=s.last_run,
            is_active=s.is_active,
            created_at=s.created_at,
        )
        for s in schedules
    ]


# =============================================================================
# AnalyticsService Implementation
# =============================================================================

class AnalyticsService:
    """Service class for computing analytics and KPIs across the network"""

    @staticmethod
    def get_network_summary(db: Session, period_start: date, period_end: date, kg_ids: Optional[List[int]] = None) -> NetworkSummary:
        """Get network-wide summary metrics"""
        from kpi_service import KPIService

        # Count total active kindergartens
        kg_query = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_ids:
            kg_query = kg_query.filter(models.Kindergarten.id.in_(kg_ids))
        total_kindergartens = kg_query.count()

        # Count total active children
        child_query = db.query(func.count(models.Child.id)).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
        if kg_ids:
            child_query = child_query.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total_children = child_query.scalar() or 0

        # Count total active enrollments
        enroll_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
        if kg_ids:
            enroll_q = enroll_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total_enrollments = enroll_q.scalar() or 0

        # Count total staff
        staff_query = db.query(func.count(models.User.id)).filter(
            models.User.role.in_([
                models.UserRole.ADMIN,
                models.UserRole.MANAGER,
                models.UserRole.SUPERVISOR
            ])
        )
        if kg_ids:
            staff_query = staff_query.filter(models.User.kindergarten_id.in_(kg_ids))
        total_staff = staff_query.scalar() or 0

        # Calculate total capacity (sum of all kindergarten capacities)
        # Note: Capacity not currently stored in database schema
        if kg_ids:
            total_capacity = db.query(func.sum(models.Class.capacity_total)).join(
                models.Kindergarten
            ).filter(
                models.Kindergarten.id.in_(kg_ids),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                models.Class.is_active == True
            ).scalar() or 0
        else:
            total_capacity = 0

        # Calculate enrollment rate
        enrollment_rate = (total_children / total_capacity * 100) if total_capacity > 0 else 0.0

        # Calculate network-wide attendance rate
        attendance_rate = AnalyticsService._compute_network_attendance_rate(db, period_start, period_end)

        # Calculate network-wide incident rate
        incident_rate = AnalyticsService._compute_network_incident_rate(db, period_start, period_end)

        # Calculate report submission and approval rates
        report_submission_rate = AnalyticsService._compute_report_submission_rate(db, period_start, period_end)
        report_approval_rate = AnalyticsService._compute_report_approval_rate(db, period_start, period_end)

        # Calculate average governance score (GCEI)
        governance_avg_score = AnalyticsService._compute_network_governance_score(db, period_start, period_end)

        return NetworkSummary(
            total_kindergartens=total_kindergartens,
            total_children=total_children,
            total_staff=total_staff,
            total_capacity=total_capacity,
            enrollment_rate=enrollment_rate,
            attendance_rate=attendance_rate,
            incident_rate=incident_rate,
            report_submission_rate=report_submission_rate,
            report_approval_rate=report_approval_rate,
            governance_avg_score=governance_avg_score
        )

    @staticmethod
    def get_governance_distribution(
        db: Session, period_start: date, period_end: date, kg_filter: Optional[List[int]] = None
    ) -> GovernanceDistribution:
        """
        Provide class-level access to governance distribution to match route calls.
        """
        kg_query = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_filter:
            kg_query = kg_query.filter(models.Kindergarten.id.in_(kg_filter))
        kindergartens = kg_query.all()

        green = amber = red = 0
        for kg in kindergartens:
            _, band = KPIService.compute_governance_score(db, kg.id, period_start, period_end)
            # Band is returned as "GREEN", "AMBER", or "RED" (uppercase)
            if band == "GREEN":
                green += 1
            elif band == "AMBER":
                amber += 1
            elif band == "RED":
                red += 1

        return GovernanceDistribution(green=green, amber=amber, red=red)

    @staticmethod
    def get_governorate_breakdown(
        db: Session,
        period_start: date,
        period_end: date,
        governorate: Optional[str] = None,
        allowed_kgs: Optional[List[int]] = None,
        allowed_governorates: Optional[List[str]] = None
    ) -> List[GovernorateMetrics]:
        """Get metrics broken down by governorate"""
        from kpi_service import KPIService

        # Get governorates with active kindergartens
        if governorate:
            governorates = [(governorate,)]
        else:
            governorates = db.query(models.Kindergarten.governorate).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).distinct().all()

        gov_names = [g for (g,) in governorates if g]
        if allowed_governorates is not None:
            gov_names = [g for g in gov_names if g in allowed_governorates]

        results = []
        for gov_name in gov_names:
            gov_kg_ids = _kg_ids_for_governorate(db, gov_name) or []
            if allowed_kgs is not None:
                gov_kg_ids = [kg for kg in gov_kg_ids if kg in allowed_kgs]
            if allowed_kgs is not None and not gov_kg_ids:
                continue

            # Count kindergartens in this governorate
            if gov_kg_ids:
                kg_count = len(gov_kg_ids)
            else:
                kg_count = db.query(func.count(models.Kindergarten.id)).filter(
                    models.Kindergarten.governorate == gov_name,
                    models.Kindergarten.status == models.KindergartenStatus.ACTIVE
                ).scalar() or 0

            # Count children in this governorate
            children_q = db.query(func.count(models.Child.id)).join(
                models.EnrollmentApplication
            ).join(
                models.Kindergarten
            ).filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            )
            if gov_kg_ids:
                children_q = children_q.filter(models.EnrollmentApplication.kindergarten_id.in_(gov_kg_ids))
            else:
                children_q = children_q.filter(models.Kindergarten.governorate == gov_name)
            children_count = children_q.scalar() or 0

            # Sum capacity of classes in active kindergartens for this governorate
            capacity_q = db.query(func.coalesce(func.sum(models.Class.capacity_total), 0)).join(
                models.Kindergarten,
                models.Kindergarten.id == models.Class.kindergarten_id
            ).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            )
            if gov_kg_ids:
                capacity_q = capacity_q.filter(models.Class.kindergarten_id.in_(gov_kg_ids))
            else:
                capacity_q = capacity_q.filter(models.Kindergarten.governorate == gov_name)
            capacity = capacity_q.scalar() or 0

            # Enrollment rate (children / capacity)
            enrollment_rate = round((children_count / capacity) * 100, 2) if capacity else 0.0

            # Calculate governorate attendance rate
            attendance_rate = AnalyticsService._compute_governorate_attendance_rate(
                db, gov_name, period_start, period_end, gov_kg_ids
            )

            # Calculate governorate incident rate
            incident_rate = AnalyticsService._compute_governorate_incident_rate(
                db, gov_name, period_start, period_end, gov_kg_ids
            )

            # Calculate governorate governance score
            governance_score = AnalyticsService._compute_governorate_governance_score(
                db, gov_name, period_start, period_end, gov_kg_ids
            )

            results.append(GovernorateMetrics(
                governorate=gov_name,
                kindergarten_count=kg_count,
                children_count=children_count,
                capacity=int(capacity),
                enrollment_rate=enrollment_rate,
                attendance_rate=attendance_rate,
                incident_rate=incident_rate,
                governance_score=governance_score
            ))

        return results

    @staticmethod
    def get_network_trends(db: Session, metric: str, period_start: date, period_end: date, kg_ids: Optional[List[int]] = None) -> List[TimeSeriesPoint]:
        """Get time-series trend data for network metrics"""
        trends = []

        # Generate monthly intervals
        current_date = period_start
        while current_date <= period_end:
            month_end = min(current_date + timedelta(days=30), period_end)

            if metric == "attendance":
                value = AnalyticsService._compute_network_attendance_rate(db, current_date, month_end, kg_ids)
            elif metric == "incidents":
                value = AnalyticsService._compute_network_incident_rate(db, current_date, month_end, kg_ids)
            else:
                value = 0.0

            trends.append(TimeSeriesPoint(
                date=current_date.isoformat(),
                value=round(value, 2),
                label=f"{current_date.strftime('%b %Y')}"
            ))

            # Move to next month
            current_date = current_date + timedelta(days=30)

        return trends

    @staticmethod
    def get_high_risk_children(db: Session, kg_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Get list of high-risk children based on attendance and incidents"""
        period_end = _jordan_today()
        period_start = period_end - timedelta(days=30)

        # Project kg_id alongside child to avoid lazy-load N+1 on .enrollments[0].kindergarten
        low_att_q = db.query(
            models.Child,
            func.count(models.AttendanceLog.id).label('attendance_days'),
            models.EnrollmentApplication.kindergarten_id.label('kg_id'),
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).outerjoin(
            models.AttendanceLog,
            and_(
                models.AttendanceLog.child_id == models.Child.id,
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
            )
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        if kg_ids:
            low_att_q = low_att_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        low_attendance_children = low_att_q.group_by(
            models.Child.id,
            models.EnrollmentApplication.kindergarten_id,
        ).having(
            func.count(models.AttendanceLog.id) / 30.0 < 0.8
        ).all()

        # Project kg_id from incident to avoid lazy-load N+1 on .incidents[0].kindergarten
        inc_q = db.query(
            models.Child,
            func.count(models.Incident.id).label('incident_count'),
            models.Incident.kindergarten_id.label('kg_id'),
        ).join(
            models.Incident,
            models.Incident.child_id == models.Child.id,
        ).filter(
            models.Incident.occurred_at >= period_start,
            models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL]),
        )
        if kg_ids:
            inc_q = inc_q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        recent_incidents = inc_q.group_by(
            models.Child.id,
            models.Incident.kindergarten_id,
        ).having(
            func.count(models.Incident.id) >= 2
        ).all()

        # Batch-load kindergarten names in two queries
        all_kg_ids = {row.kg_id for row in low_attendance_children if row.kg_id} | \
                     {row.kg_id for row in recent_incidents if row.kg_id}
        kg_name_map: dict[int, str] = {}
        if all_kg_ids:
            kg_name_map = {
                kg.id: kg.name_ar
                for kg in db.query(models.Kindergarten.id, models.Kindergarten.name_ar)
                            .filter(models.Kindergarten.id.in_(all_kg_ids))
                            .all()
            }

        risk_children = []
        for child, attendance_days, kg_id in low_attendance_children:
            attendance_rate = (attendance_days / 30.0) * 100
            risk_children.append({
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_name": kg_name_map.get(kg_id, "Unknown"),
                "risk_type": "Low Attendance",
                "risk_value": round(attendance_rate, 1),
                "description": f"Attendance rate: {round(attendance_rate, 1)}%",
            })
        for child, incident_count, kg_id in recent_incidents:
            risk_children.append({
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_name": kg_name_map.get(kg_id, "Unknown"),
                "risk_type": "Multiple Incidents",
                "risk_value": incident_count,
                "description": f"{incident_count} serious incidents in last 30 days",
            })

        return risk_children

    # Helper methods for computing network-level metrics

    @staticmethod
    def _compute_network_attendance_rate(db: Session, period_start: date, period_end: date, kg_ids: Optional[List[int]] = None) -> float:
        """Compute network-wide attendance rate (optionally filtered to a KG list)"""
        # Single aggregate query for attended child-days
        attended_q = db.query(func.count(models.AttendanceLog.id)).join(
            models.Child,
            models.AttendanceLog.child_id == models.Child.id,
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        ).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        if kg_ids:
            attended_q = attended_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total_attended_days = attended_q.scalar() or 0

        # Single aggregate query for active enrollment count
        enroll_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        if kg_ids:
            enroll_q = enroll_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total_active_enrollments = enroll_q.scalar() or 0

        days_in_period = (period_end - period_start).days + 1
        total_expected_days = total_active_enrollments * days_in_period

        if total_expected_days == 0:
            return 0.0

        return round((total_attended_days / total_expected_days) * 100, 2)

    @staticmethod
    def _compute_network_incident_rate(db: Session, period_start: date, period_end: date, kg_ids: Optional[List[int]] = None) -> float:
        """Compute network-wide incident rate per 1,000 attended child-days"""
        # Count total incidents
        incident_q = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        )
        if kg_ids:
            incident_q = incident_q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        total_incidents = incident_q.scalar() or 0

        # Count physically attended child-days (PRESENT + LATE only, excludes EXCUSED)
        child_days_q = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ]),
        )
        if kg_ids:
            child_days_q = child_days_q.join(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        total_child_days = child_days_q.scalar() or  0
        if total_child_days == 0:
            return 0.0


        return round((total_incidents / total_child_days) * 1000, 3)

    @staticmethod
    def _compute_network_serious_incident_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide serious incident rate per 1,000 attended child-days"""
        # Count serious incidents
        serious_incidents = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL])
        ).scalar() or 0

        # Count physically attended child-days (PRESENT + LATE only, excludes EXCUSED)
        total_child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ]),
        ).scalar() or 1

        return round((serious_incidents / total_child_days) * 1000, 3)

    @staticmethod
    def _compute_network_governance_score(db: Session, period_start: date, period_end: date) -> float:
        """Compute average governance score across all kindergartens"""
        from kpi_service import KPIService

        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kindergartens:
            return 0.0

        total_score = 0.0
        count = 0

        for kg in kindergartens:
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)
            if score > 0:
                total_score += score
                count += 1

        return round(total_score / count, 2) if count > 0 else 0.0

    @staticmethod
    def _compute_governorate_attendance_rate(
        db: Session,
        governorate: str,
        period_start: date,
        period_end: date,
        kg_ids: Optional[List[int]] = None
    ) -> float:
        """Compute attendance rate for a specific governorate"""
        # Get all kindergartens in the governorate
        if kg_ids is None:
            kg_rows = db.query(models.Kindergarten.id).filter(
                models.Kindergarten.governorate == governorate,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).all()
            kg_ids = [kg_id for (kg_id,) in kg_rows]

        if not kg_ids:
            return 0.0

        # Count attended days
        attended = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Count expected days
        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        days_in_period = (period_end - period_start).days + 1
        expected = active_enrollments * days_in_period

        if expected == 0:
            return 0.0

        return round((attended / expected) * 100, 2)

    @staticmethod
    def _compute_governorate_incident_rate(
        db: Session,
        governorate: str,
        period_start: date,
        period_end: date,
        kg_ids: Optional[List[int]] = None
    ) -> float:
        """Compute incident rate for a specific governorate"""
        # Get kindergarten IDs in governorate
        if kg_ids is None:
            kg_rows = db.query(models.Kindergarten.id).filter(
                models.Kindergarten.governorate == governorate,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).all()
            kg_ids = [kg_id for (kg_id,) in kg_rows]

        if not kg_ids:
            return 0.0

        # Count incidents
        incidents = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id.in_(kg_ids),
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        # Count physically attended child-days (PRESENT + LATE only, excludes EXCUSED)
        child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ]),
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
        ).scalar() or 1

        return round((incidents / child_days) * 1000, 3)

    @staticmethod
    def _compute_governorate_governance_score(
        db: Session,
        governorate: str,
        period_start: date,
        period_end: date,
        kg_ids: Optional[List[int]] = None
    ) -> float:
        """Compute average governance score for a governorate"""
        # Get all kindergartens in governorate
        kg_query = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_ids:
            kg_query = kg_query.filter(models.Kindergarten.id.in_(kg_ids))
        else:
            kg_query = kg_query.filter(models.Kindergarten.governorate == governorate)
        kindergartens = kg_query.all()

        if not kindergartens:
            return 0.0

        total_score = 0.0
        count = 0

        for kg in kindergartens:
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)
            if score > 0:
                total_score += score
                count += 1

        return round(total_score / count, 2) if count > 0 else 0.0

    @staticmethod
    def _compute_kindergarten_governance_score(db: Session, kindergarten_id: int, period_start: date, period_end: date) -> float:
        """Compute governance score (GCEI) for a specific kindergarten"""
        from kpi_service import KPIService

        try:
            # Get individual KPI scores
            attendance_rate = KPIService.compute_attendance_rate(db, kindergarten_id, period_start, period_end)
            incident_rate = KPIService.compute_incident_rate(db, kindergarten_id, period_start, period_end)
            serious_incident_rate = KPIService.compute_serious_incident_rate(db, kindergarten_id, period_start, period_end)
            ratio_compliance = KPIService.compute_ratio_compliance(db, kindergarten_id, period_start, period_end)

            # Normalize and weight the scores (simplified GCEI calculation)
            # Higher attendance = better score
            attendance_score = min(attendance_rate, 100) * 0.4

            # Lower incident rates = better score
            # compute_incident_rate() returns per-1,000 child-days; divide by 10 to
            # restore per-100 equivalent before applying the original multiplier.
            incident_score = max(0, 100 - (incident_rate / 10) * 10) * 0.3

            # Lower serious incident rates = better score
            serious_incident_score = max(0, 100 - (serious_incident_rate / 10) * 20) * 0.2

            # Higher ratio compliance = better score
            ratio_score = ratio_compliance * 0.1

            total_score = attendance_score + incident_score + serious_incident_score + ratio_score

            return round(total_score, 2)
        except SQLAlchemyError:
            logger.exception("Failed to compute kindergarten governance score due to database error")
            return 0.0
        except (ZeroDivisionError, TypeError, ValueError):
            logger.exception("Failed to compute kindergarten governance score due to invalid analytics data")
            return 0.0

    @staticmethod
    def _compute_report_submission_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide report submission rate"""
        # Count expected reports (one per kindergarten per day in period)
        days_in_period = (period_end - period_start).days + 1
        total_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).scalar() or 0
        expected_reports = total_kindergartens * days_in_period

        # Count actual submitted reports
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        ).scalar() or 0

        return round((submitted_reports / expected_reports * 100) if expected_reports > 0 else 0, 2)

    @staticmethod
    def _compute_report_approval_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide report approval rate"""
        # Count submitted reports
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        ).scalar() or 0

        # Count approved reports
        approved_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).scalar() or 0

        return round((approved_reports / submitted_reports * 100) if submitted_reports > 0 else 0, 2)

    # Advanced analytics cache helpers (used by /analytics/advanced-cache* endpoints)
    @staticmethod
    def get_advanced_analytics_cache(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_id: str,
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> Optional[models.AdvancedAnalyticsCache]:
        """Fetch a single cache entry for the requested dimension/period."""
        return db.query(models.AdvancedAnalyticsCache).filter(
            models.AdvancedAnalyticsCache.dimension_type == dimension_type,
            models.AdvancedAnalyticsCache.dimension_id == str(dimension_id),
            models.AdvancedAnalyticsCache.period_type == period_type,
            models.AdvancedAnalyticsCache.period_start == period_start,
            models.AdvancedAnalyticsCache.period_end == period_end
        ).first()

    @staticmethod
    def invalidate_advanced_analytics_cache(
        db: Session,
        dimension_type: Optional[models.AnalyticsDimensionType] = None,
        dimension_id: Optional[str] = None,
        period_type: Optional[models.AnalyticsPeriodType] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None
    ) -> int:
        """Delete cache rows matching supplied filters; returns rows deleted."""
        query = db.query(models.AdvancedAnalyticsCache)
        if dimension_type:
            query = query.filter(models.AdvancedAnalyticsCache.dimension_type == dimension_type)
        if dimension_id:
            query = query.filter(models.AdvancedAnalyticsCache.dimension_id == str(dimension_id))
        if period_type:
            query = query.filter(models.AdvancedAnalyticsCache.period_type == period_type)
        if period_start:
            query = query.filter(models.AdvancedAnalyticsCache.period_start == period_start)
        if period_end:
            query = query.filter(models.AdvancedAnalyticsCache.period_end == period_end)
        deleted = query.delete(synchronize_session=False)
        db.commit()
        return deleted

    @staticmethod
    def warm_advanced_analytics_cache(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_ids: List[str],
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> int:
        """Compute & store cache entries for provided ids; returns number created."""
        created = 0
        for dim_id in dimension_ids:
            AnalyticsService.compute_advanced_analytics(
                db, dimension_type, dim_id, period_type, period_start, period_end
            )
            created += 1
        return created

    @staticmethod
    def compute_advanced_analytics(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_id: str,
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> models.AdvancedAnalyticsCache:
        """
        Compute and persist advanced analytics metrics for a dimension/period.
        Existing cache row for same key is replaced.
        """
        # Remove any existing cache for this dimension/period
        existing = db.query(models.AdvancedAnalyticsCache).filter(
            models.AdvancedAnalyticsCache.dimension_type == dimension_type,
            models.AdvancedAnalyticsCache.dimension_id == str(dimension_id),
            models.AdvancedAnalyticsCache.period_type == period_type,
            models.AdvancedAnalyticsCache.period_start == period_start,
            models.AdvancedAnalyticsCache.period_end == period_end
        ).first()
        if existing:
            db.delete(existing)
            db.commit()

        # Initialize metrics
        attendance_rate = chronic_absence_rate = incident_rate_per_100 = None
        serious_incident_rate = ratio_compliance_rate = report_completion_rate = None
        parent_satisfaction_nps = child_development_index = staff_turnover_rate = None
        regulatory_compliance_score = attendance_trend_slope = risk_score = None
        improvement_velocity = attendance_incident_correlation = None
        staffing_quality_correlation = health_alerts_count = curriculum_progress = None

        if dimension_type == models.AnalyticsDimensionType.KINDERGARTEN:
            kg_id = int(dimension_id)
            attendance_rate = KPIService.compute_attendance_rate(db, kg_id, period_start, period_end)
            chronic_absence_rate = KPIService.compute_chronic_absence_rate(db, kg_id, period_start, period_end)
            # compute_incident_rate() now returns per-1,000; divide by 10 to store
            # the correct per-100 value in the incident_rate_per_100 column.
            incident_rate_per_100 = KPIService.compute_incident_rate(db, kg_id, period_start, period_end) / 10.0
            serious_incident_rate = KPIService.compute_serious_incident_rate(db, kg_id, period_start, period_end)
            ratio_compliance_rate = KPIService.compute_ratio_compliance(db, kg_id, period_start, period_end)

            # Daily report completion
            total_reports = db.query(models.DailyReport).join(models.Child).join(
                models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end
            ).count()
            sent_reports = db.query(models.DailyReport).join(models.Child).join(
                models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
                models.DailyReport.status == models.DailyReportStatus.SUBMITTED
            ).count()
            report_completion_rate = (sent_reports / total_reports * 100) if total_reports > 0 else 0

            # Health alerts
            health_alerts_count = db.query(models.HealthAlert).join(models.Child).join(
                models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.HealthAlert.created_at >= period_start,
                models.HealthAlert.created_at <= period_end
            ).count()

            # Attendance trend slope (simple least squares on daily counts)
            daily_attendance = db.query(
                models.AttendanceLog.date,
                func.count(models.AttendanceLog.id)
            ).join(models.Child).join(
                models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()

            if daily_attendance:
                counts = [row[1] for row in daily_attendance]
                n = len(counts)
                if n > 1:
                    x_vals = list(range(n))
                    sum_x = sum(x_vals)
                    sum_y = sum(counts)
                    sum_xy = sum(i * c for i, c in enumerate(counts))
                    sum_xx = sum(i * i for i in x_vals)
                    denominator = (n * sum_xx - sum_x ** 2)
                    attendance_trend_slope = round((n * sum_xy - sum_x * sum_y) / denominator, 3) if denominator else 0.0
                else:
                    attendance_trend_slope = 0.0

            # Heuristic risk score: children with <80% attendance
            active_enrollments = db.query(models.EnrollmentApplication).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).all()
            total_kids = len(active_enrollments)
            if total_kids > 0:
                # Batch-load attendance counts to avoid N+1 queries
                child_ids_for_risk = [e.child_id for e in active_enrollments]
                attendance_counts_by_child = dict(
                    db.query(
                        models.AttendanceLog.child_id,
                        func.count(models.AttendanceLog.id),
                    ).filter(
                        models.AttendanceLog.child_id.in_(child_ids_for_risk),
                        models.AttendanceLog.date >= period_start,
                        models.AttendanceLog.date <= period_end
                    ).group_by(models.AttendanceLog.child_id).all()
                ) if child_ids_for_risk else {}
                days_in_period = (period_end - period_start).days + 1
                at_risk = 0
                for enrollment in active_enrollments:
                    attended_days = attendance_counts_by_child.get(enrollment.child_id, 0)
                    attendance_pct = (attended_days / days_in_period * 100) if days_in_period else 0
                    if attendance_pct < 80:
                        at_risk += 1
                risk_score = round((at_risk / total_kids) * 100, 2)

        cache = models.AdvancedAnalyticsCache(
            dimension_type=dimension_type,
            dimension_id=str(dimension_id),
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            attendance_rate=attendance_rate,
            chronic_absence_rate=chronic_absence_rate,
            incident_rate_per_100=incident_rate_per_100,
            serious_incident_rate=serious_incident_rate,
            ratio_compliance_rate=ratio_compliance_rate,
            report_completion_rate=report_completion_rate,
            parent_satisfaction_nps=parent_satisfaction_nps,
            child_development_index=child_development_index,
            staff_turnover_rate=staff_turnover_rate,
            regulatory_compliance_score=regulatory_compliance_score,
            attendance_trend_slope=attendance_trend_slope,
            risk_score=risk_score,
            improvement_velocity=improvement_velocity,
            attendance_incident_correlation=attendance_incident_correlation,
            staffing_quality_correlation=staffing_quality_correlation,
            health_alerts_count=health_alerts_count,
        )
        db.add(cache)
        db.commit()
        db.refresh(cache)
        return cache

    @staticmethod
    def get_kindergarten_metrics(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> KindergartenMetrics:
        """Get detailed metrics for a specific kindergarten"""
        # Try cache first
        period_days = (period_end - period_start).days + 1
        period_type = models.AnalyticsPeriodType.MONTHLY if period_days > 31 else models.AnalyticsPeriodType.DAILY
        attendance_trend_slope = None
        risk_score = None
        attendance_incident_correlation = None

        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if not kg:
            raise HTTPException(status_code=404, detail="Kindergarten not found")

        cached = AnalyticsService.get_advanced_analytics_cache(
            db,
            models.AnalyticsDimensionType.KINDERGARTEN,
            str(kindergarten_id),
            period_type,
            period_start,
            period_end
        )

        # Get capacity from classes
        kg_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).scalar() or 0

        # Children count
        children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Enrollment rate
        enrollment_rate = (children_count / kg_capacity * 100) if kg_capacity > 0 else 0

        # Attendance / incident: use cache if present
        # incident_rate_per_100 stores per-100; multiply by 10 to expose per-1,000
        # so both cached and live paths return the same scale in KindergartenMetrics.
        if cached:
            attendance_rate = cached.attendance_rate or 0
            incident_rate = (cached.incident_rate_per_100 or 0) * 10.0
            report_submission_rate = cached.report_completion_rate or 0
            attendance_trend_slope = cached.attendance_trend_slope
            risk_score = cached.risk_score
            attendance_incident_correlation = cached.attendance_incident_correlation
        else:
            attendance_rate = KPIService.compute_attendance_rate(
                db, kindergarten_id, period_start, period_end
            )
            incident_rate = KPIService.compute_incident_rate(
                db, kindergarten_id, period_start, period_end
            )

        # Report completion rate
        days_in_period = (period_end - period_start).days + 1
        expected_reports = children_count * days_in_period
        submitted_reports = db.query(func.count(models.DailyReport.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_([
                models.DailyReportStatus.SUBMITTED,
                models.DailyReportStatus.APPROVED
            ])
        ).scalar() or 0

        approved_reports = db.query(func.count(models.DailyReport.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).scalar() or 0

        report_submission_rate = (submitted_reports / expected_reports * 100) if expected_reports > 0 else 0
        report_approval_rate = (approved_reports / submitted_reports * 100) if submitted_reports > 0 else 0
        report_completion_rate = report_submission_rate

        # Ratio compliance
        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )

        # Governance score
        gov_score, gov_band = KPIService.compute_governance_score(
            db, kindergarten_id, period_start, period_end
        )

        # If cache was missing, write it now for future requests
        if not cached:
            try:
                AnalyticsService.compute_advanced_analytics(
                    db,
                    models.AnalyticsDimensionType.KINDERGARTEN,
                    str(kindergarten_id),
                    period_type,
                    period_start,
                    period_end
                )
            except SQLAlchemyError:
                logger.exception("Failed to cache advanced analytics due to database error")
            except (TypeError, ValueError):
                logger.exception("Failed to cache advanced analytics due to invalid analytics data")

        return KindergartenMetrics(
            id=kg.id,
            name=kg.name_ar,
            governorate=kg.governorate or "",
            children_count=children_count,
            capacity=kg_capacity,
            enrollment_rate=round(enrollment_rate, 2),
            attendance_rate=attendance_rate,
            incident_rate=incident_rate,
            report_submission_rate=round(report_submission_rate, 2),
            report_approval_rate=round(report_approval_rate, 2),
            report_completion_rate=round(report_completion_rate, 2),
            ratio_compliance=ratio_compliance,
            governance_score=gov_score,
            governance_band=gov_band,
            attendance_trend_slope=attendance_trend_slope if cached else None,
            risk_score=risk_score if cached else None,
            attendance_incident_correlation=attendance_incident_correlation if cached else None
        )

    @staticmethod
    def get_rankings(
        db: Session,
        metric: str,
        period_start: date,
        period_end: date,
        top_n: int = 10,
        bottom: bool = False,
        kg_filter: Optional[List[int]] = None
    ) -> List[RankingEntry]:
        """Get top/bottom kindergartens by a specific metric"""
        # Get all active kindergartens
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        )
        if kg_filter:
            kindergartens = kindergartens.filter(models.Kindergarten.id.in_(kg_filter))
        kindergartens = kindergartens.all()

        rankings = []
        for kg in kindergartens:
            band = None
            if metric == "attendance_rate":
                value = KPIService.compute_attendance_rate(db, kg.id, period_start, period_end)
            elif metric == "incident_rate":
                value = KPIService.compute_incident_rate(db, kg.id, period_start, period_end)
            elif metric == "ratio_compliance":
                value = KPIService.compute_ratio_compliance(db, kg.id, period_start, period_end)
            elif metric == "governance_score":
                value, band = KPIService.compute_governance_score(db, kg.id, period_start, period_end)
            else:
                value = 0

            rankings.append({
                "kindergarten_id": kg.id,
                "kindergarten_name": kg.name_ar,
                "governorate": kg.governorate or "",
                "value": value,
                "band": band
            })

        # Sort
        reverse = not bottom  # For most metrics, higher is better
        if metric == "incident_rate":
            reverse = bottom  # For incidents, lower is better

        rankings.sort(key=lambda x: x["value"], reverse=reverse)

        # Return top N with ranks
        results = []
        for i, r in enumerate(rankings[:top_n]):
            results.append(RankingEntry(
                rank=i + 1,
                kindergarten_id=r["kindergarten_id"],
                kindergarten_name=r["kindergarten_name"],
                governorate=r["governorate"],
                value=r["value"],
                band=r["band"]
            ))

        return results

    @staticmethod
    def get_kindergarten_trend(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date,
        metric: str
    ) -> List[Dict[str, Any]]:
        points = []
        current = period_start
        while current <= period_end:
            day_end = current
            if metric == "attendance":
                value = KPIService.compute_attendance_rate(db, kindergarten_id, current, day_end)
            else:
                value = KPIService.compute_incident_rate(db, kindergarten_id, current, day_end)
            points.append({"date": current.isoformat(), "value": value})
            current += timedelta(days=1)
        return points

    @staticmethod
    def get_class_metrics(db: Session, class_id: int, period_start: date, period_end: date) -> Dict[str, Any]:
        class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
        if not class_obj:
            raise HTTPException(status_code=404, detail="Class not found")

        total_logs = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.class_id == class_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).scalar() or 0
        present_logs = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.class_id == class_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT
        ).scalar() or 0
        attendance_rate = (present_logs / total_logs * 100) if total_logs else 0.0

        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.class_id == class_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.class_id == class_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        return {
            "class_id": class_id,
            "class_name": class_obj.name_ar,
            "children_count": children_count,
            "attendance_rate": round(attendance_rate, 2),
            "incident_count": incident_count,
        }

    @staticmethod
    def get_child_metrics(db: Session, child_id: int, period_start: date, period_end: date) -> Dict[str, Any]:
        child = db.query(models.Child).filter(models.Child.id == child_id).first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")

        total_logs = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id == child_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).scalar() or 0
        present_logs = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id == child_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT
        ).scalar() or 0
        attendance_rate = (present_logs / total_logs * 100) if total_logs else 0.0

        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.child_id == child_id,
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        return {
            "child_id": child_id,
            "child_name": f"{child.first_name} {child.last_name}",
            "attendance_rate": round(attendance_rate, 2),
            "incident_count": incident_count,
        }

    @staticmethod
    def get_class_trend(db: Session, class_id: int, period_start: date, period_end: date) -> List[Dict[str, Any]]:
        points = []
        current = period_start
        while current <= period_end:
            total_logs = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.class_id == class_id,
                models.AttendanceLog.date == current
            ).scalar() or 0
            present_logs = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.class_id == class_id,
                models.AttendanceLog.date == current,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT
            ).scalar() or 0
            attendance_rate = (present_logs / total_logs * 100) if total_logs else 0.0
            points.append({"date": current.isoformat(), "value": round(attendance_rate, 2)})
            current += timedelta(days=1)
        return points

    @staticmethod
    def get_child_trend(db: Session, child_id: int, period_start: date, period_end: date) -> List[Dict[str, Any]]:
        points = []
        current = period_start
        while current <= period_end:
            total_logs = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.child_id == child_id,
                models.AttendanceLog.date == current
            ).scalar() or 0
            present_logs = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.child_id == child_id,
                models.AttendanceLog.date == current,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT
            ).scalar() or 0
            attendance_rate = (present_logs / total_logs * 100) if total_logs else 0.0
            points.append({"date": current.isoformat(), "value": round(attendance_rate, 2)})
            current += timedelta(days=1)
        return points

    @staticmethod
    def evaluate_thresholds(db: Session) -> None:
        today = _jordan_today()
        thresholds = db.query(models.AlertThreshold).filter(models.AlertThreshold.is_active == True).all()
        for threshold in thresholds:
            window_start = today - timedelta(days=threshold.window_days)
            current_value = AnalyticsService._metric_value_for_scope(
                db,
                threshold.metric_type,
                threshold.scope_type,
                threshold.scope_id,
                window_start,
                today
            )
            comparator = threshold.operator
            triggered = False
            if comparator == models.AlertOperator.GT:
                triggered = current_value > threshold.threshold_value
            elif comparator == models.AlertOperator.GTE:
                triggered = current_value >= threshold.threshold_value
            elif comparator == models.AlertOperator.LT:
                triggered = current_value < threshold.threshold_value
            elif comparator == models.AlertOperator.LTE:
                triggered = current_value <= threshold.threshold_value

            existing = db.query(models.ActiveAlert).filter(
                models.ActiveAlert.threshold_id == threshold.id,
                models.ActiveAlert.status == models.AlertStatus.ACTIVE
            ).first()
            if triggered:
                message = f"Threshold breached for {threshold.metric_type}"
                if existing:
                    existing.current_value = current_value
                    existing.message = message
                    existing.severity = threshold.severity
                    db.commit()
                else:
                    alert = models.ActiveAlert(
                        threshold_id=threshold.id,
                        metric_type=threshold.metric_type,
                        scope_type=threshold.scope_type,
                        scope_id=threshold.scope_id,
                        current_value=current_value,
                        message=message,
                        severity=threshold.severity,
                        status=models.AlertStatus.ACTIVE,
                        triggered_at=_utcnow_naive(),
                    )
                    db.add(alert)
                    db.commit()
            else:
                if existing:
                    existing.status = models.AlertStatus.RESOLVED
                    db.commit()

    @staticmethod
    def _metric_value_for_scope(
        db: Session,
        metric_type: str,
        scope_type: str,
        scope_id: Optional[str],
        period_start: date,
        period_end: date
    ) -> float:
        if metric_type == "attendance_rate":
            if scope_type == "NETWORK":
                return AnalyticsService._compute_network_attendance_rate(db, period_start, period_end)
            if scope_type == "GOVERNORATE" and scope_id:
                return AnalyticsService._compute_governorate_attendance_rate(db, scope_id, period_start, period_end)
            if scope_type == "KINDERGARTEN" and scope_id:
                return KPIService.compute_attendance_rate(db, int(scope_id), period_start, period_end)
            if scope_type == "CLASS" and scope_id:
                return AnalyticsService.get_class_metrics(db, int(scope_id), period_start, period_end)["attendance_rate"]
            if scope_type == "CHILD" and scope_id:
                return AnalyticsService.get_child_metrics(db, int(scope_id), period_start, period_end)["attendance_rate"]
        if metric_type == "incident_rate":
            if scope_type == "NETWORK":
                return AnalyticsService._compute_network_incident_rate(db, period_start, period_end)
            if scope_type == "GOVERNORATE" and scope_id:
                return AnalyticsService._compute_governorate_incident_rate(db, scope_id, period_start, period_end)
            if scope_type == "KINDERGARTEN" and scope_id:
                return KPIService.compute_incident_rate(db, int(scope_id), period_start, period_end)
        if metric_type == "enrollment_rate":
            if scope_type == "KINDERGARTEN" and scope_id:
                return AnalyticsService.get_kindergarten_metrics(db, int(scope_id), period_start, period_end).enrollment_rate
        return 0.0

    @staticmethod
    def generate_recommendations_for_kindergarten(db: Session, kindergarten_id: int, user_id: int) -> None:
        today = _jordan_today()
        recent = db.query(models.Recommendation).filter(
            models.Recommendation.kindergarten_id == kindergarten_id,
            models.Recommendation.created_at >= _utcnow_naive() - timedelta(days=30)
        ).first()
        if recent:
            return

        period_start = today - timedelta(days=30)
        period_end = today
        attendance_rate = KPIService.compute_attendance_rate(db, kindergarten_id, period_start, period_end)
        incident_rate = KPIService.compute_incident_rate(db, kindergarten_id, period_start, period_end)

        if attendance_rate < 85:
            db.add(models.Recommendation(
                kindergarten_id=kindergarten_id,
                scope_type="KINDERGARTEN",
                scope_id=str(kindergarten_id),
                metric_type="attendance_rate",
                title="رفع نسبة الحضور",
                description="نسبة الحضور أقل من الحد المستهدف. يُنصح بتفعيل التواصل مع أولياء الأمور ومتابعة الحالات المتكررة.",
                severity=models.SeverityLevel.MEDIUM,
                recommended_actions=["التواصل مع أولياء الأمور", "تحليل أسباب الغياب", "خطة متابعة أسبوعية"],
                created_by=user_id,
            ))
        if incident_rate > 2:
            db.add(models.Recommendation(
                kindergarten_id=kindergarten_id,
                scope_type="KINDERGARTEN",
                scope_id=str(kindergarten_id),
                metric_type="incident_rate",
                title="خفض معدل الحوادث",
                description="معدل الحوادث أعلى من المتوسط. يُنصح بمراجعة إجراءات السلامة وتعزيز التدريب.",
                severity=models.SeverityLevel.HIGH,
                recommended_actions=["تدريب إضافي للطاقم", "مراجعة إجراءات السلامة", "مراقبة مناطق الخطر"],
                created_by=user_id,
            ))
        db.commit()

    @staticmethod
    def evaluate_data_quality(db: Session, user_id: int) -> None:
        latest = db.query(models.DataQualityMetric).order_by(models.DataQualityMetric.evaluated_at.desc()).first()
        if latest and latest.evaluated_at >= _utcnow_naive() - timedelta(hours=12):
            return

        total_kgs = db.query(func.count(models.Kindergarten.id)).scalar() or 0
        complete_kgs = db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.name_ar.isnot(None),
            models.Kindergarten.governorate.isnot(None),
            models.Kindergarten.district.isnot(None),
            models.Kindergarten.area.isnot(None),
            models.Kindergarten.address_line.isnot(None),
            models.Kindergarten.contact_phone.isnot(None)
        ).scalar() or 0
        kg_completeness = (complete_kgs / total_kgs * 100) if total_kgs else 100.0

        total_children = db.query(func.count(models.Child.id)).scalar() or 0
        complete_children = db.query(func.count(models.Child.id)).filter(
            models.Child.first_name.isnot(None),
            models.Child.last_name.isnot(None),
            models.Child.date_of_birth.isnot(None),
            models.Child.gender.isnot(None)
        ).scalar() or 0
        child_completeness = (complete_children / total_children * 100) if total_children else 100.0

        completeness_percent = round((kg_completeness + child_completeness) / 2, 2)
        accuracy_score = round(min(100.0, completeness_percent + 5.0), 2)
        timeliness_score = 90.0
        consistency_score = round(min(100.0, completeness_percent + 3.0), 2)

        metric = models.DataQualityMetric(
            entity_type="NETWORK",
            entity_id=None,
            completeness_percent=completeness_percent,
            accuracy_score=accuracy_score,
            timeliness_score=timeliness_score,
            consistency_score=consistency_score,
            evaluated_at=_utcnow_naive(),
            details={
                "kindergarten_completeness": kg_completeness,
                "child_completeness": child_completeness,
                "total_kindergartens": total_kgs,
                "total_children": total_children,
            },
        )
        db.add(metric)
        db.commit()


# ============================================================================
# New admin-only analytics endpoints
# ============================================================================

@router.get("/attendance/by-class")
def get_attendance_by_class(
    kindergarten_id: int = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Attendance breakdown by class for a kindergarten (admin only)"""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)
    total_days = (period_end - period_start).days + 1

    classes = db.query(models.Class).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active == True
    ).all()

    result = []
    for cls in classes:
        enrolled = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.class_id == cls.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0
        expected = enrolled * total_days
        attended = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.class_id == cls.id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT
        ).scalar() or 0
        attendance_rate = round((attended / expected) * 100, 2) if expected > 0 else 0.0
        result.append({
            "class_id": cls.id,
            "class_name": cls.name_ar or cls.name_en,
            "attendance_rate": attendance_rate,
            "enrolled_count": enrolled,
        })

    return {"classes": result}


@router.get("/attendance/chronic-absence")
def get_chronic_absence(
    threshold_pct: float = Query(80.0),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Children with attendance rate below threshold (admin only)"""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)
    total_days = max((period_end - period_start).days + 1, 1)

    enrollment_q = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )
    if kindergarten_id:
        enrollment_q = enrollment_q.filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        )
    enrollments = enrollment_q.all()

    chronic_children = []
    for enrollment in enrollments:
        attended = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id == enrollment.child_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT
        ).scalar() or 0
        attendance_rate = round((attended / total_days) * 100, 2)
        if attendance_rate < threshold_pct:
            child = enrollment.child
            chronic_children.append({
                "child_id": enrollment.child_id,
                "child_name": f"{child.first_name} {child.last_name}" if child else str(enrollment.child_id),
                "attendance_rate": attendance_rate,
                "kindergarten_id": enrollment.kindergarten_id,
            })

    return {
        "chronically_absent_children": chronic_children,
        "count": len(chronic_children),
        "threshold_pct": threshold_pct,
    }


@router.get("/attendance/by-governorate")
def get_attendance_by_governorate(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Attendance breakdown by governorate (admin only)"""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)

    governorates = db.query(models.Kindergarten.governorate).filter(
        models.Kindergarten.governorate.isnot(None),
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).distinct().all()

    result = []
    for (gov,) in governorates:
        kg_ids = [k.id for k in db.query(models.Kindergarten).filter(
            models.Kindergarten.governorate == gov,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()]
        if not kg_ids:
            continue
        total_days = max((period_end - period_start).days + 1, 1)
        enrolled = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0
        expected_total = enrolled * total_days
        attended = db.query(func.count(models.AttendanceLog.id)).join(
            models.Class, models.Class.id == models.AttendanceLog.class_id
        ).filter(
            models.Class.kindergarten_id.in_(kg_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT
        ).scalar() or 0
        attendance_rate = round((attended / expected_total) * 100, 2) if expected_total > 0 else 0.0
        result.append({
            "governorate": gov,
            "attendance_rate": attendance_rate,
            "kindergarten_count": len(kg_ids),
        })

    return {"governorates": result}


@router.get("/daily-reports/supervisor-performance")
def get_supervisor_performance(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Supervisor daily report submission performance (admin only)"""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)

    report_q = db.query(models.DailyReport).filter(
        models.DailyReport.date >= period_start,
        models.DailyReport.date <= period_end,
        models.DailyReport.submitted_by.isnot(None)
    )
    if kindergarten_id:
        report_q = report_q.filter(models.DailyReport.kindergarten_id == kindergarten_id)
    reports = report_q.all()

    by_supervisor: dict = {}
    for report in reports:
        sid = report.submitted_by
        if sid not in by_supervisor:
            by_supervisor[sid] = {"total": 0, "submitted": 0}
        by_supervisor[sid]["total"] += 1
        if report.status != models.DailyReportStatus.DRAFT:
            by_supervisor[sid]["submitted"] += 1

    supervisors = []
    for sid, counts in by_supervisor.items():
        total = counts["total"]
        submitted = counts["submitted"]
        completion_rate = round((submitted / total) * 100, 2) if total > 0 else 0.0
        supervisors.append({
            "supervisor_id": sid,
            "total_reports": total,
            "submitted_reports": submitted,
            "completion_rate": completion_rate,
        })

    return {"supervisors": supervisors}


@router.get("/enrollment/trends")
def get_enrollment_trends(
    granularity: str = Query(..., pattern="^(weekly|monthly)$"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enrollment trends over time (admin only). granularity: 'weekly' or 'monthly'."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)

    enrollment_q = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.created_at.isnot(None),
    )
    if kindergarten_id:
        enrollment_q = enrollment_q.filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        )
    enrollments = enrollment_q.all()

    periods: dict = {}
    for enrollment in enrollments:
        created = enrollment.created_at
        if created is None:
            continue
        created_date = created.date() if hasattr(created, 'date') else created
        if created_date < period_start or created_date > period_end:
            continue
        if granularity == "weekly":
            monday = created_date - timedelta(days=created_date.weekday())
            period_key = monday.isoformat()
        else:
            period_key = f"{created_date.year}-{created_date.month:02d}-01"
        periods[period_key] = periods.get(period_key, 0) + 1

    sorted_periods = sorted(periods.items())
    trends = []
    cumulative = 0
    for period_key, count in sorted_periods:
        cumulative += count
        trends.append({
            "period": period_key,
            "new_applications": count,
            "cumulative": cumulative,
        })

    return {"trends": trends, "granularity": granularity}
