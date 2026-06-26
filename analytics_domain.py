"""Analytics domain schemas and core computation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

import models


ALLOWED_PREDICT_METRICS = {
    "attendance_forecast",
    "incident_prediction",
    "enrollment_trend",
}


class PredictRequest(BaseModel):
    scope_type: str
    scope_id: Optional[str] = None
    start_date: date
    end_date: date
    horizon_days: int = Field(default=30, ge=1, le=180)


class ScopeInfo(BaseModel):
    scope_type: str
    scope_id: Optional[str] = None
    label: Optional[str] = None


class SeriesPoint(BaseModel):
    date: date
    value: float


class PredictResponse(BaseModel):
    metric: str
    scope: ScopeInfo
    points: List[SeriesPoint]
    forecast_points: List[SeriesPoint]
    confidence: Dict[str, List[SeriesPoint]]
    model_meta: Dict[str, object]


class AnomalyRecord(BaseModel):
    id: int
    metric_type: str
    scope_type: str
    scope_id: Optional[str]
    detected_at: date
    score: float
    severity: str
    message: str
    ack_status: bool


class DrilldownResponse(BaseModel):
    scope: Dict[str, object]
    kpis: Dict[str, object]
    charts: Dict[str, object]
    breakdowns: Dict[str, object]
    top_bottom_lists: Dict[str, object]
    risk: Dict[str, object]
    metadata: Dict[str, object]


class ThresholdRequest(BaseModel):
    metric_type: str
    scope_type: str
    scope_id: Optional[str] = None
    operator: str
    threshold_value: float
    window_days: int = Field(default=30, ge=1, le=365)
    severity: str = "MEDIUM"
    is_active: bool = True


class ActionPlanRequest(BaseModel):
    recommendation_id: Optional[int] = None
    kindergarten_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


class TargetRequest(BaseModel):
    metric_type: str
    scope_type: str
    scope_id: Optional[str] = None
    target_value: float
    effective_date: date


class DataQualityResult(BaseModel):
    entity_type: str
    entity_id: Optional[str]
    completeness_percent: float
    accuracy_score: float
    timeliness_score: float
    consistency_score: float
    evaluated_at: datetime
    details: Dict[str, object]


@dataclass
class RegressionResult:
    slope: float
    intercept: float
    stddev: float


def hash_params(metric: str, scope_type: str, scope_id: Optional[str], start: date, end: date, horizon: int) -> str:
    raw = f"{metric}|{scope_type}|{scope_id}|{start.isoformat()}|{end.isoformat()}|{horizon}"
    return sha256(raw.encode("utf-8")).hexdigest()


def linear_regression(series: List[SeriesPoint]) -> RegressionResult:
    if len(series) < 2:
        return RegressionResult(0.0, series[0].value if series else 0.0, 0.0)

    xs = list(range(len(series)))
    ys = [p.value for p in series]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    denom = sum((x - x_mean) ** 2 for x in xs) or 1.0
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    intercept = y_mean - slope * x_mean

    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    variance = sum(r ** 2 for r in residuals) / max(n - 2, 1)
    stddev = variance ** 0.5
    return RegressionResult(slope=slope, intercept=intercept, stddev=stddev)


def build_forecast(series: List[SeriesPoint], horizon_days: int) -> Tuple[List[SeriesPoint], Dict[str, List[SeriesPoint]], Dict[str, object]]:
    if not series:
        return [], {"lower": [], "upper": []}, {"model_version": "linear_v1", "confidence": 0.0}

    regression = linear_regression(series)
    last_date = series[-1].date
    forecast_points: List[SeriesPoint] = []
    lower_band: List[SeriesPoint] = []
    upper_band: List[SeriesPoint] = []

    for idx in range(1, horizon_days + 1):
        x = len(series) - 1 + idx
        value = max(0.0, regression.slope * x + regression.intercept)
        forecast_date = last_date + timedelta(days=idx)
        margin = regression.stddev * 1.96
        forecast_points.append(SeriesPoint(date=forecast_date, value=round(value, 2)))
        lower_band.append(SeriesPoint(date=forecast_date, value=round(max(0.0, value - margin), 2)))
        upper_band.append(SeriesPoint(date=forecast_date, value=round(value + margin, 2)))

    meta = {
        "model_version": "linear_v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "confidence": round(max(0.1, 1.0 - regression.stddev / max(abs(series[-1].value), 1.0)), 2),
        "slope": round(regression.slope, 4),
    }
    return forecast_points, {"lower": lower_band, "upper": upper_band}, meta


def z_score_anomalies(series: List[SeriesPoint]) -> List[Tuple[SeriesPoint, float, models.SeverityLevel]]:
    if len(series) < 5:
        return []
    values = [p.value for p in series]
    mean_val = sum(values) / len(values)
    variance = sum((v - mean_val) ** 2 for v in values) / max(len(values) - 1, 1)
    stddev = variance ** 0.5 or 1.0

    anomalies = []
    for point in series:
        score = (point.value - mean_val) / stddev
        abs_score = abs(score)
        if abs_score >= 2.0:
            if abs_score >= 3.0:
                severity = models.SeverityLevel.HIGH
            elif abs_score >= 2.5:
                severity = models.SeverityLevel.MEDIUM
            else:
                severity = models.SeverityLevel.LOW
            anomalies.append((point, round(score, 2), severity))
    return anomalies


def scoped_kindergarten_ids(db: Session, scope_type: str, scope_id: Optional[str]) -> List[int]:
    if scope_type == "NETWORK":
        return [kg.id for kg in db.query(models.Kindergarten.id).all()]
    if scope_type == "GOVERNORATE" and scope_id:
        return [kg.id for kg in db.query(models.Kindergarten.id).filter(models.Kindergarten.governorate == scope_id).all()]
    if scope_type == "KINDERGARTEN" and scope_id:
        return [int(scope_id)]
    return []


def attendance_series(db: Session, scope_type: str, scope_id: Optional[str], start: date, end: date) -> List[SeriesPoint]:
    series: List[SeriesPoint] = []
    current = start
    kg_ids = scoped_kindergarten_ids(db, scope_type, scope_id)

    while current <= end:
        attendance_q = db.query(func.count(models.AttendanceLog.id)).filter(models.AttendanceLog.date == current)
        if scope_type == "CLASS" and scope_id:
            attendance_q = attendance_q.filter(models.AttendanceLog.class_id == int(scope_id))
        elif scope_type == "CHILD" and scope_id:
            attendance_q = attendance_q.filter(models.AttendanceLog.child_id == int(scope_id))
        elif kg_ids:
            attendance_q = attendance_q.join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
            )
        total_logs = attendance_q.scalar() or 0

        present_q = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date == current,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        )
        if scope_type == "CLASS" and scope_id:
            present_q = present_q.filter(models.AttendanceLog.class_id == int(scope_id))
        elif scope_type == "CHILD" and scope_id:
            present_q = present_q.filter(models.AttendanceLog.child_id == int(scope_id))
        elif kg_ids:
            present_q = present_q.join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
            )
        present_logs = present_q.scalar() or 0

        value = round((present_logs / total_logs) * 100, 2) if total_logs else 0.0
        series.append(SeriesPoint(date=current, value=value))
        current += timedelta(days=1)

    return series


def incident_series(db: Session, scope_type: str, scope_id: Optional[str], start: date, end: date) -> List[SeriesPoint]:
    series: List[SeriesPoint] = []
    current = start
    while current <= end:
        incident_q = db.query(func.count(models.Incident.id)).filter(func.date(models.Incident.occurred_at) == current)
        if scope_type == "KINDERGARTEN" and scope_id:
            incident_q = incident_q.filter(models.Incident.kindergarten_id == int(scope_id))
        elif scope_type == "CLASS" and scope_id:
            incident_q = incident_q.filter(models.Incident.class_id == int(scope_id))
        elif scope_type == "CHILD" and scope_id:
            incident_q = incident_q.filter(models.Incident.child_id == int(scope_id))
        elif scope_type == "GOVERNORATE" and scope_id:
            incident_q = incident_q.join(models.Kindergarten).filter(models.Kindergarten.governorate == scope_id)
        count = incident_q.scalar() or 0
        series.append(SeriesPoint(date=current, value=float(count)))
        current += timedelta(days=1)
    return series


def enrollment_series(db: Session, scope_type: str, scope_id: Optional[str], start: date, end: date) -> List[SeriesPoint]:
    series: List[SeriesPoint] = []
    current = start
    while current <= end:
        enroll_q = db.query(func.count(models.EnrollmentApplication.id)).filter(func.date(models.EnrollmentApplication.created_at) == current)
        if scope_type == "KINDERGARTEN" and scope_id:
            enroll_q = enroll_q.filter(models.EnrollmentApplication.kindergarten_id == int(scope_id))
        elif scope_type == "CLASS" and scope_id:
            enroll_q = enroll_q.filter(models.EnrollmentApplication.class_id == int(scope_id))
        elif scope_type == "CHILD" and scope_id:
            enroll_q = enroll_q.filter(models.EnrollmentApplication.child_id == int(scope_id))
        elif scope_type == "GOVERNORATE" and scope_id:
            enroll_q = enroll_q.join(models.Kindergarten).filter(models.Kindergarten.governorate == scope_id)
        count = enroll_q.scalar() or 0
        series.append(SeriesPoint(date=current, value=float(count)))
        current += timedelta(days=1)
    return series
