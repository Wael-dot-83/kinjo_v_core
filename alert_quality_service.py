"""
Alert quality analytics service.
Computes signal-to-noise ratio, false positive rate, and time-to-acknowledge metrics.
Operates on the existing active_alerts and anomaly_alerts tables.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from models import (
    ActiveAlert,
    AnomalyAlert,
    AlertThreshold,
    SeverityLevel,
    AlertStatus,
)

logger = logging.getLogger(__name__)


class AlertQualityService:
    """Compute quality metrics for the alerting system."""

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def signal_to_noise_ratio(
        self,
        db: Session,
        days: int = 30,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        query = db.query(ActiveAlert).filter(ActiveAlert.triggered_at >= cutoff)
        if kindergarten_id is not None:
            query = query.filter(
                and_(
                    ActiveAlert.scope_type == "KINDERGARTEN",
                    ActiveAlert.scope_id == str(kindergarten_id),
                )
            )

        total = query.count()
        if total == 0:
            return {
                "snr": 1.0,
                "total_alerts": 0,
                "critical_high": 0,
                "medium_low": 0,
                "period_days": days,
                "classification": "no_data",
            }

        critical_high = query.filter(
            ActiveAlert.severity.in_([SeverityLevel.HIGH, SeverityLevel.CRITICAL])
        ).count()

        medium_low = total - critical_high
        snr = critical_high / total if total > 0 else 1.0

        if snr >= 0.6:
            classification = "healthy"
        elif snr >= 0.4:
            classification = "watch"
        else:
            classification = "degraded"

        return {
            "snr": round(snr, 3),
            "total_alerts": total,
            "critical_high": critical_high,
            "medium_low": medium_low,
            "period_days": days,
            "classification": classification,
        }

    def false_positive_rate(
        self,
        db: Session,
        days: int = 30,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        query = db.query(ActiveAlert).filter(ActiveAlert.triggered_at >= cutoff)
        if kindergarten_id is not None:
            query = query.filter(
                and_(
                    ActiveAlert.scope_type == "KINDERGARTEN",
                    ActiveAlert.scope_id == str(kindergarten_id),
                )
            )

        total = query.count()
        if total == 0:
            return {
                "fpr": 0.0,
                "total_alerts": 0,
                "unactioned": 0,
                "acknowledged": 0,
                "resolved": 0,
                "period_days": days,
                "classification": "no_data",
            }

        acknowledged = query.filter(
            ActiveAlert.acknowledged_at.isnot(None)
        ).count()

        resolved = query.filter(
            ActiveAlert.status.in_([AlertStatus.RESOLVED, AlertStatus.DISMISSED])
        ).count()

        actioned = query.filter(
            or_(
                ActiveAlert.acknowledged_at.isnot(None),
                ActiveAlert.status.in_([AlertStatus.RESOLVED, AlertStatus.DISMISSED]),
            )
        ).count()

        unactioned = total - actioned
        fpr = unactioned / total if total > 0 else 0.0

        if fpr <= 0.10:
            classification = "ideal"
        elif fpr <= 0.25:
            classification = "acceptable"
        else:
            classification = "overloaded"

        return {
            "fpr": round(fpr, 3),
            "total_alerts": total,
            "unactioned": unactioned,
            "acknowledged": acknowledged,
            "resolved": resolved,
            "period_days": days,
            "classification": classification,
        }

    def time_to_acknowledge(
        self,
        db: Session,
        days: int = 7,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        query = db.query(ActiveAlert).filter(
            and_(
                ActiveAlert.triggered_at >= cutoff,
                ActiveAlert.acknowledged_at.isnot(None),
            )
        )
        if kindergarten_id is not None:
            query = query.filter(
                and_(
                    ActiveAlert.scope_type == "KINDERGARTEN",
                    ActiveAlert.scope_id == str(kindergarten_id),
                )
            )

        rows = query.all()
        if not rows:
            return {
                "avg_minutes": None,
                "p50_minutes": None,
                "p95_minutes": None,
                "min_minutes": None,
                "max_minutes": None,
                "acknowledged_count": 0,
                "period_days": days,
            }

        durations = []
        for row in rows:
            if row.acknowledged_at and row.triggered_at:
                triggered = row.triggered_at
                acked = row.acknowledged_at
                if triggered.tzinfo is None:
                    triggered = triggered.replace(tzinfo=timezone.utc)
                if acked.tzinfo is None:
                    acked = acked.replace(tzinfo=timezone.utc)
                delta_minutes = (acked - triggered).total_seconds() / 60.0
                durations.append(max(0, delta_minutes))

        if not durations:
            return {
                "avg_minutes": None,
                "p50_minutes": None,
                "p95_minutes": None,
                "min_minutes": None,
                "max_minutes": None,
                "acknowledged_count": 0,
                "period_days": days,
            }

        durations.sort()
        n = len(durations)

        return {
            "avg_minutes": round(sum(durations) / n, 1),
            "p50_minutes": round(durations[n // 2], 1),
            "p95_minutes": round(durations[min(int(n * 0.95), n - 1)], 1),
            "min_minutes": round(durations[0], 1),
            "max_minutes": round(durations[-1], 1),
            "acknowledged_count": n,
            "period_days": days,
        }

    def overall_alert_quality(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        snr_result = self.signal_to_noise_ratio(db, days=30, kindergarten_id=kindergarten_id)
        fpr_result = self.false_positive_rate(db, days=30, kindergarten_id=kindergarten_id)
        tta_result = self.time_to_acknowledge(db, days=7, kindergarten_id=kindergarten_id)

        snr_score = snr_result["snr"] * 100.0
        fpr_score = max(0, 100.0 - (fpr_result["fpr"] * 100.0))
        if tta_result["p95_minutes"] is not None:
            if tta_result["p95_minutes"] <= 5:
                tta_score = 100.0
            elif tta_result["p95_minutes"] <= 30:
                tta_score = 80.0
            elif tta_result["p95_minutes"] <= 60:
                tta_score = 60.0
            else:
                tta_score = 40.0
        else:
            tta_score = 50.0

        overall = snr_score * 0.40 + fpr_score * 0.35 + tta_score * 0.25

        if overall >= 80:
            health = "healthy"
        elif overall >= 60:
            health = "watch"
        else:
            health = "degraded"

        return {
            "overall_score": round(overall, 1),
            "health": health,
            "signal_to_noise": snr_result,
            "false_positive_rate": fpr_result,
            "time_to_acknowledge": tta_result,
        }


alert_quality_service = AlertQualityService()
