"""Predictive analytics service backed by historical ORM data."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from utils.time_utils import today_amman as _today
from enum import Enum
from math import sqrt
from typing import Dict, List, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


class PredictionType(Enum):
    ATTENDANCE = "attendance"
    INCIDENTS = "incidents"
    CAPACITY = "capacity"
    ENROLLMENT = "enrollment"


class ModelType(Enum):
    LINEAR = "linear"


@dataclass
class Prediction:
    prediction_type: PredictionType
    predicted_value: float
    confidence_interval: List[float]
    confidence_level: float
    model_used: ModelType
    accuracy_score: float
    historical_data_points: int
    prediction_date: date
    forecast_period_days: int


@dataclass
class TrendAnalysis:
    trend_direction: str
    trend_strength: float
    seasonality_detected: bool
    change_points: List[datetime]
    forecast_values: List[float]
    forecast_dates: List[date]
    r_squared: float
    mean_absolute_error: float


class PredictiveAnalytics:
    """Simple linear-trend forecaster for attendance, incidents, and capacity."""

    @staticmethod
    def _linear_fit(values: Sequence[float]) -> Tuple[float, float, float, float, float]:
        """Return slope, intercept, r2, mae, stddev."""
        n = len(values)
        if n == 0:
            raise ValueError("No historical data points available")
        if n == 1:
            return 0.0, values[0], 1.0, 0.0, 0.0

        x_vals = list(range(n))
        mean_x = sum(x_vals) / n
        mean_y = sum(values) / n

        ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, values))
        ss_xx = sum((x - mean_x) ** 2 for x in x_vals)
        slope = ss_xy / ss_xx if ss_xx else 0.0
        intercept = mean_y - (slope * mean_x)

        fitted = [intercept + slope * x for x in x_vals]
        residuals = [y - yhat for y, yhat in zip(values, fitted)]
        mae = sum(abs(r) for r in residuals) / n
        variance = sum((r - (sum(residuals) / n)) ** 2 for r in residuals) / n
        stddev = sqrt(max(0.0, variance))

        ss_tot = sum((y - mean_y) ** 2 for y in values)
        ss_res = sum((y - yhat) ** 2 for y, yhat in zip(values, fitted))
        r2 = 1.0 if ss_tot == 0 else max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))
        return slope, intercept, r2, mae, stddev

    @staticmethod
    def _predict_at_index(slope: float, intercept: float, idx: int) -> float:
        return (slope * idx) + intercept

    @staticmethod
    def _bound_percent(value: float) -> float:
        return max(0.0, min(100.0, value))

    @staticmethod
    def _date_buckets(start: date, end: date) -> List[date]:
        days = (end - start).days
        return [start + timedelta(days=offset) for offset in range(days + 1)]

    def _attendance_series(self, db: Session, kindergarten_id: int, days_window: int = 90) -> List[float]:
        end_day = _today()
        start_day = end_day - timedelta(days=max(7, days_window))

        q_active = db.query(models.EnrollmentApplication.child_id).filter(models.EnrollmentApplication.is_active.is_(True))
        if kindergarten_id > 0:
            q_active = q_active.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
        
        active_children = q_active.distinct().count()
        if active_children <= 0:
            raise ValueError("No active children for this scope")

        q_rows = (
            db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id))
            .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
            .filter(
                models.AttendanceLog.date >= start_day,
                models.AttendanceLog.date <= end_day,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
        )
        if kindergarten_id > 0:
            q_rows = q_rows.filter(models.Class.kindergarten_id == kindergarten_id)
            
        rows = (
            q_rows.group_by(models.AttendanceLog.date)
            .order_by(models.AttendanceLog.date.asc())
            .all()
        )
        present_by_date: Dict[date, int] = {row[0]: int(row[1]) for row in rows}
        return [
            self._bound_percent((present_by_date.get(day, 0) / active_children) * 100.0)
            for day in self._date_buckets(start_day, end_day)
        ]

    def _incidents_series(self, db: Session, kindergarten_id: int, days_window: int = 120) -> List[float]:
        end_day = _today()
        start_day = end_day - timedelta(days=max(14, days_window))

        q_rows = (
            db.query(func.date(models.Incident.occurred_at), func.count(models.Incident.id))
            .filter(
                func.date(models.Incident.occurred_at) >= start_day,
                func.date(models.Incident.occurred_at) <= end_day,
            )
        )
        if kindergarten_id > 0:
            q_rows = q_rows.filter(models.Incident.kindergarten_id == kindergarten_id)
            
        rows = (
            q_rows.group_by(func.date(models.Incident.occurred_at))
            .order_by(func.date(models.Incident.occurred_at).asc())
            .all()
        )
        counts_by_date: Dict[date, int] = {}
        for day_value, count_value in rows:
            if isinstance(day_value, str):
                bucket_day = date.fromisoformat(day_value)
            elif isinstance(day_value, datetime):
                bucket_day = day_value.date()
            else:
                bucket_day = day_value
            counts_by_date[bucket_day] = int(count_value)

        return [float(counts_by_date.get(day, 0)) for day in self._date_buckets(start_day, end_day)]

    def _capacity_series(self, db: Session, kindergarten_id: int, days_window: int = 180) -> List[float]:
        end_day = _today()
        start_day = end_day - timedelta(days=max(30, days_window))

        q_cap = db.query(func.sum(models.Class.capacity_total)).filter(models.Class.is_active.is_(True))
        if kindergarten_id > 0:
            q_cap = q_cap.filter(models.Class.kindergarten_id == kindergarten_id)
            
        capacity_total = q_cap.scalar() or 0
        if capacity_total <= 0:
            raise ValueError("No class capacity configured for this scope")

        q_rows = (
            db.query(models.EnrollmentApplication.enrollment_start_date, func.count(models.EnrollmentApplication.id))
            .filter(
                models.EnrollmentApplication.is_active.is_(True),
                models.EnrollmentApplication.enrollment_start_date.isnot(None),
                models.EnrollmentApplication.enrollment_start_date >= start_day,
                models.EnrollmentApplication.enrollment_start_date <= end_day,
            )
        )
        if kindergarten_id > 0:
            q_rows = q_rows.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
            
        rows = (
            q_rows.group_by(models.EnrollmentApplication.enrollment_start_date)
            .order_by(models.EnrollmentApplication.enrollment_start_date.asc())
            .all()
        )
        by_date = {row[0]: int(row[1]) for row in rows}

        q_base = db.query(func.count(models.EnrollmentApplication.id)).filter(models.EnrollmentApplication.is_active.is_(True))
        if kindergarten_id > 0:
            q_base = q_base.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
            
        baseline_active = q_base.scalar() or 0

        cumulative = max(0, int(baseline_active) - sum(by_date.values()))
        series: List[float] = []
        for day in self._date_buckets(start_day, end_day):
            cumulative += by_date.get(day, 0)
            series.append(self._bound_percent((cumulative / capacity_total) * 100.0))
        return series

    def _build_prediction(
        self,
        prediction_type: PredictionType,
        values: Sequence[float],
        days_ahead: int,
        percent_metric: bool = True,
    ) -> Prediction:
        slope, intercept, r2, mae, stddev = self._linear_fit(values)
        future_index = len(values) - 1 + max(1, days_ahead)
        predicted_raw = self._predict_at_index(slope, intercept, future_index)
        predicted = self._bound_percent(predicted_raw) if percent_metric else max(0.0, predicted_raw)

        margin = (1.96 * stddev) if stddev > 0 else max(1.0, mae)
        lower = predicted - margin
        upper = predicted + margin
        if percent_metric:
            lower = self._bound_percent(lower)
            upper = self._bound_percent(upper)
        else:
            lower = max(0.0, lower)
            upper = max(0.0, upper)

        return Prediction(
            prediction_type=prediction_type,
            predicted_value=predicted,
            confidence_interval=[lower, upper],
            confidence_level=0.95,
            model_used=ModelType.LINEAR,
            accuracy_score=r2,
            historical_data_points=len(values),
            prediction_date=_today(),
            forecast_period_days=max(1, days_ahead),
        )

    def _forecast_curve(
        self,
        values: Sequence[float],
        horizon_days: int,
        percent_metric: bool = True,
    ) -> Tuple[List[float], float, float]:
        slope, intercept, r2, mae, _ = self._linear_fit(values)
        curve: List[float] = []
        for offset in range(1, max(1, horizon_days) + 1):
            idx = len(values) - 1 + offset
            value = self._predict_at_index(slope, intercept, idx)
            if percent_metric:
                value = self._bound_percent(value)
            else:
                value = max(0.0, value)
            curve.append(value)
        return curve, r2, mae

    async def predict_attendance_rate(self, db: Session, kindergarten_id: int, days_ahead: int = 7) -> Prediction:
        values = self._attendance_series(db, kindergarten_id, days_window=90)
        return self._build_prediction(PredictionType.ATTENDANCE, values, days_ahead, percent_metric=True)

    async def predict_incident_trend(self, db: Session, kindergarten_id: int, days_ahead: int = 30) -> Prediction:
        values = self._incidents_series(db, kindergarten_id, days_window=120)
        return self._build_prediction(PredictionType.INCIDENTS, values, days_ahead, percent_metric=False)

    async def predict_capacity_utilization(
        self,
        db: Session,
        kindergarten_id: int,
        days_ahead: int = 90,
    ) -> Prediction:
        values = self._capacity_series(db, kindergarten_id, days_window=180)
        return self._build_prediction(PredictionType.CAPACITY, values, days_ahead, percent_metric=True)

    def _enrollment_series(self, db: Session, kindergarten_id: int, days_window: int = 180) -> List[float]:
        end_day = _today()
        start_day = end_day - timedelta(days=max(30, days_window))

        rows = (
            db.query(
                func.date(models.EnrollmentApplication.created_at),
                func.count(models.EnrollmentApplication.id),
            )
            .filter(
                models.EnrollmentApplication.kindergarten_id == kindergarten_id,
                func.date(models.EnrollmentApplication.created_at) >= start_day,
                func.date(models.EnrollmentApplication.created_at) <= end_day,
            )
            .group_by(func.date(models.EnrollmentApplication.created_at))
            .order_by(func.date(models.EnrollmentApplication.created_at).asc())
            .all()
        )
        by_date: Dict[date, int] = {}
        for day_value, count_value in rows:
            if isinstance(day_value, str):
                bucket_day = date.fromisoformat(day_value)
            elif isinstance(day_value, datetime):
                bucket_day = day_value.date()
            else:
                bucket_day = day_value
            by_date[bucket_day] = int(count_value)

        # Return cumulative daily application counts as the time series
        cumulative = 0
        series: List[float] = []
        for day in self._date_buckets(start_day, end_day):
            cumulative += by_date.get(day, 0)
            series.append(float(cumulative))
        return series

    async def predict_enrollment_trend(
        self,
        db: Session,
        kindergarten_id: int,
        days_ahead: int = 30,
    ) -> Prediction:
        values = self._enrollment_series(db, kindergarten_id, days_window=180)
        return self._build_prediction(PredictionType.ENROLLMENT, values, days_ahead, percent_metric=False)

    async def analyze_trends(
        self,
        db: Session,
        kindergarten_id: int,
        metric_type: str,
        days: int = 365,
    ) -> TrendAnalysis:
        normalized = (metric_type or "").lower()
        if normalized == "attendance":
            values = self._attendance_series(db, kindergarten_id, days_window=min(max(days, 30), 365))
            percent_metric = True
        elif normalized == "incidents":
            values = self._incidents_series(db, kindergarten_id, days_window=min(max(days, 30), 365))
            percent_metric = False
        elif normalized == "capacity":
            values = self._capacity_series(db, kindergarten_id, days_window=min(max(days, 30), 365))
            percent_metric = True
        elif normalized == "enrollment":
            values = self._enrollment_series(db, kindergarten_id, days_window=min(max(days, 30), 365))
            percent_metric = False
        else:
            raise ValueError("Unsupported metric type")

        forecast_values, r2, mae = self._forecast_curve(values, horizon_days=14, percent_metric=percent_metric)
        slope, _, _, _, _ = self._linear_fit(values)
        trend_direction = "stable"
        if slope > 0.02:
            trend_direction = "upward"
        elif slope < -0.02:
            trend_direction = "downward"

        trend_strength = min(1.0, abs(slope))
        return TrendAnalysis(
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            seasonality_detected=False,
            change_points=[],
            forecast_values=forecast_values,
            forecast_dates=[_today() + timedelta(days=i) for i in range(1, len(forecast_values) + 1)],
            r_squared=r2,
            mean_absolute_error=mae,
        )

    async def get_predictive_insights(self, db: Session, kindergarten_id: int) -> dict:
        attendance = await self.predict_attendance_rate(db, kindergarten_id, days_ahead=7)
        incidents = await self.predict_incident_trend(db, kindergarten_id, days_ahead=14)
        capacity = await self.predict_capacity_utilization(db, kindergarten_id, days_ahead=30)

        alerts: List[str] = []
        recommendations: List[str] = []

        if attendance.predicted_value < 80:
            alerts.append("attendance_drop_risk")
            recommendations.append("Increase parent engagement for absent children.")
        if incidents.predicted_value > 3:
            alerts.append("incident_spike_risk")
            recommendations.append("Review safety protocols and staff supervision coverage.")
        if capacity.predicted_value > 90:
            alerts.append("capacity_saturation_risk")
            recommendations.append("Plan class expansion or rebalance enrollments.")

        if not recommendations:
            recommendations.append("Metrics are stable; continue monitoring weekly.")

        summary = (
            f"Attendance forecast: {attendance.predicted_value:.1f}%, "
            f"incidents/day: {incidents.predicted_value:.2f}, "
            f"capacity: {capacity.predicted_value:.1f}%."
        )

        return {
            "summary": summary,
            "recommendations": recommendations,
            "alerts": alerts,
            "confidence": {
                "attendance_r2": attendance.accuracy_score,
                "incidents_r2": incidents.accuracy_score,
                "capacity_r2": capacity.accuracy_score,
            },
        }


predictive_analytics = PredictiveAnalytics()
