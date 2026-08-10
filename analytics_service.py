"""
Analytics and Reporting Services for Admin Dashboard
Implements drill-down analytics from Network → Governorate → Kindergarten → Class → Child
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks, Response, Request
from fastapi import Path as FastAPIPath
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from enum import Enum
import os
import hashlib
import secrets
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
from services.jordan_locations import governorate_filter
from kpi_service import KPIService
from data_quality_enhanced import enhanced_data_quality_service
import validators
from audit_actions import AuditAction
from admin_security import log_audit_event, validation_error
from cache_service import cache_service
from config import settings
from utils.time_utils import jordan_date_range_filter, jordan_day_bounds, to_jordan_date
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
    can_view_child_detail,
    enforce_analytics_rbac as _enforce_analytics_rbac,
    enforce_kindergarten_scope,
    get_date_range,
    kg_ids_for_governorate as _kg_ids_for_governorate,
)

logger = logging.getLogger(__name__)


def _validate_csrf_token(request: Request) -> None:
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
        raise validation_error("Invalid CSRF token", fields={"csrf_token": "invalid"})


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

_DASHBOARD_CACHE_TTL = 60  # seconds


def _analytics_cache_get(key: str):
    if getattr(settings, "TESTING", False):
        return None
    try:
        return cache_service.get(key)
    except Exception:
        return None


def _analytics_cache_set(key: str, value: Any, ttl: int = _DASHBOARD_CACHE_TTL) -> None:
    if getattr(settings, "TESTING", False):
        return
    try:
        cache_service.set(key, value, ttl_seconds=ttl)
    except Exception:
        pass


def _kg_ids_cache_token(kg_ids: Optional[List[int]]) -> str:
    if not kg_ids:
        return "all"
    return hashlib.md5(",".join(map(str, sorted(kg_ids))).encode()).hexdigest()[:12]


def _cached_network_summary(db, period_start, period_end, kg_ids):
    """Cache-backed get_network_summary. Keyed on the explicit (Jordan) period +
    scope, so it never uses date.today()/UTC. Collapses the redundant recomputes
    that insights / action-queue / target-progress otherwise trigger per load."""
    key = (
        f"analytics:netsum:{period_start.isoformat()}:{period_end.isoformat()}:"
        f"{_kg_ids_cache_token(kg_ids)}"
    )
    cached = _analytics_cache_get(key)
    if cached is not None:
        return NetworkSummary.model_validate(cached)
    summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_ids)
    _analytics_cache_set(key, summary.model_dump(mode="json"))
    return summary


def _cached_governorate_breakdown(db, period_start, period_end, governorate, allowed_kgs, extra=None):
    key = (
        f"analytics:govbrk:{period_start.isoformat()}:{period_end.isoformat()}:"
        f"{governorate or 'all'}:{_kg_ids_cache_token(allowed_kgs)}"
    )
    cached = _analytics_cache_get(key)
    if cached is not None:
        return [GovernorateMetrics.model_validate(item) for item in cached]
    breakdown = AnalyticsService.get_governorate_breakdown(
        db, period_start, period_end, governorate, allowed_kgs, extra
    )
    _analytics_cache_set(key, [b.model_dump(mode="json") for b in breakdown])
    return breakdown


class InsightEngine:
    """Generate actionable insights from analytics data"""

    @staticmethod
    def generate_insights(network_summary: dict, governorate_breakdown: list) -> list:
        insights = []

        attendance_rate = network_summary.get('attendance_rate', 100)
        if attendance_rate < 70:
            insights.append({
                'type': 'ATTENDANCE_CRITICAL',
                'severity': 'HIGH',
                'icon': 'bi-exclamation-triangle-fill',
                'message_ar': f'معدل الحضور منخفض جدًا ({attendance_rate:.1f}%)',
                'message_en': f'Attendance rate critically low ({attendance_rate:.1f}%)',
                'action_ar': 'مراجعة سجلات الحضور والتواصل مع مديري الحضانات',
                'action_en': 'Review attendance records and contact kindergarten managers',
                'affected_count': len([g for g in governorate_breakdown if g.get('attendance_rate', 100) < 70]),
                'link': '/admin/analytics?tab=overview#attendance'
            })
        elif attendance_rate < 80:
            insights.append({
                'type': 'ATTENDANCE_WARNING',
                'severity': 'MEDIUM',
                'icon': 'bi-exclamation-circle-fill',
                'message_ar': f'معدل الحضور منخفض ({attendance_rate:.1f}%)',
                'message_en': f'Attendance rate below target ({attendance_rate:.1f}%)',
                'action_ar': 'مراجعة اتجاهات الحضور وتحديد الحضانات المتأثرة',
                'action_en': 'Review attendance trends and identify affected kindergartens',
                'affected_count': len([g for g in governorate_breakdown if g.get('attendance_rate', 100) < 80]),
                'link': '/admin/analytics?tab=overview#attendance'
            })

        incident_rate = network_summary.get('incident_rate', 0)
        if incident_rate > 10:
            insights.append({
                'type': 'INCIDENT_CRITICAL',
                'severity': 'HIGH',
                'icon': 'bi-shield-exclamation',
                'message_ar': f'معدل الحوادث مرتفع ({incident_rate:.1f} لكل 100 طفل)',
                'message_en': f'Incident rate elevated ({incident_rate:.1f} per 100 children)',
                'action_ar': 'مراجعة الحوادث الأخيرة ومراجعة بروتوكولات السلامة',
                'action_en': 'Investigate recent incidents and review safety protocols',
                'affected_count': len([g for g in governorate_breakdown if g.get('incident_rate', 0) > 10]),
                'link': '/admin/analytics?tab=overview#incidents'
            })
        elif incident_rate > 5:
            insights.append({
                'type': 'INCIDENT_WARNING',
                'severity': 'MEDIUM',
                'icon': 'bi-shield-exclamation',
                'message_ar': f'معدل الحوادث فوق الطبيعي ({incident_rate:.1f} لكل 100 طفل)',
                'message_en': f'Incident rate above normal ({incident_rate:.1f} per 100 children)',
                'action_ar': 'مراجعة تقارير الحوادث وتحديد الأنماط',
                'action_en': 'Review incident reports and identify patterns',
                'affected_count': len([g for g in governorate_breakdown if g.get('incident_rate', 0) > 5]),
                'link': '/admin/analytics?tab=overview#incidents'
            })

        governance_score = network_summary.get('governance_avg_score', 100)
        if governance_score < 60:
            insights.append({
                'type': 'GOVERNANCE_CRITICAL',
                'severity': 'HIGH',
                'icon': 'bi-clipboard-x-fill',
                'message_ar': f'متوسط درجة الحوكمة منخفض ({governance_score:.1f}%)',
                'message_en': f'Governance score critically low ({governance_score:.1f}%)',
                'action_ar': 'مراجعة تقييمات الحوكمة ووضع خطط تحسين',
                'action_en': 'Review governance assessments and create improvement plans',
                'affected_count': len([g for g in governorate_breakdown if g.get('governance_score', 100) < 60]),
                'link': '/admin/analytics?tab=governance'
            })

        severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        insights.sort(key=lambda x: severity_order.get(x['severity'], 3))

        return insights[:5]


def log_data_anomaly(field: str, value: Any, expected_range: str = None):
    """Log data integrity anomalies"""
    msg = f"Data anomaly detected: {field}={value}"
    if expected_range:
        msg += f" (expected: {expected_range})"
    logger.warning(msg)


def validate_dashboard_data(data: dict) -> dict:
    """Validate data integrity before serving to frontend"""
    validated = data.copy()

    for key in ['total_kindergartens', 'total_children', 'total_incidents']:
        if key in validated:
            val = validated[key]
            if val is None or val < 0:
                log_data_anomaly(key, val, ">= 0")
                validated[key] = max(0, val or 0)

    for key in ['attendance_rate', 'incident_rate', 'enrollment_rate']:
        if key in validated:
            val = validated[key]
            if val is not None and not (0 <= val <= 100):
                log_data_anomaly(key, val, "0-100")
                validated[key] = max(0, min(100, val))

    # (Removed a dead attendance_trend/incident_trend chronological check:
    # NetworkSummary carries no such keys, and post-model_dump items are dicts
    # with no .date attribute, so the branch never ran and would have errored.)
    return validated


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
        {"id": "org.kindergarten", "label_ar": "الحضانة", "label_en": "Kindergarten", "allowed_filters": ["eq", "in"], "drill_targets": ["org.class"]},
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
    request: Request = None,
):
    _validate_csrf_token(request)
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


@router.get("/model-performance")
def get_model_performance(
    metric: str = Query(..., pattern="^(attendance|incidents|enrollment)$"),
    days_back: int = Query(30, ge=7, le=180),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate forecast model accuracy by comparing predictions vs actuals."""
    _ensure_admin_only(current_user)

    today = _jordan_today()
    evaluation_start = today - timedelta(days=days_back)

    past_predictions = db.query(models.PredictionCache).filter(
        models.PredictionCache.metric_type == metric,
        models.PredictionCache.scope_type == "NETWORK",
        models.PredictionCache.created_at >= evaluation_start,
    ).order_by(models.PredictionCache.created_at.desc()).limit(10).all()

    if not past_predictions:
        return {
            "metric": metric,
            "accuracy": None,
            "mape": None,
            "evaluations": 0,
            "trend": "insufficient_data",
            "message_ar": "لا توجد بيانات كافية لتقييم الأداء",
            "message_en": "Insufficient data for performance evaluation",
        }

    evaluations = []
    total_error = 0
    eval_count = 0

    # Batch every actual for the window in one grouped query (was an N+1:
    # 2 non-sargable COUNTs per forecast point across up to 10 predictions).
    actuals = _actual_values_for_window(db, metric, evaluation_start, today)

    for prediction in past_predictions:
        forecast_points = prediction.forecast_points
        if isinstance(forecast_points, str):
            forecast_points = json.loads(forecast_points)

        for fp in forecast_points:
            forecast_date = fp["date"] if isinstance(fp, dict) else fp.date
            if isinstance(forecast_date, str):
                forecast_date = date.fromisoformat(forecast_date)

            if forecast_date >= today:
                continue

            predicted_value = fp["value"] if isinstance(fp, dict) else fp.value
            actual_value = actuals.get(forecast_date)

            if actual_value is not None:
                error = abs(predicted_value - actual_value)
                percentage_error = (error / actual_value * 100) if actual_value != 0 else 0

                evaluations.append(
                    {
                        "date": forecast_date.isoformat(),
                        "predicted": predicted_value,
                        "actual": actual_value,
                        "error": round(error, 2),
                        "percentage_error": round(percentage_error, 2),
                    }
                )

                total_error += percentage_error
                eval_count += 1

    if eval_count == 0:
        return {
            "metric": metric,
            "accuracy": None,
            "mape": None,
            "evaluations": 0,
            "trend": "insufficient_data",
            "message_ar": "لا توجد تنبؤات منتهية الصلاحية للتقييم",
            "message_en": "No expired predictions to evaluate",
        }

    mape = total_error / eval_count
    accuracy = 100 - mape

    # Order chronologically so "recent" is really the later half — evaluations
    # were appended in prediction-desc order, not by date.
    evaluations.sort(key=lambda e: e["date"])
    half = len(evaluations) // 2
    older_evals = evaluations[:half] or evaluations
    recent_evals = evaluations[half:] or evaluations

    recent_mape = sum(e["percentage_error"] for e in recent_evals) / len(recent_evals) if recent_evals else mape
    older_mape = sum(e["percentage_error"] for e in older_evals) / len(older_evals) if older_evals else mape

    if recent_mape < older_mape * 0.9:
        trend = "improving"
    elif recent_mape > older_mape * 1.1:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "metric": metric,
        "accuracy": round(accuracy, 2),
        "mape": round(mape, 2),
        "evaluations": eval_count,
        "trend": trend,
        "recent_evaluations": evaluations[-5:],
    }


def _actual_values_for_window(db: Session, metric: str, start: date, end: date) -> Dict[date, float]:
    """Batched {date: actual_value} for the whole [start, end] window in one grouped
    query per metric. Same definitions as the former per-date _get_actual_value, but
    avoids the N+1 (2 COUNTs per forecast point) and the non-sargable
    func.date(col) == filters — the WHERE uses half-open ranges on the raw column."""
    result: Dict[date, float] = {}
    try:
        if metric == "attendance":
            rows = (
                db.query(
                    models.AttendanceLog.date,
                    func.count(models.AttendanceLog.id),
                    func.sum(case((models.AttendanceLog.status == models.AttendanceStatus.PRESENT, 1), else_=0)),
                )
                .filter(models.AttendanceLog.date >= start, models.AttendanceLog.date <= end)
                .group_by(models.AttendanceLog.date)
                .all()
            )
            for d, total, present in rows:
                if total:
                    result[d] = round((present or 0) / total * 100, 2)
        elif metric in ("incidents", "enrollment"):
            if metric == "incidents":
                col, model_id = models.Incident.occurred_at, models.Incident.id
            else:
                col, model_id = models.EnrollmentApplication.created_at, models.EnrollmentApplication.id
            # Use Jordan-local date bounds to avoid func.date() timezone issues (CHART-013)
            from utils.time_utils import jordan_day_bounds
            start_dt, end_dt = jordan_day_bounds(start)
            _, end_dt_final = jordan_day_bounds(end)
            rows = (
                db.query(func.date(col), func.count(model_id))
                .filter(
                    col >= start_dt,
                    col < end_dt_final,
                )
                .group_by(func.date(col))
                .all()
            )
            for d, c in rows:
                key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
                result[key] = float(c)
        return result
    except Exception as e:
        logger.error(f"Error batching actuals for {metric} [{start}..{end}]: {e}")
        return result


def _metric_target(db: Session, metric_type: str, default: float) -> float:
    """Latest network PerformanceTarget for a metric, else the supplied default."""
    t = (
        db.query(models.PerformanceTarget)
        .filter(
            models.PerformanceTarget.metric_type == metric_type,
            models.PerformanceTarget.scope_type == "NETWORK",
        )
        .order_by(models.PerformanceTarget.effective_date.desc())
        .first()
    )
    return t.target_value if t else default


def _forecast_breach_alert(series, horizon_days, today, threshold, higher_is_better,
                           metric, unit, name_ar, name_en):
    """Forecast a series and, if it is projected to cross `threshold` adversely
    within the horizon, return a bilingual predictive alert (else None)."""
    if not series or len(series) < 5:
        return None
    forecast_points, _bands, meta = build_forecast(series, horizon_days)
    if not forecast_points:
        return None

    def _is_adverse(v):
        return v < threshold if higher_is_better else v > threshold

    breach = next((p for p in forecast_points if _is_adverse(p.value)), None)
    if breach is None:
        return None

    days_out = (breach.date - today).days
    severity = "HIGH" if days_out <= 3 else "MEDIUM" if days_out <= 7 else "LOW"
    dir_ar = "الانخفاض دون" if higher_is_better else "تجاوز"
    dir_en = "fall below" if higher_is_better else "exceed"
    return {
        "metric": metric,
        "severity": severity,
        "breach_date": breach.date.isoformat(),
        "days_until_breach": days_out,
        "predicted_value": round(breach.value, 2),
        "threshold": round(threshold, 2),
        "unit": unit,
        "higher_is_better": higher_is_better,
        "confidence": meta.get("confidence"),
        "icon": "bi-graph-down-arrow" if higher_is_better else "bi-graph-up-arrow",
        "message_ar": (
            f"يُتوقع {dir_ar} {threshold:.1f}{unit} لمؤشر {name_ar} بحلول "
            f"{breach.date.isoformat()} (القيمة المتوقعة {breach.value:.1f}{unit})"
        ),
        "message_en": (
            f"{name_en} is projected to {dir_en} {threshold:.1f}{unit} by "
            f"{breach.date.isoformat()} (predicted {breach.value:.1f}{unit})"
        ),
    }


@router.get("/predictive-alerts")
def get_predictive_alerts(
    horizon_days: int = Query(14, ge=1, le=90),
    lookback_days: int = Query(60, ge=14, le=365),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Forecast key metrics and raise alerts for any projected to breach their
    target/threshold within the horizon. Composes attendance/incident series +
    the ensemble build_forecast + configured PerformanceTargets. Admin-only."""
    _ensure_admin_only(current_user)

    today = _jordan_today()
    start = today - timedelta(days=lookback_days)
    scope_type = "GOVERNORATE" if governorate else "NETWORK"
    scope_id = governorate

    alerts = []

    # Attendance rate (%, higher is better): alert if projected below target.
    att_target = _metric_target(db, "attendance_rate", 85.0)
    att = _forecast_breach_alert(
        attendance_series(db, scope_type, scope_id, start, today),
        horizon_days, today, threshold=att_target, higher_is_better=True,
        metric="attendance", unit="%", name_ar="الحضور", name_en="Attendance",
    )
    if att:
        alerts.append(att)

    # Incidents (daily count, lower is better): alert if projected to spike above
    # 1.5x the recent baseline (floored at 1) — a data-driven, self-scaling threshold.
    inc_series = incident_series(db, scope_type, scope_id, start, today)
    recent = inc_series[-14:]
    inc_baseline = (sum(p.value for p in recent) / len(recent)) if recent else 0.0
    inc = _forecast_breach_alert(
        inc_series, horizon_days, today,
        threshold=max(inc_baseline * 1.5, 1.0), higher_is_better=False,
        metric="incidents", unit="", name_ar="الحوادث", name_en="Incidents",
    )
    if inc:
        alerts.append(inc)

    sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: (sev_order.get(a["severity"], 3), a["breach_date"]))

    return {
        "generated_at": today.isoformat(),
        "horizon_days": horizon_days,
        "governorate": governorate,
        "alerts": alerts,
        "count": len(alerts),
    }


# --- Phase 4 item 3: data lineage / provenance ------------------------------
# (dataset key, table, name_ar, name_en, model, recency column, is-a-Date-not-DateTime)
_LINEAGE_SOURCES = [
    ("attendance", "attendance_logs", "سجلات الحضور", "Attendance logs",
     models.AttendanceLog, "date", True),
    ("incidents", "incidents", "بلاغات الحوادث", "Incident reports",
     models.Incident, "occurred_at", False),
    ("daily_reports", "daily_reports", "التقارير اليومية", "Daily reports",
     models.DailyReport, "date", True),
    ("enrollments", "enrollment_applications", "طلبات التسجيل", "Enrollment applications",
     models.EnrollmentApplication, "created_at", False),
    ("kindergartens", "kindergartens", "الحضانات", "Kindergartens",
     models.Kindergarten, "created_at", False),
    ("children", "children", "الأطفال", "Children",
     models.Child, "created_at", False),
]


def _gov_en(gov: str) -> str:
    """Map a stored (Arabic) governorate name to its English label so English
    output never carries Arabic place names. Falls back to the original value."""
    if not gov:
        return ""
    if gov in settings.JORDAN_GOVERNORATES:
        idx = settings.JORDAN_GOVERNORATES.index(gov)
        if idx < len(settings.JORDAN_GOVERNORATES_ENGLISH):
            return settings.JORDAN_GOVERNORATES_ENGLISH[idx]
    return gov


def _lineage_status(count: int, freshness_days: Optional[int]) -> str:
    if count == 0:
        return "empty"
    if freshness_days is None:
        return "unknown"
    if freshness_days <= 2:
        return "fresh"
    if freshness_days <= 7:
        return "recent"
    return "stale"


@router.get("/data-lineage")
def get_data_lineage(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Provenance panel: for each source feeding the analytics, report row count,
    last-updated date and freshness — so the dashboard's numbers are traceable."""
    _ensure_admin_only(current_user)
    today = _jordan_today()

    sources = []
    for key, table, name_ar, name_en, model, col_name, is_date in _LINEAGE_SOURCES:
        col = getattr(model, col_name)
        count = db.query(func.count(model.id)).scalar() or 0
        latest = db.query(func.max(col)).scalar()
        latest_date = None
        if latest is not None:
            latest_date = latest if (isinstance(latest, date) and not isinstance(latest, datetime)) \
                else (latest.date() if isinstance(latest, datetime) else None)
        freshness_days = (today - latest_date).days if latest_date else None
        sources.append({
            "dataset": key, "table": table, "name_ar": name_ar, "name_en": name_en,
            "record_count": count,
            "last_updated": latest_date.isoformat() if latest_date else None,
            "freshness_days": freshness_days,
            "status": _lineage_status(count, freshness_days),
        })

    operational = [s["freshness_days"] for s in sources
                   if s["dataset"] in ("attendance", "incidents", "daily_reports")
                   and s["freshness_days"] is not None]
    return {
        "generated_at": today.isoformat(),
        "sources": sources,
        "overall_freshness_days": max(operational) if operational else None,
    }


# --- Phase 4 item 4: NLP narrative insights (rule-based NLG) -----------------
@router.get("/narrative-summary")
def get_narrative_summary(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Auto-generated bilingual executive narrative — plain-language sentences
    composed deterministically from the computed network + governorate metrics."""
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

    ns = _cached_network_summary(db, period_start, period_end, kg_filter)
    breakdown = _cached_governorate_breakdown(db, period_start, period_end, governorate, allowed_kgs, None)

    sentences = []

    # 1. Scale
    sentences.append({
        "tone": "neutral", "icon": "bi-diagram-3",
        "ar": f"تغطي الشبكة {ns.total_kindergartens} حضانة و{ns.total_children} طفلاً في الفترة المحددة.",
        "en": f"The network covers {ns.total_kindergartens} kindergartens and {ns.total_children} children in the selected period.",
    })

    # 2. Attendance assessment
    att = ns.attendance_rate or 0
    if att >= 90:
        tone, ar_q, en_q = "positive", "قوي", "strong"
    elif att >= 80:
        tone, ar_q, en_q = "neutral", "ضمن المستوى المقبول", "within an acceptable range"
    elif att >= 70:
        tone, ar_q, en_q = "warning", "دون المستهدف", "below target"
    else:
        tone, ar_q, en_q = "negative", "منخفض بشكل حرج", "critically low"
    sentences.append({
        "tone": tone, "icon": "bi-person-check",
        "ar": f"متوسط الحضور {att:.1f}% وهو {ar_q}.",
        "en": f"Average attendance is {att:.1f}%, which is {en_q}.",
    })

    # 3. Governorates below the 80% attendance line
    below = [g for g in breakdown if (getattr(g, "attendance_rate", 100) or 100) < 80]
    if breakdown:
        if below:
            names = "، ".join(g.governorate for g in below[:3])
            names_en = ", ".join(_gov_en(g.governorate) for g in below[:3])
            sentences.append({
                "tone": "warning", "icon": "bi-geo-alt",
                "ar": f"{len(below)} من {len(breakdown)} محافظة دون خط الحضور 80% (أبرزها: {names}).",
                "en": f"{len(below)} of {len(breakdown)} governorates are below the 80% attendance line (notably: {names_en}).",
            })
        else:
            sentences.append({
                "tone": "positive", "icon": "bi-geo-alt",
                "ar": "جميع المحافظات عند خط الحضور 80% أو أعلى.",
                "en": "All governorates are at or above the 80% attendance line.",
            })

    # 4. Incidents
    inc = ns.incident_rate or 0
    sentences.append({
        "tone": "negative" if inc > 10 else "warning" if inc > 5 else "neutral",
        "icon": "bi-shield-exclamation",
        "ar": f"معدل الحوادث {inc:.1f} لكل 1000 طفل.",
        "en": f"The incident rate is {inc:.1f} per 1,000 children.",
    })

    # 5. Governance
    gov = ns.governance_avg_score or 0
    sentences.append({
        "tone": "positive" if gov >= 80 else "warning" if gov >= 60 else "negative",
        "icon": "bi-clipboard-check",
        "ar": f"متوسط درجة الحوكمة {gov:.1f}%.",
        "en": f"The average governance score is {gov:.1f}%.",
    })

    return {
        "generated_at": _jordan_today().isoformat(),
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "governorate": governorate,
        "narrative_ar": " ".join(s["ar"] for s in sentences),
        "narrative_en": " ".join(s["en"] for s in sentences),
        "sentences": sentences,
    }


@router.get("/scenarios")
def get_scenarios(
    metric: str = Query(..., pattern="^(attendance|incidents|enrollment)$"),
    horizon_days: int = Query(30, ge=1, le=180),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate forecast scenarios (optimistic, pessimistic, etc.)."""
    _ensure_admin_only(current_user)

    scope_type = "NETWORK"
    scope_id = None

    if metric == "attendance":
        series = attendance_series(db, scope_type, scope_id, period_start, period_end)
    elif metric == "incidents":
        series = incident_series(db, scope_type, scope_id, period_start, period_end)
    else:
        series = enrollment_series(db, scope_type, scope_id, period_start, period_end)

    if not series:
        return {"scenarios": {}, "metric": metric}

    forecast_points, confidence, model_meta = build_forecast(series, horizon_days)

    if not forecast_points:
        return {"scenarios": {}, "metric": metric}

    values = [p.value for p in series]
    mean_val = sum(values) / len(values)
    variance = sum((v - mean_val) ** 2 for v in values) / max(len(values) - 1, 1)
    stddev = variance ** 0.5 or 1.0

    scenarios = {}

    scenarios['baseline'] = [
        {"date": p.date.isoformat(), "value": p.value}
        for p in forecast_points
    ]

    scenarios['optimistic'] = [
        {"date": p.date.isoformat(), "value": round(max(0.0, p.value + stddev), 2)}
        for p in forecast_points
    ]

    scenarios['pessimistic'] = [
        {"date": p.date.isoformat(), "value": round(max(0.0, p.value - stddev), 2)}
        for p in forecast_points
    ]

    scenarios['best_case'] = [
        {"date": p.date.isoformat(), "value": round(max(0.0, p.value + 2 * stddev), 2)}
        for p in forecast_points
    ]

    scenarios['worst_case'] = [
        {"date": p.date.isoformat(), "value": round(max(0.0, p.value - 2 * stddev), 2)}
        for p in forecast_points
    ]

    return {
        "metric": metric,
        "horizon_days": horizon_days,
        "stddev": round(stddev, 2),
        "scenarios": scenarios,
        "historical": [
            {"date": p.date.isoformat(), "value": p.value}
            for p in series[-30:]
        ]
    }


@router.get("/what-if")
def get_what_if(
    metric: str = Query(..., pattern="^(attendance|incidents|enrollment)$"),
    adjustment_percent: float = Query(0.0, ge=-50, le=100),
    horizon_days: int = Query(30, ge=1, le=180),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Interactive what-if: apply a ramped adjustment to a forecast."""
    _ensure_admin_only(current_user)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must be <= period_end")
    if metric == "attendance":
        series = attendance_series(db, "NETWORK", None, period_start, period_end)
    elif metric == "incidents":
        series = incident_series(db, "NETWORK", None, period_start, period_end)
    else:
        series = enrollment_series(db, "NETWORK", None, period_start, period_end)
    forecast_points, _confidence, _meta = build_forecast(series, horizon_days)
    if not forecast_points:
        return {"metric": metric, "adjustment_percent": adjustment_percent,
                "horizon_days": horizon_days, "baseline": [], "adjusted": [], "summary": {}}
    n = len(forecast_points)
    baseline = [{"date": p.date.isoformat(), "value": p.value} for p in forecast_points]
    adjusted = []
    for i, p in enumerate(forecast_points):
        multiplier = 1.0 + (adjustment_percent / 100.0) * ((i + 1) / n)
        adjusted.append({"date": p.date.isoformat(), "value": round(max(0.0, p.value * multiplier), 2)})
    baseline_end = baseline[-1]["value"]
    adjusted_end = adjusted[-1]["value"]
    delta_abs = round(adjusted_end - baseline_end, 2)
    delta_pct = round((delta_abs / baseline_end * 100), 2) if baseline_end else 0.0
    return {"metric": metric, "adjustment_percent": adjustment_percent, "horizon_days": horizon_days,
            "baseline": baseline, "adjusted": adjusted,
            "summary": {"baseline_end": baseline_end, "adjusted_end": adjusted_end,
                        "delta_absolute": delta_abs, "delta_percent": delta_pct}}


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
    request: Request = None,
):
    _validate_csrf_token(request)
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
    request: Request = None,
):
    _validate_csrf_token(request)
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
    request: Request = None,
):
    _validate_csrf_token(request)
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


@router.get("/target-progress")
def get_target_progress(
    metric: str = Query(..., pattern="^(attendance_rate|incident_rate|governance_score|enrollment_rate)$"),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Show progress toward targets with velocity and ETA"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    today = _jordan_today()
    period_start = today - timedelta(days=30)
    summary = _cached_network_summary(db, period_start, today, kg_filter)

    current_values = {
        "attendance_rate": summary.attendance_rate,
        "incident_rate": summary.incident_rate,
        "governance_score": summary.governance_avg_score,
        "enrollment_rate": summary.enrollment_rate,
    }

    current_value = current_values.get(metric)
    if current_value is None:
        return {"metric": metric, "error": "Metric not available"}

    default_targets = {
        "attendance_rate": 90.0,
        "incident_rate": 3.0,
        "governance_score": 80.0,
        "enrollment_rate": 85.0,
    }

    custom_target = db.query(models.PerformanceTarget).filter(
        models.PerformanceTarget.metric_type == metric,
        models.PerformanceTarget.scope_type == "NETWORK",
    ).order_by(models.PerformanceTarget.effective_date.desc()).first()

    target_value = custom_target.target_value if custom_target else default_targets.get(metric, 80.0)

    higher_is_better = metric != "incident_rate"

    if higher_is_better:
        progress = min(100, (current_value / target_value) * 100) if target_value > 0 else 0
        gap = target_value - current_value
    else:
        baseline = default_targets.get(metric, 10)
        progress = min(100, ((baseline - current_value) / (baseline - target_value)) * 100) if target_value < baseline else 0
        gap = current_value - target_value

    prev_start = period_start - timedelta(days=30)
    prev_summary = _cached_network_summary(db, prev_start, period_start, kg_filter)

    prev_values = {
        "attendance_rate": prev_summary.attendance_rate,
        "incident_rate": prev_summary.incident_rate,
        "governance_score": prev_summary.governance_avg_score,
        "enrollment_rate": prev_summary.enrollment_rate,
    }
    prev_value = prev_values.get(metric, current_value)

    velocity = (current_value - prev_value) / 30

    if higher_is_better:
        if velocity > 0 and gap > 0:
            days_to_target = int(gap / velocity)
        elif gap <= 0:
            days_to_target = 0
        else:
            days_to_target = -1
    else:
        if velocity < 0 and gap > 0:
            days_to_target = int(gap / abs(velocity))
        elif gap <= 0:
            days_to_target = 0
        else:
            days_to_target = -1

    percentile = None
    if governorate:
        all_govs = _cached_governorate_breakdown(db, period_start, today, None, allowed_kgs, None)
        gov_values = [getattr(g, metric, 0) or 0 for g in all_govs]
        if gov_values:
            gov_values.sort()
            idx = next((i for i, v in enumerate(gov_values) if v >= current_value), len(gov_values))
            percentile = round((idx / len(gov_values)) * 100)

    return {
        "metric": metric,
        "current_value": round(current_value, 2),
        "target_value": round(target_value, 2),
        "progress_percent": round(progress, 1),
        "gap": round(abs(gap), 2),
        "velocity_per_day": round(velocity, 4),
        "days_to_target": days_to_target,
        "percentile": percentile,
        "higher_is_better": higher_is_better,
        "status": "on_track" if days_to_target >= 0 and days_to_target <= 90 else "at_risk" if days_to_target >= 0 else "off_track" if days_to_target < 0 and gap > 0 else "achieved",
    }


@router.get("/network-rankings")
def get_network_rankings(
    metric: str = Query(..., pattern="^(attendance_rate|incident_rate|governance_score|total_children)$"),
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get network-wide rankings with percentile positions"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    breakdown = AnalyticsService.get_governorate_breakdown(db, period_start, period_end, governorate, allowed_kgs, None)

    rankings = []
    for item in breakdown:
        item_dict = item.model_dump() if hasattr(item, "model_dump") else item
        value = item_dict.get(metric, 0) or 0
        rankings.append(
            {
                "governorate": item_dict.get("governorate", "Unknown"),
                "value": round(value, 2),
                "kindergartens": item_dict.get("kindergarten_count", 0),
                "children": item_dict.get("children_count", 0),
            }
        )

    higher_is_better = metric != "incident_rate"
    rankings.sort(key=lambda x: x["value"], reverse=higher_is_better)

    total = len(rankings)
    for idx, item in enumerate(rankings):
        item["rank"] = idx + 1
        item["percentile"] = round(((total - idx) / total) * 100)

    return {
        "metric": metric,
        "rankings": rankings,
        "total": total,
        "higher_is_better": higher_is_better,
    }


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
    request: Request = None,
):
    _validate_csrf_token(request)
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
    db: Session = Depends(get_db),
    request: Request = None,
):
    _validate_csrf_token(request)
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
    db: Session = Depends(get_db),
    request: Request = None,
):
    _validate_csrf_token(request)
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


@router.get("/action-queue")
def get_action_queue(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get prioritized action queue based on insights and data quality"""
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

    # Get insights
    network_summary = _cached_network_summary(db, period_start, period_end, kg_filter)
    governorate_breakdown = _cached_governorate_breakdown(
        db, period_start, period_end, governorate, allowed_kgs, None
    )
    insights = InsightEngine.generate_insights(
        network_summary.model_dump(),
        [g.model_dump() if hasattr(g, 'model_dump') else g for g in governorate_breakdown]
    )

    # Convert insights to actions
    actions = []
    for insight in insights:
        action = {
            'id': f"action_{insight['type'].lower()}",
            'type': insight['type'],
            'priority': insight['severity'],
            'icon': insight['icon'],
            'title_ar': insight['message_ar'],
            'title_en': insight['message_en'],
            'description_ar': insight['action_ar'],
            'description_en': insight['action_en'],
            'affected_count': insight.get('affected_count', 0),
            'deadline': _calculate_deadline(insight['severity']),
            'status': 'pending',
            'link': insight.get('link', '#')
        }
        actions.append(action)

    # Add data quality actions if needed. evaluate_data_quality() persists a
    # DataQualityMetric but returns None, so read the latest stored metric.
    latest_dq = (
        db.query(models.DataQualityMetric)
        .filter(models.DataQualityMetric.entity_type == "NETWORK")
        .order_by(models.DataQualityMetric.evaluated_at.desc())
        .first()
    )
    completeness_percent = latest_dq.completeness_percent if latest_dq else 100.0
    if completeness_percent < 90:
        actions.append({
            'id': 'action_data_quality',
            'type': 'DATA_QUALITY',
            'priority': 'MEDIUM',
            'icon': 'bi-database-exclamation',
            'title_ar': f'جودة البيانات منخفضة ({completeness_percent:.1f}%)',
            'title_en': f'Data quality low ({completeness_percent:.1f}%)',
            'description_ar': 'مراجعة سجلات البيانات الناقصة أو غير الدقيقة',
            'description_en': 'Review incomplete or inaccurate data records',
            'affected_count': 0,
            'deadline': _calculate_deadline('MEDIUM'),
            'status': 'pending',
            'link': '/admin/analytics/reports#pane-dataquality'
        })

    # Sort by priority
    priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    actions.sort(key=lambda x: priority_order.get(x['priority'], 3))

    return {"actions": actions[:10], "total": len(actions)}


@router.get("/root-cause")
def get_root_cause(
    metric: str = Query(..., pattern="^(attendance_rate|incident_rate|governance_score)$"),
    governorate: Optional[str] = Query(None),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze root causes for metric underperformance"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    factors = []

    if metric == 'attendance_rate':
        factors = _analyze_attendance_root_causes(db, kg_filter, period_start, period_end)
    elif metric == 'incident_rate':
        factors = _analyze_incident_root_causes(db, kg_filter, period_start, period_end)
    elif metric == 'governance_score':
        factors = _analyze_governance_root_causes(db, kg_filter, period_start, period_end)

    factors.sort(key=lambda x: x['impact_score'], reverse=True)

    return {
        'metric': metric,
        'governorate': governorate,
        'period': {'start': period_start.isoformat(), 'end': period_end.isoformat()},
        'factors': factors,
        'recommendations': _generate_recommendations(factors, metric)
    }


def _analyze_attendance_root_causes(db: Session, kg_filter, period_start: date, period_end: date) -> list:
    """Analyze factors affecting attendance"""
    factors = []

    incident_count = db.query(func.count(models.Incident.id)).filter(
        *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
    )
    if kg_filter:
        incident_count = incident_count.filter(models.Incident.kindergarten_id.in_(kg_filter))
    incidents = incident_count.scalar() or 0

    if incidents > 5:
        factors.append({
            'factor_ar': 'حوادث حديثة متكررة',
            'factor_en': 'Frequent recent incidents',
            'impact_score': min(1.0, incidents / 20),
            'detail_ar': f'{incidents} حادثة في الفترة المحددة',
            'detail_en': f'{incidents} incidents in the selected period',
            'icon': 'bi-shield-exclamation',
            'severity': 'HIGH' if incidents > 10 else 'MEDIUM'
        })

    current_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == 'ACTIVE',
        models.EnrollmentApplication.created_at < jordan_day_bounds(period_end)[1]
    )
    if kg_filter:
        current_enrollments = current_enrollments.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
    current_count = current_enrollments.scalar() or 0

    prev_start = period_start - (period_end - period_start)
    prev_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == 'ACTIVE',
        models.EnrollmentApplication.created_at < jordan_day_bounds(prev_start)[1]
    )
    if kg_filter:
        prev_enrollments = prev_enrollments.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter))
    prev_count = prev_enrollments.scalar() or 0

    if prev_count > 0 and current_count < prev_count * 0.9:
        drop_pct = ((prev_count - current_count) / prev_count) * 100
        factors.append({
            'factor_ar': 'انخفاض في التسجيل',
            'factor_en': 'Enrollment decline',
            'impact_score': min(1.0, drop_pct / 30),
            'detail_ar': f'انخفاض بنسبة {drop_pct:.1f}% عن الفترة السابقة',
            'detail_en': f'{drop_pct:.1f}% decline from previous period',
            'icon': 'bi-person-dash-fill',
            'severity': 'HIGH' if drop_pct > 20 else 'MEDIUM'
        })

    total_expected = (period_end - period_start).days + 1
    attendance_records = db.query(func.count(func.distinct(models.AttendanceLog.date))).filter(
        models.AttendanceLog.date >= period_start,
        models.AttendanceLog.date <= period_end
    ).scalar() or 0

    if attendance_records < total_expected * 0.8:
        completeness = (attendance_records / total_expected) * 100
        factors.append({
            'factor_ar': 'بيانات حضور غير مكتملة',
            'factor_en': 'Incomplete attendance data',
            'impact_score': min(1.0, (100 - completeness) / 50),
            'detail_ar': f'{completeness:.1f}% فقط من أيام التسجيل',
            'detail_en': f'Only {completeness:.1f}% of days have records',
            'icon': 'bi-calendar-x-fill',
            'severity': 'MEDIUM'
        })

    return factors


def _analyze_incident_root_causes(db: Session, kg_filter, period_start: date, period_end: date) -> list:
    """Analyze factors affecting incident rates"""
    factors = []

    serious_incidents = db.query(func.count(models.Incident.id)).filter(
        *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end),
        models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL])
    )
    if kg_filter:
        serious_incidents = serious_incidents.filter(models.Incident.kindergarten_id.in_(kg_filter))
    serious_count = serious_incidents.scalar() or 0

    total_incidents = db.query(func.count(models.Incident.id)).filter(
        *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
    )
    if kg_filter:
        total_incidents = total_incidents.filter(models.Incident.kindergarten_id.in_(kg_filter))
    total_count = total_incidents.scalar() or 0

    if total_count > 0 and serious_count / total_count > 0.3:
        ratio = (serious_count / total_count) * 100
        factors.append({
            'factor_ar': 'نسبة حوادث خطيرة مرتفعة',
            'factor_en': 'High serious incident ratio',
            'impact_score': min(1.0, ratio / 50),
            'detail_ar': f'{ratio:.1f}% من الحوادث خطيرة',
            'detail_en': f'{ratio:.1f}% of incidents are serious',
            'icon': 'bi-exclamation-octagon-fill',
            'severity': 'HIGH'
        })

    if kg_filter and total_count > 0:
        top_kg_incidents = db.query(
            models.Incident.kindergarten_id,
            func.count(models.Incident.id).label('count')
        ).filter(
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end),
            models.Incident.kindergarten_id.in_(kg_filter)
        ).group_by(models.Incident.kindergarten_id).order_by(desc('count')).limit(3).all()

        if top_kg_incidents and len(top_kg_incidents) > 0:
            top_count = sum(c for _, c in top_kg_incidents)
            concentration = (top_count / total_count) * 100
            if concentration > 60:
                factors.append({
                    'factor_ar': 'حوادث مركزة في حضانات محددة',
                    'factor_en': 'Incidents concentrated in specific kindergartens',
                    'impact_score': min(1.0, concentration / 80),
                    'detail_ar': f'{concentration:.1f}% من الحوادث في {len(top_kg_incidents)} حضانة',
                    'detail_en': f'{concentration:.1f}% of incidents in {len(top_kg_incidents)} kindergartens',
                    'icon': 'bi-geo-alt-fill',
                    'severity': 'MEDIUM'
                })

    return factors


def _analyze_governance_root_causes(db: Session, kg_filter, period_start: date, period_end: date) -> list:
    """Analyze factors affecting governance scores"""
    factors = []

    low_gov_count = db.query(func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.governance_score < 60
    )
    if kg_filter:
        low_gov_count = low_gov_count.filter(models.Kindergarten.id.in_(kg_filter))
    low_count = low_gov_count.scalar() or 0

    total_kgs = db.query(func.count(models.Kindergarten.id))
    if kg_filter:
        total_kgs = total_kgs.filter(models.Kindergarten.id.in_(kg_filter))
    total_count = total_kgs.scalar() or 0

    if total_count > 0 and low_count / total_count > 0.2:
        pct = (low_count / total_count) * 100
        factors.append({
            'factor_ar': 'نسبة عالية من الحضانات منخفضة الحوكمة',
            'factor_en': 'High proportion of low-governance kindergartens',
            'impact_score': min(1.0, pct / 40),
            'detail_ar': f'{pct:.1f}% من الحضانات درجة الحوكمة فيها أقل من 60',
            'detail_en': f'{pct:.1f}% of kindergartens have governance score below 60',
            'icon': 'bi-clipboard-x-fill',
            'severity': 'HIGH' if pct > 40 else 'MEDIUM'
        })

    return factors


def _generate_recommendations(factors: list, metric: str) -> list:
    """Generate actionable recommendations based on root causes"""
    recommendations = []

    for factor in factors[:3]:
        if 'incident' in factor.get('factor_en', '').lower():
            recommendations.append({
                'recommendation_ar': 'مراجعة بروتوكولات السلامة وتوفير تدريب إضافي',
                'recommendation_en': 'Review safety protocols and provide additional training',
                'priority': factor['severity'],
                'related_factor': factor['factor_en']
            })
        elif 'enrollment' in factor.get('factor_en', '').lower():
            recommendations.append({
                'recommendation_ar': 'مراجعة عملية التسجيل وتبسيطها',
                'recommendation_en': 'Review and streamline the enrollment process',
                'priority': factor['severity'],
                'related_factor': factor['factor_en']
            })
        elif 'data' in factor.get('factor_en', '').lower() or 'incomplete' in factor.get('factor_en', '').lower():
            recommendations.append({
                'recommendation_ar': 'تعزيز متطلبات الإبلاغ ومتابعة اكتمال البيانات',
                'recommendation_en': 'Strengthen reporting requirements and follow up on data completeness',
                'priority': factor['severity'],
                'related_factor': factor['factor_en']
            })
        elif 'governance' in factor.get('factor_en', '').lower():
            recommendations.append({
                'recommendation_ar': 'وضع خطط تحسين مخصصة للحضانات منخفضة الأداء',
                'recommendation_en': 'Create targeted improvement plans for underperforming kindergartens',
                'priority': factor['severity'],
                'related_factor': factor['factor_en']
            })
        elif 'concentrated' in factor.get('factor_en', '').lower():
            recommendations.append({
                'recommendation_ar': 'تركيز التدخلات على الحضانات الأكثر تأثراً',
                'recommendation_en': 'Focus interventions on the most affected kindergartens',
                'priority': factor['severity'],
                'related_factor': factor['factor_en']
            })

    return recommendations


def _calculate_deadline(severity: str) -> str:
    """Calculate recommended deadline based on severity"""
    today = _jordan_today()
    if severity == 'HIGH':
        deadline = today + timedelta(days=3)
    elif severity == 'MEDIUM':
        deadline = today + timedelta(days=7)
    else:
        deadline = today + timedelta(days=14)
    return deadline.isoformat()


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
        models.Kindergarten.created_at < jordan_day_bounds(as_of_date)[1],
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
    # Subquery for active child_ids in scope (avoids Cartesian product)
    active_child_sq = db.query(models.EnrollmentApplication.child_id).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    )
    if kg_ids is not None:
        active_child_sq = active_child_sq.filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
        )
    active_child_sq = active_child_sq.distinct().scalar_subquery()
    query = db.query(func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date >= period_start,
        models.AttendanceLog.date <= period_end,
        models.AttendanceLog.child_id.in_(active_child_sq),
    )
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

        # Cache keyed by date range + gov filter + user scope.
        #
        # Scope key must NOT be current_user.role alone: a MANAGER's or
        # SUPERVISOR's actual data scope is their own kindergarten
        # assignment, which differs per user and is not fully captured by
        # gov_filter (two managers can share a governorate while managing
        # different kindergartens). Keying on role alone would let two such
        # users share one cache entry within the TTL window, each silently
        # seeing the other's kindergarten's dashboard. ADMINs share a scope
        # key since every admin sees the identical (optionally
        # governorate-filtered) network-wide view.
        scope_key = "ADMIN" if current_user.role == models.UserRole.ADMIN else f"user:{current_user.id}"
        cache_key = f"analytics:dashboard:{period_start}:{period_end}:{gov_filter}:{scope_key}"
        cached = _analytics_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached analytics dashboard response")
            return cached

        logger.info(f"Fetching analytics data for date range {period_start} to {period_end}")

        network_summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)
        previous_period_bounds = _previous_period_bounds(period_start, period_end)
        if previous_period_bounds:
            previous_start, previous_end = previous_period_bounds
            # Only attendance_rate, incident_rate, and total_kindergartens from the
            # previous period feed into `deltas` below — the full get_network_summary()
            # call also computes governance_avg_score (a ~11s network-wide scan over
            # every kindergarten), enrollment_rate, and report submission/approval
            # rates, none of which are used here. Compute just the three cheap
            # aggregate values that are actually read instead of the full summary.
            previous_attendance_rate = AnalyticsService._compute_network_attendance_rate(
                db, previous_start, previous_end, kg_filter
            )
            previous_incident_rate = AnalyticsService._compute_network_incident_rate(
                db, previous_start, previous_end, kg_filter
            )
            previous_total_kindergartens = _count_active_kindergartens_at(db, kg_filter, previous_end)
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
                        previous_total_kindergartens,
                        True,
                        available=True,
                    )
                ),
                "attendance_rate": MetricDelta(
                    **_build_metric_delta(
                        network_summary.attendance_rate,
                        previous_attendance_rate,
                        True,
                        available=previous_expected_child_days > 0,
                    )
                ),
                "incident_rate": MetricDelta(
                    **_build_metric_delta(
                        network_summary.incident_rate,
                        previous_incident_rate,
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
        try:
            risk_radar = AnalyticsService.get_high_risk_children(db, kg_filter)
        except SQLAlchemyError as e:
            # Isolated on purpose: Risk Intelligence is one field in this payload,
            # not the reason for the request. A failure here should degrade to an
            # empty radar rather than 500 the whole dashboard (network_summary,
            # governorate_breakdown, trends, governance_distribution are unrelated).
            logger.error("Risk radar computation failed, degrading to empty list: %s", str(e), exc_info=True)
            risk_radar = []
        governance_distribution = AnalyticsService.get_governance_distribution(db, period_start, period_end, kg_filter)

        logger.info("Successfully retrieved analytics data")

        validated_summary = validate_dashboard_data(network_summary.model_dump())
        network_summary = type(network_summary)(**validated_summary)

        result = ConsolidatedAnalyticsResponse(
            network_summary=network_summary,
            governorate_breakdown=governorate_breakdown,
            attendance_trend=attendance_trend,
            incident_trend=incident_trend,
            risk_radar=risk_radar,
            governance_distribution=governance_distribution,
        )
        _analytics_cache_set(cache_key, result.model_dump(mode="json"))
        return result
    
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


@router.get("/insights")
def get_insights(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate actionable insights for the dashboard"""
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    gov_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and gov_filter is not None:
        gov_filter = [kg for kg in gov_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        gov_filter = allowed_kgs

    network_summary = _cached_network_summary(db, period_start, period_end, gov_filter)
    governorate_breakdown = _cached_governorate_breakdown(
        db, period_start, period_end, governorate, allowed_kgs, None
    )

    insights = InsightEngine.generate_insights(
        network_summary.model_dump(),
        [g.model_dump() if hasattr(g, 'model_dump') else g for g in governorate_breakdown]
    )

    return {"insights": insights, "count": len(insights)}


@router.get("/annotations")
def get_annotations(
    period_start: date = Query(...),
    period_end: date = Query(...),
    governorate: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get chart annotations (holidays, anomalies, events) for the trend chart."""
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must be before or equal to period_end")

    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    annotations: List[Dict[str, Any]] = []

    # Jordan public holidays (fixed Gregorian dates, expanded across the range)
    for holiday in _get_jordan_holidays(period_start, period_end):
        annotations.append({
            'type': 'holiday',
            'date': holiday['date'].isoformat(),
            'label_ar': holiday['name_ar'],
            'label_en': holiday['name_en'],
            'color': '#f59e0b',
            'severity': 'info'
        })

    # Resolve kindergarten scope (intersection of allowed and requested governorate)
    kg_filter = _kg_ids_for_governorate(db, governorate)
    if allowed_kgs is not None and kg_filter is not None:
        kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
    elif allowed_kgs is not None:
        kg_filter = allowed_kgs

    # Attendance anomalies from existing z-score detection
    attendance_series_data = AnalyticsService.get_network_trends(
        db, "attendance", period_start, period_end, kg_filter
    )
    attendance_anomalies = z_score_anomalies(
        [SeriesPoint(date=date.fromisoformat(p.date), value=p.value) for p in attendance_series_data]
    )
    for point, score, severity in attendance_anomalies:
        annotations.append({
            'type': 'anomaly',
            'date': point.date.isoformat(),
            'label_ar': f'شذوذ في الحضور (الدرجة: {score:.2f})',
            'label_en': f'Attendance anomaly (score: {score:.2f})',
            'color': '#ef4444' if severity == models.SeverityLevel.HIGH else '#f59e0b',
            'severity': severity.value if hasattr(severity, 'value') else str(severity),
            'metric': 'attendance'
        })

    # Incident anomalies from existing z-score detection
    incident_series_data = AnalyticsService.get_network_trends(
        db, "incidents", period_start, period_end, kg_filter
    )
    incident_anomalies = z_score_anomalies(
        [SeriesPoint(date=date.fromisoformat(p.date), value=p.value) for p in incident_series_data]
    )
    for point, score, severity in incident_anomalies:
        annotations.append({
            'type': 'anomaly',
            'date': point.date.isoformat(),
            'label_ar': f'شذوذ في الحوادث (الدرجة: {score:.2f})',
            'label_en': f'Incident anomaly (score: {score:.2f})',
            'color': '#ef4444' if severity == models.SeverityLevel.HIGH else '#f59e0b',
            'severity': severity.value if hasattr(severity, 'value') else str(severity),
            'metric': 'incidents'
        })

    annotations.sort(key=lambda x: x['date'])
    return {"annotations": annotations}


# Jordan Islamic public holidays — Gregorian dates for the first day of each
# observance. Hijri-based, so these are the officially published/announced dates
# and are APPROXIMATE: actual observance can shift by ±1 day on moon-sighting.
# VERIFY AND EXTEND ANNUALLY against the official Jordan government calendar.
# (month, day, name_ar, name_en) keyed by Gregorian year.
_JORDAN_ISLAMIC_HOLIDAYS: Dict[int, list] = {
    2025: [
        (1, 27, 'الإسراء والمعراج', "Isra and Mi'raj"),
        (3, 30, 'عيد الفطر', 'Eid al-Fitr'),
        (6, 5, 'وقفة عرفة', 'Arafat Day'),
        (6, 6, 'عيد الأضحى', 'Eid al-Adha'),
        (6, 26, 'رأس السنة الهجرية', 'Islamic New Year'),
        (9, 4, 'المولد النبوي الشريف', "Prophet's Birthday"),
    ],
    2026: [
        (1, 16, 'الإسراء والمعراج', "Isra and Mi'raj"),
        (3, 20, 'عيد الفطر', 'Eid al-Fitr'),
        (5, 26, 'وقفة عرفة', 'Arafat Day'),
        (5, 27, 'عيد الأضحى', 'Eid al-Adha'),
        (6, 16, 'رأس السنة الهجرية', 'Islamic New Year'),
        (8, 25, 'المولد النبوي الشريف', "Prophet's Birthday"),
    ],
    2027: [
        (1, 5, 'الإسراء والمعراج', "Isra and Mi'raj"),
        (3, 10, 'عيد الفطر', 'Eid al-Fitr'),
        (5, 16, 'وقفة عرفة', 'Arafat Day'),
        (5, 17, 'عيد الأضحى', 'Eid al-Adha'),
        (6, 6, 'رأس السنة الهجرية', 'Islamic New Year'),
        (8, 14, 'المولد النبوي الشريف', "Prophet's Birthday"),
    ],
}


def _get_jordan_holidays(start: date, end: date) -> list:
    """Return Jordan public holidays (fixed Gregorian + Islamic) within [start, end]."""
    fixed_holidays = [
        (1, 1, 'رأس السنة الميلادية', "New Year's Day"),
        (5, 1, 'عيد العمال', 'Labour Day'),
        (5, 25, 'عيد الاستقلال', 'Independence Day'),
        (12, 25, 'عيد الميلاد المجيد', 'Christmas Day'),
    ]
    holidays = []
    for year in range(start.year, end.year + 1):
        for month, day, name_ar, name_en in fixed_holidays:
            try:
                holiday_date = date(year, month, day)
            except ValueError:
                continue
            if start <= holiday_date <= end:
                holidays.append({
                    'date': holiday_date,
                    'name_ar': name_ar,
                    'name_en': name_en,
                })
        for month, day, name_ar, name_en in _JORDAN_ISLAMIC_HOLIDAYS.get(year, []):
            try:
                holiday_date = date(year, month, day)
            except ValueError:
                continue
            if start <= holiday_date <= end:
                holidays.append({
                    'date': holiday_date,
                    'name_ar': name_ar,
                    'name_en': name_en,
                })
    return holidays


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
    request_body: ExportRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Export analytics reports (CSV or Excel) with memory streaming for large datasets.
    """
    _validate_csrf_token(request)
    validators.validate_admin_role(current_user)

    start_str = request_body.filters.get("period_start") if request_body.filters else None
    end_str = request_body.filters.get("period_end") if request_body.filters else None
    
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
                report_type=request_body.report_type, export_format=request_body.export_format,
                filters=request_body.filters, status_value="failed", error_message="Invalid date format", sensitivity_level=3
            )
            raise HTTPException(status_code=400, detail="Invalid date format")

    import csv
    import io
    from fastapi.responses import Response, StreamingResponse

    # Determine headers and row generator
    headers = []
    
    def row_generator():
        if request_body.report_type == "attendance":
            headers.extend(["Kindergarten", "Children Count", "Capacity", "Attendance Rate %"])
            yield headers
            kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).yield_per(100)
            for kg in kgs:
                rate = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
                yield [kg.name_ar, len(kg.enrollments), "N/A", rate]
                
        elif request_body.report_type == "incidents":
            # Timezone stated in the heading: the column is a Jordan calendar date
            # derived from a UTC-stored instant, and without the label a reader cannot
            # tell which day an incident near midnight belongs to.
            headers.extend(["Date (Asia/Amman)", "Kindergarten", "Type", "Severity", "Description", "Child"])
            yield headers
            incidents = db.query(models.Incident).filter(
                *jordan_date_range_filter(models.Incident.occurred_at, start_date, end_date)
            ).yield_per(100)
            for inc in incidents:
                ch_name = f"{inc.child.first_name} {inc.child.last_name}" if inc.child else "Unknown"
                yield [to_jordan_date(inc.occurred_at).strftime("%Y-%m-%d"), inc.kindergarten.name_ar if inc.kindergarten else "", inc.type.value, inc.severity_level.value, inc.description, ch_name]

        elif request_body.report_type == "compliance":
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

        elif request_body.report_type == "governorate":
            headers.extend(["Governorate", "Kindergartens", "Children", "Attendance %", "Incident Rate", "Governance Score"])
            yield headers
            data = AnalyticsService.get_governorate_breakdown(db, start_date, end_date, None, None, None)
            for item in data:
                yield [item.governorate, item.kindergarten_count, item.children_count, item.attendance_rate, item.incident_rate, item.governance_score]

        elif request_body.report_type == "full_audit":
            headers.extend(["Timestamp", "User", "Action", "Entity", "Details", "IP"])
            yield headers
            
            # Streaming query for large audit logs
            query = db.query(models.AuditLog).filter(
                 *jordan_date_range_filter(models.AuditLog.created_at, start_date, end_date)
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
            report_type=request_body.report_type, export_format=request_body.export_format,
            filters=request_body.filters, status_value="failed", error_message="Invalid report type", sensitivity_level=3
        )
        raise HTTPException(status_code=400, detail="Invalid report type")

    # Excel Export
    if request_body.export_format and request_body.export_format.lower() == "excel":
        if openpyxl is None:
            raise HTTPException(status_code=500, detail="Excel export is not supported (openpyxl missing)")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = request_body.report_type.capitalize()
        
        ws.append(first_row_headers)
        for row in gen:
            ws.append(row)
            
        output = io.BytesIO()
        wb.save(output)
        
        filename = f"{request_body.report_type}_report_{start_date}_{end_date}.xlsx"
        _log_analytics_export_audit(db, action=AuditAction.ANALYTICS_EXPORT_SYNC, actor=current_user, report_type=request_body.report_type, export_format="EXCEL", filters=request_body.filters, status_value="completed", file_path=filename)
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    # Default: CSV Export (Streaming)
    filename = f"{request_body.report_type}_report_{start_date}_{end_date}.csv"
    _log_analytics_export_audit(db, action=AuditAction.ANALYTICS_EXPORT_SYNC, actor=current_user, report_type=request_body.report_type, export_format="CSV", filters=request_body.filters, status_value="completed", file_path=filename)

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
    statuses: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    reviewer_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
        """Get comprehensive enrollment/registration analytics.

        Accepts either singular filters (status_filter/source_filter/reviewer_id)
        or multi-select lists (statuses/sources/reviewer_ids); the lists win when
        provided so the Reports Center multi-select filters apply.
        """
        query = db.query(models.EnrollmentApplication)

        if kindergarten_ids:
            query = query.filter(models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids))
        elif kindergarten_id:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        if statuses:
            _status_enums = []
            for s in statuses:
                try:
                    _status_enums.append(models.EnrollmentStatus(str(s).upper()))
                except ValueError:
                    continue
            if _status_enums:
                query = query.filter(models.EnrollmentApplication.status.in_(_status_enums))
        elif status_filter:
            try:
                query = query.filter(models.EnrollmentApplication.status == models.EnrollmentStatus(status_filter.upper()))
            except ValueError:
                pass

        if sources:
            query = query.filter(models.EnrollmentApplication.source.in_(sources))
        elif source_filter:
            query = query.filter(models.EnrollmentApplication.source == source_filter)

        if reviewer_ids:
            query = query.filter(models.EnrollmentApplication.decision_by.in_(reviewer_ids))
        elif reviewer_id:
            query = query.filter(models.EnrollmentApplication.decision_by == reviewer_id)

        # Period filter on created_at for "new applications"
        period_query = query.filter(
            *jordan_date_range_filter(models.EnrollmentApplication.created_at, period_start, period_end),
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
            *jordan_date_range_filter(models.EnrollmentApplication.decision_at, period_start, period_end),
        ).all():
            day = ea.decision_at.date().isoformat()
            daily_decided[day] = daily_decided.get(day, 0) + 1

        # Time-series for new applications per day in period
        daily_new = {}
        for ea in period_query.all():
            day = to_jordan_date(ea.created_at).isoformat()
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
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
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
                *jordan_date_range_filter(models.Incident.occurred_at, current, current)
            )
            if dim_upper in ("KINDERGARTEN", "GOVERNORATE") and kg_scope:
                query = query.filter(models.Incident.kindergarten_id.in_(kg_scope))
            value = query.scalar() or 0

        elif metric == "enrollment_count":
            query = db.query(func.count(models.EnrollmentApplication.id)).filter(
                *jordan_date_range_filter(models.EnrollmentApplication.created_at, current, current)
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


def _drilldown_geo_rollup(db, group_col, base_filter, allowed_kgs):
    """Return ({group_value: nursery_count}, {group_value: children_count}) for an
    active-nursery grouping, honoring an optional allowed-kindergarten scope.

    Used by the NETWORK -> Governorate -> City drill-down levels. Two grouped
    queries (not per-nursery loops) so higher levels stay cheap on large networks.
    """
    kg_q = db.query(group_col, func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE, *base_filter
    )
    ch_q = (
        db.query(group_col, func.count(func.distinct(models.EnrollmentApplication.id)))
        .join(models.Class, models.Class.kindergarten_id == models.Kindergarten.id)
        .join(models.EnrollmentApplication, models.EnrollmentApplication.class_id == models.Class.id)
        .filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            *base_filter,
        )
    )
    if allowed_kgs is not None:
        kg_q = kg_q.filter(models.Kindergarten.id.in_(allowed_kgs))
        ch_q = ch_q.filter(models.Kindergarten.id.in_(allowed_kgs))
    nurseries = {k: v for k, v in kg_q.group_by(group_col).all() if k}
    children = {k: v for k, v in ch_q.group_by(group_col).all() if k}
    return nurseries, children


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
    Drill down one level of the hierarchy:
    Country(NETWORK) -> Governorate -> City(AREA) -> Nursery(KINDERGARTEN) -> Class -> Child.

    Each level returns aggregate ``metrics`` plus a ``children`` list of the next
    level's rows. DISTRICT is also accepted as an optional intermediate (District
    lists its Cities). "City" is the user-facing label for the AREA dimension — no
    separate City model exists (Kindergarten.area is the finest geographic field).
    """
    dim = dimension_type.upper()
    allowed_kgs = _allowed_kindergarten_ids(current_user, db)
    allowed_govs = _allowed_governorates(current_user, db) or []
    if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
        raise HTTPException(status_code=403, detail="Access denied")

    period_start, period_end = get_date_range(start_date, end_date)

    if dim in {"KINDERGARTEN", "CLASS", "CHILD"} and not dimension_id.isdigit():
        raise HTTPException(status_code=400, detail="dimension_id must be numeric for this dimension_type")

    if dim == "NETWORK":
        # Country level -> list governorates. dimension_id is ignored (use "all").
        base = []
        if allowed_govs and current_user.role != models.UserRole.ADMIN:
            base.append(models.Kindergarten.governorate.in_(allowed_govs))
        nurseries, children = _drilldown_geo_rollup(
            db, models.Kindergarten.governorate, base, allowed_kgs
        )
        gov_rows = [
            {
                "id": gov,
                "name": gov,
                "dimension_type": "GOVERNORATE",
                "nursery_count": nurseries.get(gov, 0),
                "children_count": children.get(gov, 0),
            }
            for gov in sorted(nurseries)
        ]
        return DrilldownResponse(
            dimension_type="NETWORK",
            dimension_id="all",
            dimension_name="الشبكة",
            period_start=period_start,
            period_end=period_end,
            metrics={
                "governorate_count": len(gov_rows),
                "nursery_count": sum(nurseries.values()),
                "children_count": sum(children.values()),
            },
            children=gov_rows,
        )

    if dim == "GOVERNORATE":
        if current_user.role != models.UserRole.ADMIN and allowed_govs and dimension_id not in allowed_govs:
            raise HTTPException(status_code=403, detail="Governorate not allowed")

        # Governorate level -> list Cities (distinct areas) within the governorate.
        base = [governorate_filter(models.Kindergarten.governorate, dimension_id)]
        nurseries, children = _drilldown_geo_rollup(
            db, models.Kindergarten.area, base, allowed_kgs
        )
        if not nurseries:
            raise HTTPException(status_code=403, detail="No allowed nurseries in this governorate")
        city_rows = [
            {
                "id": area,
                "name": area,
                "dimension_type": "AREA",
                "nursery_count": nurseries.get(area, 0),
                "children_count": children.get(area, 0),
            }
            for area in sorted(nurseries)
        ]
        return DrilldownResponse(
            dimension_type="GOVERNORATE",
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            period_start=period_start,
            period_end=period_end,
            metrics={
                "city_count": len(city_rows),
                "nursery_count": sum(nurseries.values()),
                "children_count": sum(children.values()),
            },
            children=city_rows,
        )

    if dim == "DISTRICT":
        # Optional intermediate: District -> list Cities (areas) within the district.
        base = [models.Kindergarten.district == dimension_id]
        nurseries, children = _drilldown_geo_rollup(
            db, models.Kindergarten.area, base, allowed_kgs
        )
        if not nurseries:
            raise HTTPException(status_code=404, detail="No nurseries in this district")
        city_rows = [
            {
                "id": area, "name": area, "dimension_type": "AREA",
                "nursery_count": nurseries.get(area, 0),
                "children_count": children.get(area, 0),
            }
            for area in sorted(nurseries)
        ]
        return DrilldownResponse(
            dimension_type="DISTRICT",
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            period_start=period_start,
            period_end=period_end,
            metrics={
                "city_count": len(city_rows),
                "nursery_count": sum(nurseries.values()),
                "children_count": sum(children.values()),
            },
            children=city_rows,
        )

    if dim == "AREA":
        # City level -> list Nurseries in this area, each with its own metrics.
        kg_ids = [
            r[0] for r in db.query(models.Kindergarten.id).filter(
                models.Kindergarten.area == dimension_id,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            ).all()
        ]
        if allowed_kgs is not None:
            kg_ids = [kg for kg in kg_ids if kg in allowed_kgs]
        if not kg_ids:
            raise HTTPException(status_code=403, detail="No allowed nurseries in this city")

        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.id.in_(kg_ids),
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        ).all()

        nursery_rows = []
        for kg in kindergartens:
            metrics = AnalyticsService.get_kindergarten_metrics(
                db, kg.id, period_start, period_end
            )
            row = metrics.model_dump()
            row["dimension_type"] = "KINDERGARTEN"
            nursery_rows.append(row)

        total_children = sum(c["children_count"] for c in nursery_rows)
        governance_scores = [
            c["governance_score"] for c in nursery_rows
            if c.get("governance_score") is not None
        ]
        avg_governance = (
            sum(governance_scores) / len(governance_scores) if governance_scores else None
        )
        return DrilldownResponse(
            dimension_type="AREA",
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            period_start=period_start,
            period_end=period_end,
            metrics={
                "nursery_count": len(kindergartens),
                "children_count": total_children,
                "governance_score": avg_governance,
            },
            children=nursery_rows,
        )

    elif dim == "KINDERGARTEN":
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
                attendance_rate = min((attendance_count / days_in_period * 100) if days_in_period > 0 else 0, 100.0)

                children_list.append({
                    "id": child.id,
                    "name": f"{child.first_name} {child.last_name}",
                    "dimension_type": "CHILD",
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

    elif dim == "CHILD":
        # Leaf level -> a single child's attendance summary for the period.
        # privacy_level=restricted; Phase 4 gates this behind analytics:child_detail.
        child_id = int(dimension_id)
        child = db.query(models.Child).filter(models.Child.id == child_id).first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")

        # Scope: the child's class -> kindergarten must be within the caller's scope.
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).first()
        if enrollment and enrollment.class_id:
            cls = db.query(models.Class).filter(models.Class.id == enrollment.class_id).first()
            if cls:
                enforce_kindergarten_scope(current_user, cls.kindergarten_id, db)

        present_count = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id == child_id,
            models.AttendanceLog.status.in_(["PRESENT", "LATE"]),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
        ).scalar() or 0
        total_logged = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.child_id == child_id,
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
        ).scalar() or 0
        attendance_rate = round(present_count / total_logged * 100, 2) if total_logged else None

        # analytics:child_detail is ADMIN-only; suppress values for other roles
        # (scope already enforced above) rather than leak individual-child figures.
        if can_view_child_detail(current_user):
            child_metrics = {
                "attendance_rate": attendance_rate,
                "attendance_days": present_count,
                "logged_days": total_logged,
                "data_state": "valid",
            }
        else:
            child_metrics = {
                "attendance_rate": None,
                "attendance_days": None,
                "logged_days": None,
                "data_state": "suppressed",
            }

        return DrilldownResponse(
            dimension_type="CHILD",
            dimension_id=dimension_id,
            dimension_name=f"{child.first_name} {child.last_name}",
            period_start=period_start,
            period_end=period_end,
            metrics=child_metrics,
            children=[],  # leaf — no further drill-down
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
def compare_endpoint(
    mode: Optional[str] = Query(None, description="Comparison mode: 'period' for time period comparison"),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    compare_start: Optional[date] = Query(None),
    compare_end: Optional[date] = Query(None),
    governorate: Optional[str] = Query(None),
    kg_ids: Optional[str] = Query(None, description="Comma-separated kindergarten IDs"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if mode == "period":
        """Compare two time periods and return deltas"""
        if not period_start or not period_end or not compare_start or not compare_end:
            raise HTTPException(status_code=422, detail="period_start, period_end, compare_start, and compare_end are required for period comparison")

        if period_start > period_end:
            raise HTTPException(status_code=422, detail="period_start must be before or equal to period_end")
        if compare_start > compare_end:
            raise HTTPException(status_code=422, detail="compare_start must be before or equal to compare_end")

        allowed_kgs = _allowed_kindergarten_ids(current_user, db)
        if current_user.role != models.UserRole.ADMIN and not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")

        kg_filter = _kg_ids_for_governorate(db, governorate)
        if allowed_kgs is not None and kg_filter is not None:
            kg_filter = [kg for kg in kg_filter if kg in allowed_kgs]
        elif allowed_kgs is not None:
            kg_filter = allowed_kgs

        current_summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_filter)
        compare_summary = AnalyticsService.get_network_summary(db, compare_start, compare_end, kg_filter)

        def calc_delta(current_val, compare_val, higher_is_better=True):
            if compare_val is None or compare_val == 0:
                return {'absolute': 0, 'percentage': 0, 'direction': 'flat', 'significant': False}

            absolute = current_val - compare_val
            percentage = (absolute / compare_val) * 100 if compare_val != 0 else 0

            if higher_is_better:
                direction = 'up' if absolute > 0 else 'down' if absolute < 0 else 'flat'
            else:
                direction = 'down' if absolute > 0 else 'up' if absolute < 0 else 'flat'

            significant = abs(percentage) > 5

            return {
                'absolute': round(absolute, 2),
                'percentage': round(percentage, 2),
                'direction': direction,
                'significant': significant
            }

        deltas = {
            'total_kindergartens': calc_delta(current_summary.total_kindergartens, compare_summary.total_kindergartens, True),
            'total_children': calc_delta(current_summary.total_children, compare_summary.total_children, True),
            'attendance_rate': calc_delta(current_summary.attendance_rate, compare_summary.attendance_rate, True),
            'incident_rate': calc_delta(current_summary.incident_rate, compare_summary.incident_rate, False),
            'governance_avg_score': calc_delta(current_summary.governance_avg_score, compare_summary.governance_avg_score, True),
        }

        return {
            'current_period': {
                'start': period_start.isoformat(),
                'end': period_end.isoformat(),
                'summary': current_summary.model_dump(mode='json')
            },
            'compare_period': {
                'start': compare_start.isoformat(),
                'end': compare_end.isoformat(),
                'summary': compare_summary.model_dump(mode='json')
            },
            'deltas': deltas
        }

    """Compare multiple kindergartens side by side"""
    if not kg_ids:
        raise HTTPException(status_code=422, detail="kg_ids is required for kindergarten comparison")

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
    metric: str = FastAPIPath(..., pattern="^(attendance_rate|incident_rate|ratio_compliance|governance_score)$"),
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

    # get_rankings scores every kindergarten in scope with the KPI engine's
    # per-kindergarten aggregator just to return the top/bottom N -- the same
    # cost pattern already fixed on dashboard-data and kpi/alerts (~13-33s
    # for the full network, uncached). This endpoint had no caching at all.
    # 5-minute TTL (vs. the 60s used elsewhere): a leaderboard is inherently
    # a slower-changing view than live alerts/KPIs, and the longer window
    # meaningfully cuts how often the expensive scan re-runs for a page most
    # admins check periodically rather than continuously.
    #
    # Scope key: ADMINs share one entry per (metric, filters, period) since
    # every admin sees the identical view; non-admins are keyed by user id,
    # since two managers/supervisors can share a governorate while managing
    # different kindergartens and must never share a cached result.
    scope_key = "ADMIN" if current_user.role == models.UserRole.ADMIN else f"user:{current_user.id}"
    cache_key = (
        f"analytics:rankings:{metric}:{top_n}:{bottom}:"
        f"{period_start}:{period_end}:{governorate or 'all'}:{scope_key}"
    )
    cached = _analytics_cache_get(cache_key)
    if cached is not None:
        return cached

    rankings = AnalyticsService.get_rankings(
        db, metric, period_start, period_end, top_n, bottom, kg_filter
    )

    result = {
        "metric": metric,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "order": "bottom" if bottom else "top",
        "rankings": [r.model_dump() for r in rankings]
    }
    _analytics_cache_set(cache_key, result, ttl=300)
    return result


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

    # Scope by user role — use the standard scope helpers
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        allowed_kgs = _allowed_kindergarten_ids(current_user, db)
        # allowed_kindergarten_ids() returns None for "unrestricted (admin)" and an
        # empty list for "no access at all". Both are falsy, so guarding on
        # `allowed_kgs and ...` collapsed the two: a caller with an EMPTY allow-list
        # fell through unscoped and got whatever kindergarten_id they asked for. A
        # parent is always [], so any parent could read any kindergarten's KPIs.
        # Deny an empty scope first — the same order the other 25 call sites use.
        if not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")
        if kg_id is None and len(allowed_kgs) == 1:
            kg_id = allowed_kgs[0]
        elif kg_id is not None and kg_id not in allowed_kgs:
            raise HTTPException(status_code=403, detail="Not allowed to access this kindergarten")
    
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
            attendance_rate = min(round((attendance_count / expected_logs) * 100, 2), 100.0)
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
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
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
    
    # Scope by user role.
    #
    # Forcing kg_id to current_user.kindergarten_id looks safe but fails open for a
    # caller who has no kindergarten at all: a parent has kindergarten_id = None, so
    # kg_id became None and every query below ran unscoped, returning network-wide
    # figures. Establish that the caller has a scope before relying on it.
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        allowed_kgs = _allowed_kindergarten_ids(current_user, db)
        if not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")
        kg_id = current_user.kindergarten_id or allowed_kgs[0]
    
    today = _jordan_today()

    # Get total children
    children_query = db.query(models.Child)
    if kg_id:
        # Enrolment links a *child* to a kindergarten. This previously filtered on
        # EnrollmentApplication.parent_id and EnrollmentStatus.ENROLLED, neither of
        # which exists, so the endpoint raised AttributeError and answered 500 for
        # every caller. Counting the enrolled children directly is both correct and
        # narrower: it does not pull in a parent's other children at another
        # kindergarten.
        enrolled_child_ids = db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
        ).scalar_subquery()
        children_query = children_query.filter(models.Child.id.in_(enrolled_child_ids))
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
    
    attendance_rate = min(round((actual_logs / expected_logs * 100) if expected_logs > 0 else 0, 2), 100.0)
    
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
    
    # Scope by user role.
    #
    # Forcing kg_id to current_user.kindergarten_id looks safe but fails open for a
    # caller who has no kindergarten at all: a parent has kindergarten_id = None, so
    # kg_id became None and every query below ran unscoped, returning network-wide
    # figures. Establish that the caller has a scope before relying on it.
    kg_id = kindergarten_id
    if current_user.role not in [models.UserRole.ADMIN]:
        allowed_kgs = _allowed_kindergarten_ids(current_user, db)
        if not allowed_kgs:
            raise HTTPException(status_code=403, detail="Access denied")
        kg_id = current_user.kindergarten_id or allowed_kgs[0]
    
    # Summary stats.
    #
    # These three counts used to run unscoped while every KPI below them already
    # honoured kg_id. A manager or supervisor is bound to exactly one
    # kindergarten, but this block answered with network-wide totals:
    # total_kindergartens returned every active kindergarten in the country,
    # total_children every child in the system, and total_staff every active
    # manager and supervisor — regardless of who was asking. They now use the
    # same kg_id the scoping block above established.
    #
    # kg_id is None only for an ADMIN who asked for no particular kindergarten,
    # which is the one case where network-wide totals are the correct answer.
    kindergartens_query = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    )
    if kg_id:
        kindergartens_query = kindergartens_query.filter(models.Kindergarten.id == kg_id)
    total_kindergartens = kindergartens_query.count()

    children_query = db.query(models.Child)
    if kg_id:
        # Children carry no kindergarten_id; enrolment is the link. Same
        # subquery the attendance endpoint above uses, so the two agree.
        scoped_child_ids = db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.kindergarten_id == kg_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
        ).scalar_subquery()
        children_query = children_query.filter(models.Child.id.in_(scoped_child_ids))
    total_children = children_query.count()

    staff_query = db.query(models.User).filter(
        models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
        models.User.status == models.UserStatus.ACTIVE
    )
    if kg_id:
        staff_query = staff_query.filter(models.User.kindergarten_id == kg_id)
    total_staff = staff_query.count()
    
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
        kpis["attendance_rate"] = min(round((attendance_count / expected * 100) if expected > 0 else 0, 2), 100.0)
        
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
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
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
            governorate_filter(models.Kindergarten.governorate, gov_name)
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
                *jordan_date_range_filter(models.User.created_at, mo_start, mo_end),
                models.User.deleted_at.is_(None),
            ).count()
        )
        kg_mo_q = db.query(models.Kindergarten).filter(
            *jordan_date_range_filter(models.Kindergarten.created_at, mo_start, mo_end),
        )
        if kg_ids_filter:
            kg_mo_q = kg_mo_q.filter(models.Kindergarten.id.in_(kg_ids_filter))
        monthly_kgs.append(kg_mo_q.count())

        ea_mo_q = db.query(models.EnrollmentApplication).filter(
            *jordan_date_range_filter(models.EnrollmentApplication.created_at, mo_start, mo_end),
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
        *jordan_date_range_filter(models.User.created_at, period_start, period_end),
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
        *jordan_date_range_filter(models.Kindergarten.created_at, period_start, period_end),
    ).count()

    # ── Enrollment applications ─────────────────────────────────────────────────
    ea_q = db.query(models.EnrollmentApplication)
    if kg_ids:
        ea_q = ea_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))

    ea_total      = ea_q.count()
    status_counts = {s.value: ea_q.filter(models.EnrollmentApplication.status == s).count()
                     for s in models.EnrollmentStatus}
    ea_new        = ea_q.filter(
        *jordan_date_range_filter(models.EnrollmentApplication.created_at, period_start, period_end),
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
            "label_ar": "حضانات لا تزال في مرحلة المسودة",
            "action_ar": "مراجعة الحضانات المعلقة",
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
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Request an async export job"""
    _validate_csrf_token(request)
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
        trace_url="/admin/audit-logs" if job.status == models.ExportStatus.FAILED else None,
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

        # Export uses the SAME per-domain engine as the preview, so downloads
        # match exactly what the user previewed (all rows, honoring all filters).
        job_user = db.query(models.User).filter(models.User.id == job.user_id).first()
        lang = filters.get("lang") or "en"
        try:
            result = compute_report_preview(
                db, job_user, job.report_type, period_start, period_end, filters,
                sample_limit=None,
            )
            data_list = list(result.sample_data or [])
            if not data_list:
                # Aggregate reports have no per-record rows; export the KPI summary.
                label_key = "label_en" if lang == "en" else "label_ar"
                data_list = [
                    {
                        "Metric": k.get(label_key) or k.get("label_en") or k.get("id"),
                        "Value": k.get("value"),
                        "Unit": k.get("unit", ""),
                    }
                    for k in (result.kpis or [])
                ]
        except Exception as exc:
            logger.error("export dataset build failed for %s: %s", job.report_type, exc, exc_info=True)
            data_list = []
        if not data_list:
            data_list = [{"Message": "No data for the selected report and filters."}]

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
                *jordan_date_range_filter(models.ActiveAlert.triggered_at, _prev[0], _prev[1]),
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
            risk_label_ar=f"{below_target} حضانات أقل من الحد الأدنى",
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
            rec_ar = "مراجعة سياسات الحضور والغياب للحضانة"
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
        description_ar="ملخص الحضور والغياب لجميع الحضانات",
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
            {"id": "absence_by_kg", "type": "bar", "label_ar": "الغياب حسب الحضانة", "label_en": "Absence by Kindergarten"},
        ],
        columns=[
            {"key": "date", "label_ar": "التاريخ", "label_en": "Date"},
            {"key": "kindergarten", "label_ar": "الحضانة", "label_en": "Kindergarten"},
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
            {"key": "kindergarten", "label_ar": "الحضانة", "label_en": "Kindergarten"},
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
            {"key": "kindergarten", "label_ar": "الحضانة", "label_en": "Kindergarten"},
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
            {"id": "enrollment_funnel", "type": "bar", "label_ar": "مراحل التسجيل", "label_en": "Enrollment Funnel"},
            {"id": "source_breakdown", "type": "doughnut", "label_ar": "توزيع المصادر", "label_en": "Source Breakdown"},
        ],
        columns=[
            {"key": "child_name", "label_ar": "الطفل", "label_en": "Child"},
            {"key": "parent_name", "label_ar": "الوصي", "label_en": "Parent"},
            {"key": "kindergarten", "label_ar": "الحضانة", "label_en": "Kindergarten"},
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


def compute_report_preview(
    db,
    current_user,
    report_type,
    period_start,
    period_end,
    filters,
    *,
    sample_limit=10,
):
    """Compute a report preview/dataset for the given type + filters.

    Shared by the preview endpoint (sample_limit=10) and the export worker
    (sample_limit=None -> all rows). Scope/role must already be established by
    the caller; this function only reads data.
    """
    from datetime import datetime, timezone
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
            from sqlalchemy import func, or_
            # Filter by the Amman-day bounds expressed in UTC (utc_start/utc_end)
            # rather than PostgreSQL's timezone() function, so this works on both
            # SQLite (dev) and PostgreSQL (prod).
            inc_base = db.query(models.Incident).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
            )
            if kg_filter: inc_base = inc_base.filter(models.Incident.kindergarten_id.in_(kg_filter))

            statuses = filters.get("statuses", [])
            if statuses:
                # Resolve incoming values to IncidentStatus members by NAME
                # (e.g. "OPEN") so the filter matches regardless of the enum's
                # display value ("Open").
                _inc_statuses = [
                    getattr(models.IncidentStatus, str(s).upper(), None) for s in statuses
                ]
                _inc_statuses = [m for m in _inc_statuses if m is not None]
                if _inc_statuses:
                    inc_base = inc_base.filter(models.Incident.status.in_(_inc_statuses))

            severities = filters.get("severities", [])
            if severities:
                inc_base = inc_base.filter(models.Incident.severity_level.in_(severities))

            incident_types = filters.get("incident_types", [])
            if incident_types:
                inc_base = inc_base.filter(models.Incident.type.in_(incident_types))

            sla_status = (filters.get("sla_status") or "").strip()
            if sla_status == "overdue":
                inc_base = inc_base.filter(
                    models.Incident.closed_at.is_(None),
                    models.Incident.followup_sla_deadline.isnot(None),
                    models.Incident.followup_sla_deadline < _jordan_now(),
                )
            elif sla_status == "on_track":
                inc_base = inc_base.filter(
                    or_(
                        models.Incident.closed_at.isnot(None),
                        models.Incident.followup_sla_deadline.is_(None),
                        models.Incident.followup_sla_deadline >= _jordan_now(),
                    )
                )

            parent_informed = (filters.get("parent_informed") or "").strip()
            if parent_informed == "yes":
                inc_base = inc_base.filter(models.Incident.parent_informed.is_(True))
            elif parent_informed == "no":
                inc_base = inc_base.filter(models.Incident.parent_informed.is_(False))

            kpis[0]["value"] = inc_base.count()
            kpis[1]["value"] = inc_base.filter(models.Incident.status == models.IncidentStatus.OPEN).count()
            kpis[2]["value"] = inc_base.filter(models.Incident.severity_level == models.SeverityLevel.CRITICAL).count()
            total_records = kpis[0]["value"]

            trend_data = db.query(
                func.date(models.Incident.occurred_at).label("d"),
                func.count(models.Incident.id),
            ).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
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
            {"id": "enrollment_funnel", "type": "bar", "label_ar": "مراحل التسجيل", "label_en": "Enrollment Funnel"},
            {"id": "source_breakdown", "type": "doughnut", "label_ar": "توزيع المصادر", "label_en": "Source Breakdown"},
        ]
        try:
            # District narrows the kindergarten scope for enrollment.
            effective_kgs = kg_filter
            district = (filters.get("district") or "").strip()
            if district:
                dq = db.query(models.Kindergarten.id).filter(models.Kindergarten.district == district)
                if kg_filter:
                    dq = dq.filter(models.Kindergarten.id.in_(kg_filter))
                effective_kgs = [r[0] for r in dq.all()]
            analytics = get_enrollment_analytics(
                db, period_start, period_end,
                kindergarten_ids=effective_kgs,
                statuses=filters.get("statuses"),
                sources=filters.get("sources"),
                reviewer_ids=[int(r) for r in (filters.get("reviewer_ids") or []) if str(r).strip()],
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
                *jordan_date_range_filter(models.EnrollmentApplication.created_at, period_start, period_end)
            )
            if effective_kgs: source_q = source_q.filter(models.EnrollmentApplication.kindergarten_id.in_(effective_kgs))
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
            from sqlalchemy import func
            query = db.query(models.AuditLog).filter(
                models.AuditLog.created_at >= utc_start,
                models.AuditLog.created_at <= utc_end,
            )
            # AuditLog has no kindergarten_id, so governorate/kindergarten scope
            # cannot apply here; audit is filtered by sensitivity and actor role.
            sensitivity_level = filters.get("sensitivity_level")
            if sensitivity_level not in (None, ""):
                try:
                    query = query.filter(models.AuditLog.sensitivity_level == int(sensitivity_level))
                except (TypeError, ValueError):
                    pass
            actor_role = (filters.get("actor_role") or "").strip()
            if actor_role:
                query = query.filter(models.AuditLog.actor_role == actor_role)

            total_records = query.count()
            kpis[0]["value"] = total_records
            # Count high sensitivity as "failed" proxy
            high_risk = query.filter(models.AuditLog.sensitivity_level >= 3).count()
            kpis[1]["value"] = high_risk

            # Actions by module (entity type)
            mod_data = query.with_entities(
                models.AuditLog.entity_type, func.count(models.AuditLog.id)
            ).group_by(models.AuditLog.entity_type).all()
            charts[0]["data"] = {
                "labels": [{"ar": (m[0] or "—"), "en": (m[0] or "—")} for m in mod_data],
                "datasets": [{"label": {"ar": "الإجراءات", "en": "Actions"}, "data": [m[1] for m in mod_data], "backgroundColor": "#4F46E5"}],
            }
        except Exception:
            warnings.append({"ar": "تعذر تحميل سجل التدقيق", "en": "Failed to load audit log data"})

    elif report_type == "staff_training":
        kpis = [
            {"id": "trained_count", "label_ar": "موظفون مدرَّبون", "label_en": "Trained Staff", "value": 0, "unit": ""},
            {"id": "training_rate", "label_ar": "معدل التدريب", "label_en": "Training Rate", "value": 0, "unit": "%"},
            {"id": "ratio_compliant", "label_ar": "حضانات ملتزمة بالنسب", "label_en": "Ratio-Compliant KGs", "value": 0, "unit": ""},
            {"id": "ratio_violations", "label_ar": "مخالفات النسب", "label_en": "Ratio Violations", "value": 0, "unit": ""},
            {"id": "avg_compliance_score", "label_ar": "متوسط درجة الامتثال", "label_en": "Avg Compliance Score", "value": 0, "unit": "%"},
        ]
        charts = [
            {"id": "training_by_kg", "type": "bar", "label_ar": "التدريب حسب الحضانة", "label_en": "Training by KG"},
            {"id": "ratio_compliance_dist", "type": "doughnut", "label_ar": "توزيع امتثال النسب", "label_en": "Ratio Compliance Distribution"},
        ]
        try:
            from sqlalchemy import func
            # Map the UI training-status filter (passed/failed) onto the real
            # TrainingStatus enum. Default to COMPLETED (the "trained" definition).
            _ts_map = {
                "PASSED": models.TrainingStatus.COMPLETED,
                "COMPLETED": models.TrainingStatus.COMPLETED,
                "FAILED": models.TrainingStatus.OVERDUE,
                "OVERDUE": models.TrainingStatus.OVERDUE,
                "PENDING": models.TrainingStatus.PENDING,
            }
            _completion_status = _ts_map.get(
                (filters.get("training_status") or "").strip().upper(),
                models.TrainingStatus.COMPLETED,
            )
            stc_q = db.query(func.count(models.StaffTrainingCompletion.id)).filter(
                models.StaffTrainingCompletion.completion_date >= period_start,
                models.StaffTrainingCompletion.completion_date <= period_end,
                models.StaffTrainingCompletion.status == _completion_status,
            )
            if kg_filter:
                stc_q = stc_q.filter(models.StaffTrainingCompletion.kindergarten_id.in_(kg_filter))
            kpis[0]["value"] = stc_q.scalar() or 0

            # Total staff (users with SUPERVISOR role)
            total_supervisors = db.query(func.count(models.User.id)).filter(
                models.User.role == models.UserRole.SUPERVISOR,
                models.User.deleted_at.is_(None),
            ).scalar() or 0
            kpis[1]["value"] = round(kpis[0]["value"] / total_supervisors * 100, 1) if total_supervisors > 0 else 0.0

            # Ratio compliance derived from operating vs. compliant minutes.
            rc_q = db.query(models.RatioCompliance).filter(
                models.RatioCompliance.date >= period_start,
                models.RatioCompliance.date <= period_end,
            )
            if kg_filter:
                rc_q = rc_q.filter(models.RatioCompliance.kindergarten_id.in_(kg_filter))
            rc_rows = rc_q.all()
            total_rc = len(rc_rows)
            compliant = sum(
                1 for r in rc_rows
                if (r.operating_minutes or 0) > 0 and r.compliant_minutes >= r.operating_minutes
            )
            kpis[2]["value"] = compliant
            kpis[3]["value"] = total_rc - compliant
            scores = [
                (r.compliant_minutes / r.operating_minutes) * 100
                for r in rc_rows if (r.operating_minutes or 0) > 0
            ]
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
                models.StaffTrainingCompletion.completion_date >= period_start,
                models.StaffTrainingCompletion.completion_date <= period_end,
                models.StaffTrainingCompletion.status == _completion_status,
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
            from sqlalchemy import func, or_
            now_dt = _jordan_now()
            inc_q = db.query(models.Incident).filter(
                models.Incident.occurred_at >= utc_start,
                models.Incident.occurred_at <= utc_end,
                models.Incident.deleted_at.is_(None),
            )
            if kg_filter:
                inc_q = inc_q.filter(models.Incident.kindergarten_id.in_(kg_filter))

            incident_types = filters.get("incident_types", [])
            if incident_types:
                inc_q = inc_q.filter(models.Incident.type.in_(incident_types))

            sla_status = (filters.get("sla_status") or "").strip()
            if sla_status == "overdue":
                inc_q = inc_q.filter(
                    models.Incident.closed_at.is_(None),
                    models.Incident.followup_sla_deadline.isnot(None),
                    models.Incident.followup_sla_deadline < now_dt,
                )
            elif sla_status == "on_track":
                inc_q = inc_q.filter(
                    or_(
                        models.Incident.closed_at.isnot(None),
                        models.Incident.followup_sla_deadline.is_(None),
                        models.Incident.followup_sla_deadline >= now_dt,
                    )
                )

            parent_informed = (filters.get("parent_informed") or "").strip()
            if parent_informed == "yes":
                inc_q = inc_q.filter(models.Incident.parent_informed.is_(True))
            elif parent_informed == "no":
                inc_q = inc_q.filter(models.Incident.parent_informed.is_(False))

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
                key = to_jordan_date(i.occurred_at).strftime("%Y-%m") if i.occurred_at else "unknown"
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
            district = (filters.get("district") or "").strip()
            if district:
                kg_q = kg_q.filter(models.Kindergarten.district == district)
            kgs = kg_q.all()
            kg_ids = [kg.id for kg in kgs]

            total_cap = sum((kg.total_capacity or 0) for kg in kgs)
            kpis[0]["value"] = total_cap

            # Per-kindergarten active enrollment, so utilization is accurate.
            enrolled_by_kg = {}
            if kg_ids:
                enrolled_by_kg = dict(
                    db.query(
                        models.EnrollmentApplication.kindergarten_id,
                        func.count(models.EnrollmentApplication.id),
                    ).filter(
                        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
                        models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                    ).group_by(models.EnrollmentApplication.kindergarten_id).all()
                )
            enrolled_cnt = sum(enrolled_by_kg.values())
            kpis[1]["value"] = enrolled_cnt
            kpis[2]["value"] = round(enrolled_cnt / total_cap * 100, 1) if total_cap > 0 else 0.0
            kpis[4]["value"] = max(0, total_cap - enrolled_cnt)

            waitlist = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
            )
            if kg_ids:
                waitlist = waitlist.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
            kpis[3]["value"] = waitlist.scalar() or 0

            total_records = len(kgs)

            # Capacity by governorate
            gov_cap = {}
            for kg in kgs:
                gov = kg.governorate or "Other"
                gov_cap[gov] = gov_cap.get(gov, 0) + (kg.total_capacity or 0)
            charts[0]["data"] = {
                "labels": [{"ar": g, "en": g} for g in gov_cap],
                "datasets": [{"label": {"ar": "السعة", "en": "Capacity"}, "data": list(gov_cap.values()), "backgroundColor": "#4F46E5"}],
            }

            # Utilization distribution: low/medium/high, computed per kindergarten.
            low = med = high = 0
            for kg in kgs:
                cap = kg.total_capacity or 0
                if cap <= 0:
                    continue
                ratio = enrolled_by_kg.get(kg.id, 0) / cap
                if ratio < 0.5:
                    low += 1
                elif ratio < 0.85:
                    med += 1
                else:
                    high += 1
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
            {"id": "active_kgs", "label_ar": "الحضانات الفعّالة", "label_en": "Active KGs", "value": 0, "unit": ""},
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
            if (att_days_q.scalar() or 0) == 0:
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
            logs = logs.limit(sample_limit).all()
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
            incs = incs.limit(sample_limit).all()
            _inc_kg_ids = list({inc.kindergarten_id for inc in incs if inc.kindergarten_id})
            _inc_kg_map = {k.id: k for k in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(_inc_kg_ids)).all()}
            for inc in incs:
                kg = _inc_kg_map.get(inc.kindergarten_id)
                sample_data.append({
                    "date": to_jordan_date(inc.occurred_at).isoformat(),
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
            apps = apps.limit(sample_limit).all()
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
            ).limit(sample_limit).all()
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


@router.post("/reports/preview", response_model=ReportPreviewResponse)
def preview_report(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Generate a preview payload for the requested report configuration."""
    _validate_csrf_token(request)
    validators.validate_admin_role(current_user)
    report_type = payload.get("report_type")
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    filters = payload.get("filters", {}) or {}

    if not report_type or not period_start or not period_end:
        raise HTTPException(status_code=400, detail="report_type, period_start, and period_end are required")

    from datetime import datetime

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

    return compute_report_preview(db, current_user, report_type, period_start, period_end, filters)



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
    request: Request = None,
):
    """Save a report configuration as a reusable template."""
    _validate_csrf_token(request)
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
    request: Request = None,
):
    """Create a scheduled report."""
    _validate_csrf_token(request)
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
        # One bulk pass for the whole network before the loop; without it this is
        # a full KPI bundle per kindergarten.
        AnalyticsService._warm_governance_memo(
            db, [kg.id for kg in kindergartens], period_start, period_end
        )
        for kg in kindergartens:
            _, band = AnalyticsService._kg_governance_score_and_band(db, kg.id, period_start, period_end)
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
                    governorate_filter(models.Kindergarten.governorate, gov_name),
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
                children_q = children_q.filter(governorate_filter(models.Kindergarten.governorate, gov_name))
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
                capacity_q = capacity_q.filter(governorate_filter(models.Kindergarten.governorate, gov_name))
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
            attendance_rate = min((attendance_days / 30.0) * 100, 100.0)
            risk_children.append({
                "child_id": child.id,
                "kindergarten_id": kg_id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_name": kg_name_map.get(kg_id, "Unknown"),
                "risk_type": "Low Attendance",
                "risk_value": round(attendance_rate, 1),
                "description": f"Attendance rate: {round(attendance_rate, 1)}%",
            })
        for child, incident_count, kg_id in recent_incidents:
            risk_children.append({
                "child_id": child.id,
                "kindergarten_id": kg_id,
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
        """Network-wide attendance rate via the canonical KPIService definition.

        Was a looser calendar-day formula — every attendance log (any status) over the
        window divided by active_enrollments × calendar_days — which counted absences as
        attendance, ignored working days, and disagreed with kg-overview and the KPI
        dashboard for the same data. It now sums the canonical (attended, expected)
        child-days over the scope, so a network number matches the sum of its parts.
        """
        if kg_ids is None:
            kg_ids = [
                kid for (kid,) in db.query(models.Kindergarten.id).filter(
                    models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                    models.Kindergarten.deleted_at.is_(None),
                ).all()
            ]
        if not kg_ids:
            return 0.0

        components = KPIService.compute_attendance_components_bulk(
            db, kg_ids, period_start, period_end
        )
        attended = sum(a for a, _ in components.values())
        expected = sum(e for _, e in components.values())
        return round((attended / expected) * 100, 2) if expected > 0 else 0.0

    @staticmethod
    def _compute_network_incident_rate(db: Session, period_start: date, period_end: date, kg_ids: Optional[List[int]] = None) -> float:
        """Compute network-wide incident rate per 1,000 attended child-days"""
        # Count total incidents
        incident_q = db.query(func.count(models.Incident.id)).filter(
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
        )
        if kg_ids:
            incident_q = incident_q.filter(models.Incident.kindergarten_id.in_(kg_ids))
        total_incidents = incident_q.scalar() or 0

        # Subquery avoids Cartesian product when filtering by KG scope
        if kg_ids:
            scope_child_sq = db.query(models.EnrollmentApplication.child_id).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            ).distinct().scalar_subquery()
            child_days_q = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([
                    models.AttendanceStatus.PRESENT,
                    models.AttendanceStatus.LATE,
                ]),
                models.AttendanceLog.child_id.in_(scope_child_sq),
            )
        else:
            child_days_q = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end,
                models.AttendanceLog.status.in_([
                    models.AttendanceStatus.PRESENT,
                    models.AttendanceStatus.LATE,
                ]),
            )
        total_child_days = child_days_q.scalar() or 0
        if total_child_days == 0:
            return 0.0

        return round((total_incidents / total_child_days) * 1000, 3)

    @staticmethod
    def _compute_network_serious_incident_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide serious incident rate per 1,000 attended child-days"""
        # Count serious incidents
        serious_incidents = db.query(func.count(models.Incident.id)).filter(
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end),
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

        # One bulk pass for the whole network before the loop; without it this is
        # a full KPI bundle per kindergarten.
        AnalyticsService._warm_governance_memo(
            db, [kg.id for kg in kindergartens], period_start, period_end
        )
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
                governorate_filter(models.Kindergarten.governorate, governorate),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).all()
            kg_ids = [kg_id for (kg_id,) in kg_rows]

        if not kg_ids:
            return 0.0

        # Canonical definition over the governorate's kindergartens — same helper the
        # network rate above uses, so governorate and network agree with each other and
        # with kg-overview / the KPI dashboard. (Was the looser calendar-day formula.)
        components = KPIService.compute_attendance_components_bulk(
            db, kg_ids, period_start, period_end
        )
        attended = sum(a for a, _ in components.values())
        expected = sum(e for _, e in components.values())
        return round((attended / expected) * 100, 2) if expected > 0 else 0.0

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
                governorate_filter(models.Kindergarten.governorate, governorate),
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).all()
            kg_ids = [kg_id for (kg_id,) in kg_rows]

        if not kg_ids:
            return 0.0

        # Count incidents
        incidents = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id.in_(kg_ids),
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
        ).scalar() or 0

        # Subquery avoids Cartesian product from joining through enrollment
        child_sq = db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).distinct().scalar_subquery()

        child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end,
            models.AttendanceLog.status.in_([
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.LATE,
            ]),
            models.AttendanceLog.child_id.in_(child_sq),
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
            kg_query = kg_query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
        kindergartens = kg_query.all()

        if not kindergartens:
            return 0.0

        total_score = 0.0
        count = 0

        # One bulk pass for the whole network before the loop; without it this is
        # a full KPI bundle per kindergarten.
        AnalyticsService._warm_governance_memo(
            db, [kg.id for kg in kindergartens], period_start, period_end
        )
        for kg in kindergartens:
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)
            if score > 0:
                total_score += score
                count += 1

        return round(total_score / count, 2) if count > 0 else 0.0

    @staticmethod
    def _warm_governance_memo(
        db: Session,
        kindergarten_ids: List[int],
        period_start: date,
        period_end: date,
    ) -> None:
        """Fill the (score, band) memo for a whole network in one bulk pass.

        The memo below already collapses repeated lookups for the *same*
        kindergarten within a request, but it still cost one
        compute_governance_score — and so one full KPI bundle — per
        kindergarten. Across 446 active kindergartens that is the N+1 that made
        the report preview and governance distribution exceed the request
        timeout.

        compute_kpi_bundles_bulk produces the same governance_score and
        governance_band as compute_governance_score (both read the same bundle
        fields, pinned by test_kpi_bundles_bulk_equivalence), so pre-seeding the
        memo changes timing only, never a number. Failures are swallowed on
        purpose: the memo is an optimisation, and a miss simply falls back to the
        per-kindergarten path rather than failing the request.
        """
        memo = db.info.setdefault("_governance_score_memo", {})
        missing = [
            kg_id for kg_id in kindergarten_ids
            if (kg_id, period_start, period_end) not in memo
        ]
        if not missing:
            return
        from kpi_service import KPIService
        try:
            bundles = KPIService.compute_kpi_bundles_bulk(
                db, missing, period_start, period_end
            )
        except (SQLAlchemyError, ZeroDivisionError, TypeError, ValueError):
            logger.exception(
                "Bulk governance warm-up failed for %d kindergartens; "
                "falling back to per-kindergarten computation", len(missing)
            )
            return
        for kg_id, bundle in bundles.items():
            memo[(kg_id, period_start, period_end)] = (
                float(bundle.get("governance_score", 0.0)),
                str(bundle.get("governance_band", "RED")),
            )

    @staticmethod
    def _kg_governance_score_and_band(db: Session, kindergarten_id: int, period_start: date, period_end: date) -> Tuple[float, str]:
        """Canonical (score, band) for one kindergarten/period.

        Delegates to KPIService.compute_governance_score — the single source
        of truth per project convention (KPI computations belong in
        kpi_service.py). Memoized on the request's db.info so repeated
        lookups for the same (kg, period) within one dashboard-data request
        — network summary, governorate breakdown, and governance distribution
        all need it — compute the score once instead of up to three times
        per kindergarten. This previously caused ~35s cold-cache dashboard
        loads and, since a separate "simplified GCEI" formula used to live
        here duplicating kpi_service.py's logic, could show materially
        different governance scores in different dashboard sections for the
        same kindergarten/period (e.g. 60.0 vs 40.0/RED).
        """
        from kpi_service import KPIService
        memo = db.info.setdefault("_governance_score_memo", {})
        key = (kindergarten_id, period_start, period_end)
        if key not in memo:
            try:
                score, band = KPIService.compute_governance_score(db, kindergarten_id, period_start, period_end)
                memo[key] = (float(score), str(band))
            except SQLAlchemyError:
                logger.exception("Failed to compute kindergarten governance score due to database error")
                memo[key] = (0.0, "RED")
            except (ZeroDivisionError, TypeError, ValueError):
                logger.exception("Failed to compute kindergarten governance score due to invalid analytics data")
                memo[key] = (0.0, "RED")
        return memo[key]

    @staticmethod
    def _compute_kindergarten_governance_score(db: Session, kindergarten_id: int, period_start: date, period_end: date) -> float:
        """Governance score only. See _kg_governance_score_and_band for the memoized (score, band) pair."""
        score, _band = AnalyticsService._kg_governance_score_and_band(db, kindergarten_id, period_start, period_end)
        return score

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
            ) or 0
            incident_rate = KPIService.compute_incident_rate(
                db, kindergarten_id, period_start, period_end
            ) or 0

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

        # One bulk pass for the whole scope. Calling the per-kindergarten KPI
        # computers in this loop cost a full bundle each and timed out once the
        # network reached 446 active kindergartens. The bundle carries every
        # metric this endpoint can rank, so one pass answers all four.
        bundles = KPIService.compute_kpi_bundles_bulk(
            db, [kg.id for kg in kindergartens], period_start, period_end
        )

        rankings = []
        for kg in kindergartens:
            bundle = bundles.get(kg.id) or {}
            quality = bundle.get("quality") or {}
            band = None
            if metric == "attendance_rate":
                # The bundle reports 0.0 where compute_attendance_rate returns
                # None. That distinction decides whether a kindergarten is
                # rankable at all, so recover it from the same has_data flag —
                # a 0.0 here would plant every non-reporting kindergarten at the
                # bottom of the table as though it had genuinely scored zero.
                value = bundle.get("attendance_rate")
                if not (quality.get("attendance_rate") or {}).get("has_data", False):
                    value = None
            elif metric == "incident_rate":
                value = bundle.get("incident_rate", 0.0)
            elif metric == "ratio_compliance":
                value = bundle.get("ratio_compliance", 0.0)
            elif metric == "governance_score":
                value = bundle.get("governance_score", 0.0)
                band = bundle.get("governance_band")
            else:
                value = 0

            # The KPI computers return None when the kindergarten has no data for
            # the period. Such a kindergarten cannot be ranked: coercing it to 0
            # would place it artificially at the top or bottom of the table (and
            # None would break both the sort below and RankingEntry validation).
            if value is None:
                continue

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
        attendance_rate = min((present_logs / total_logs * 100), 100.0) if total_logs else 0.0

        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.class_id == class_id,
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
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
        attendance_rate = min((present_logs / total_logs * 100), 100.0) if total_logs else 0.0

        incident_count = db.query(func.count(models.Incident.id)).filter(
            models.Incident.child_id == child_id,
            *jordan_date_range_filter(models.Incident.occurred_at, period_start, period_end)
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
            attendance_rate = min((present_logs / total_logs * 100), 100.0) if total_logs else 0.0
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
            attendance_rate = min((present_logs / total_logs * 100), 100.0) if total_logs else 0.0
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

        if attendance_rate is not None and attendance_rate < 85:
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
        # Compare aware-to-aware: db_types.UTCDateTime returns timezone-aware UTC, so
        # pairing it with _utcnow_naive() raises "can't compare offset-naive and
        # offset-aware datetimes". Query *bounds* elsewhere can stay naive — those are
        # bind parameters and the type reads naive as UTC — but this is a Python-level
        # comparison against a loaded value.
        if latest and latest.evaluated_at >= datetime.now(timezone.utc) - timedelta(hours=12):
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

        # Accuracy, timeliness, and consistency were previously derived as
        # arbitrary offsets of completeness_percent (+5%, hardcoded 90.0, +3%)
        # rather than independently measured. EnhancedDataQualityService
        # already computes real signals for each from distinct data sources
        # (report-recency for timeliness, record-validity checks for
        # accuracy, cross-entity duplicate/overflow checks for consistency)
        # and is already relied on by observability_endpoints.py — reuse it
        # here instead of maintaining a second, fake formula.
        validity = enhanced_data_quality_service.validity_check(db)
        freshness = enhanced_data_quality_service.freshness_latency(db)
        consistency = enhanced_data_quality_service.cross_entity_consistency(db)
        accuracy_score = validity["validity_score"]
        timeliness_score = freshness["score"]
        consistency_score = consistency["consistency_score"]

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
                "accuracy_issues": validity["issues"],
                "timeliness_hours_since_last_report": freshness["hours_since_last_report"],
                "consistency_issues": consistency["issues"],
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
        attendance_rate = min(round((attended / expected) * 100, 2) if expected > 0 else 0.0, 100.0)
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
        attendance_rate = min(round((attended / total_days) * 100, 2), 100.0)
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
            governorate_filter(models.Kindergarten.governorate, gov),
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
        attendance_rate = min(round((attended / expected_total) * 100, 2) if expected_total > 0 else 0.0, 100.0)
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
