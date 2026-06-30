"""
Predictive analytics extensions.
Attendance volatility index, capacity runway projection, and seasonal analysis.
"""
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, and_, extract
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    AttendanceStatus,
    Class,
    EnrollmentApplication,
    EnrollmentStatus,
    Kindergarten,
    KindergartenStatus,
)

logger = logging.getLogger(__name__)


class PredictiveAnalyticsService:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def attendance_volatility_index(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        window_days: int = 7,
        lookback_days: int = 30,
    ) -> List[Dict[str, Any]]:
        results = []

        if kindergarten_id is not None:
            kg_ids = [kindergarten_id]
        else:
            kg_ids = (
                db.query(Kindergarten.id)
                .filter(Kindergarten.status == KindergartenStatus.ACTIVE)
                .all()
            )
            kg_ids = [k[0] for k in kg_ids]

        cutoff = _today() - timedelta(days=max(lookback_days, window_days + 1))

        for kg_id in kg_ids:
            active_children = (
                db.query(EnrollmentApplication.child_id)
                .filter(
                    EnrollmentApplication.kindergarten_id == kg_id,
                    EnrollmentApplication.status.in_([
                        EnrollmentStatus.ACTIVE,
                        EnrollmentStatus.ACCEPTED,
                    ]),
                )
                .distinct()
                .all()
            )
            child_ids = [c[0] for c in active_children]

            if not child_ids:
                continue

            daily_rates = []
            for day_offset in range(lookback_days):
                d = _today() - timedelta(days=day_offset)
                total = len(child_ids)
                present = (
                    db.query(func.count(AttendanceLog.id))
                    .filter(
                        AttendanceLog.child_id.in_(child_ids),
                        AttendanceLog.date == d,
                        AttendanceLog.status == AttendanceStatus.PRESENT,
                    )
                    .scalar()
                    or 0
                )
                daily_rates.append(present / total * 100.0 if total > 0 else 0.0)

            daily_rates.reverse()
            if len(daily_rates) < window_days:
                continue

            window_values = daily_rates[-window_days:]
            mean_rate = sum(window_values) / len(window_values) if window_values else 0
            variance = sum((v - mean_rate) ** 2 for v in window_values) / max(len(window_values), 1)
            std_dev = math.sqrt(variance)
            cv = std_dev / mean_rate if mean_rate > 0 else 0

            if cv <= 0.03:
                classification = "stable"
            elif cv <= 0.08:
                classification = "normal"
            elif cv <= 0.15:
                classification = "volatile"
            else:
                classification = "highly_volatile"

            trend = self._compute_trend(daily_rates[-14:] if len(daily_rates) >= 14 else daily_rates)

            results.append({
                "kindergarten_id": kg_id,
                "avg_attendance_rate": round(mean_rate, 1),
                "std_dev": round(std_dev, 2),
                "volatility_index": round(cv, 4),
                "trend_slope": round(trend, 2),
                "trend_direction": "improving" if trend > 0.5 else ("declining" if trend < -0.5 else "stable"),
                "window_days": window_days,
                "classification": classification,
            })

        return sorted(results, key=lambda r: abs(r["volatility_index"]), reverse=True)

    def _compute_trend(self, values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def capacity_runway(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if kindergarten_id is not None:
            kg_ids = [kindergarten_id]
            kgs = db.query(Kindergarten).filter(Kindergarten.id == kindergarten_id).all()
        else:
            kgs = db.query(Kindergarten).filter(
                Kindergarten.status == KindergartenStatus.ACTIVE,
            ).all()
            kg_ids = [k.id for k in kgs]

        results = []
        for kg in kgs:
            kg_id = kg.id
            total_capacity = (
                db.query(func.sum(Class.capacity_total))
                .filter(Class.kindergarten_id == kg_id, Class.capacity_total.isnot(None))
                .scalar()
                or 0
            )

            total_enrolled = (
                db.query(func.count(EnrollmentApplication.id))
                .filter(
                    EnrollmentApplication.kindergarten_id == kg_id,
                    EnrollmentApplication.status.in_([
                        EnrollmentStatus.ACTIVE,
                        EnrollmentStatus.ACCEPTED,
                    ]),
                )
                .scalar()
                or 0
            )

            enrollment_30d_ago = (
                db.query(func.count(EnrollmentApplication.id))
                .filter(
                    EnrollmentApplication.kindergarten_id == kg_id,
                    EnrollmentApplication.status.in_([
                        EnrollmentStatus.ACTIVE,
                        EnrollmentStatus.ACCEPTED,
                    ]),
                    EnrollmentApplication.created_at < self._utcnow_naive() - timedelta(days=30),
                )
                .scalar()
                or 0
            )

            monthly_growth = total_enrolled - enrollment_30d_ago
            daily_growth = monthly_growth / 30.0

            remaining_capacity = max(0, total_capacity - total_enrolled)
            if daily_growth > 0:
                runway_days = int(remaining_capacity / daily_growth)
            else:
                runway_days = None

            occupancy_rate = (total_enrolled / total_capacity * 100.0) if total_capacity > 0 else 0

            if runway_days is None:
                classification = "no_risk"
            elif runway_days <= 30:
                classification = "critical"
            elif runway_days <= 90:
                classification = "warning"
            elif runway_days <= 180:
                classification = "watch"
            else:
                classification = "healthy"

            results.append({
                "kindergarten_id": kg_id,
                "kindergarten_name": kg.name_ar,
                "governorate": kg.governorate,
                "total_capacity": int(total_capacity),
                "total_enrolled": int(total_enrolled),
                "occupancy_rate": round(occupancy_rate, 1),
                "monthly_net_growth": monthly_growth,
                "runway_days": runway_days,
                "classification": classification,
            })

        return sorted(results, key=lambda r: (r["runway_days"] or 9999))

    def enrollment_projection(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        months_ahead: int = 6,
    ) -> Dict[str, Any]:
        if kindergarten_id is None:
            return {
                "error": "kindergarten_id required",
            }

        total_capacity = (
            db.query(func.sum(Class.capacity_total))
            .filter(Class.kindergarten_id == kindergarten_id, Class.capacity_total.isnot(None))
            .scalar()
            or 0
        )

        monthly_counts = []
        for m in range(months_ahead + 1):
            month_start = _today().replace(day=1) - timedelta(days=m * 30)
            count = (
                db.query(func.count(EnrollmentApplication.id))
                .filter(
                    EnrollmentApplication.kindergarten_id == kindergarten_id,
                    EnrollmentApplication.status.in_([
                        EnrollmentStatus.ACTIVE,
                        EnrollmentStatus.ACCEPTED,
                    ]),
                    EnrollmentApplication.created_at < datetime.combine(month_start, datetime.min.time()),
                )
                .scalar()
                or 0
            )
            monthly_counts.append(count)

        monthly_counts.reverse()
        if len(monthly_counts) < 2:
            return {"projection": [], "classification": "insufficient_data"}

        growth_rate = self._compute_trend([float(c) for c in monthly_counts])
        last_count = monthly_counts[-1]

        projection = []
        for m in range(1, months_ahead + 1):
            projected = max(0, int(last_count + growth_rate * m))
            projection.append({
                "month": m,
                "projected_enrollment": projected,
                "remaining_capacity": max(0, total_capacity - projected),
                "occupancy_pct": round(projected / total_capacity * 100, 1) if total_capacity > 0 else 0,
            })

        return {
            "current_enrollment": last_count,
            "total_capacity": int(total_capacity),
            "monthly_growth_rate": round(growth_rate, 1),
            "projection": projection,
            "months_to_capacity": next(
                (
                    p["month"] for p in projection
                    if p["projected_enrollment"] >= total_capacity > 0
                ),
                None,
            ),
            "classification": (
                "growing" if growth_rate > 2
                else "stable" if growth_rate > -2
                else "declining"
            ),
        }


predictive_analytics_service = PredictiveAnalyticsService()
