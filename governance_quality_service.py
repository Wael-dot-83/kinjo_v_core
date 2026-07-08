"""
Governance quality analytics service.
Computes report rejection rate, first-pass approval rate, submission timing,
and morning routine completion metrics.
"""
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from models import (
    DailyReport,
    DailyReportStatus,
    Kindergarten,
    KindergartenStatus,
)

logger = logging.getLogger(__name__)


class GovernanceQualityService:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def report_rejection_rate(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff_date = _today() - timedelta(days=max(1, days))
        base_filter = [DailyReport.date >= cutoff_date]
        if kindergarten_id is not None:
            base_filter.append(DailyReport.kindergarten_id == kindergarten_id)

        total_submitted = (
            db.query(func.count(DailyReport.id))
            .filter(
                *base_filter,
                DailyReport.status.in_([
                    DailyReportStatus.SUBMITTED,
                    DailyReportStatus.APPROVED,
                    DailyReportStatus.REJECTED,
                    DailyReportStatus.RETURNED,
                    DailyReportStatus.SENT_TO_PARENT,
                ]),
            )
            .scalar()
            or 0
        )

        if total_submitted == 0:
            return {
                "rejection_rate": 0.0,
                "total_submitted": 0,
                "rejected_count": 0,
                "period_days": days,
                "classification": "no_data",
            }

        rejected = (
            db.query(func.count(DailyReport.id))
            .filter(
                *base_filter,
                DailyReport.status.in_([
                    DailyReportStatus.REJECTED,
                    DailyReportStatus.RETURNED,
                ]),
            )
            .scalar()
            or 0
        )

        rejection_rate = (rejected / total_submitted) * 100.0

        if rejection_rate <= 5:
            classification = "excellent"
        elif rejection_rate <= 15:
            classification = "acceptable"
        else:
            classification = "needs_improvement"

        return {
            "rejection_rate": round(rejection_rate, 2),
            "total_submitted": int(total_submitted),
            "rejected_count": int(rejected),
            "period_days": days,
            "classification": classification,
        }

    def first_pass_approval_rate(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff_date = _today() - timedelta(days=max(1, days))
        base_filter = [DailyReport.date >= cutoff_date]
        if kindergarten_id is not None:
            base_filter.append(DailyReport.kindergarten_id == kindergarten_id)

        total_with_resolution = (
            db.query(func.count(DailyReport.id))
            .filter(
                *base_filter,
                DailyReport.status.in_([
                    DailyReportStatus.APPROVED,
                    DailyReportStatus.REJECTED,
                    DailyReportStatus.RETURNED,
                    DailyReportStatus.SENT_TO_PARENT,
                ]),
            )
            .scalar()
            or 0
        )

        if total_with_resolution == 0:
            return {
                "first_pass_rate": 0.0,
                "total_resolved": 0,
                "approved_first": 0,
                "classification": "no_data",
            }

        approved_first = (
            db.query(func.count(DailyReport.id))
            .filter(
                *base_filter,
                DailyReport.status.in_([
                    DailyReportStatus.APPROVED,
                    DailyReportStatus.SENT_TO_PARENT,
                ]),
                DailyReport.rejected_reason.is_(None)
            )
            .scalar()
            or 0
        )

        first_pass_rate = (approved_first / total_with_resolution) * 100.0

        return {
            "first_pass_rate": round(first_pass_rate, 2),
            "total_resolved": int(total_with_resolution),
            "approved_first": int(approved_first),
            "period_days": days,
            "classification": (
                "excellent" if first_pass_rate >= 90
                else "acceptable" if first_pass_rate >= 70
                else "needs_improvement"
            ),
        }

    def submission_timing_distribution(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        cutoff_date = _today() - timedelta(days=max(1, days))
        base_filter = [DailyReport.date >= cutoff_date]
        if kindergarten_id is not None:
            base_filter.append(DailyReport.kindergarten_id == kindergarten_id)

        rows = (
            db.query(DailyReport.created_at)
            .filter(*base_filter)
            .all()
        )

        if not rows:
            return {
                "hour_distribution": {},
                "peak_hour": None,
                "morning_rate": 0.0,
                "total_reports": 0,
                "classification": "no_data",
            }

        hour_counts: Counter = Counter()
        for row in rows:
            created_at = row[0]
            if created_at:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                jordan_tz = timezone(timedelta(hours=3))
                dt_jordan = created_at.astimezone(jordan_tz)
                hour = dt_jordan.hour
                hour_counts[hour] += 1

        distribution = {str(h): c for h, c in sorted(hour_counts.items())}
        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

        morning_count = sum(hour_counts.get(h, 0) for h in range(6, 10))
        morning_rate = (morning_count / len(rows)) * 100.0 if rows else 0.0

        return {
            "hour_distribution": distribution,
            "peak_hour": peak_hour,
            "morning_rate": round(morning_rate, 1),
            "total_reports": len(rows),
            "period_days": days,
            "classification": (
                "structured" if morning_rate >= 60
                else "scattered" if len(hour_counts) > 8
                else "consistent"
            ),
        }

    def morning_routine_completion(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        target_hour: int = 10,
        days: int = 7,
    ) -> Dict[str, Any]:
        cutoff_date = _today() - timedelta(days=max(1, days))

        query = (
            db.query(DailyReport.date, DailyReport.created_at)
            .filter(DailyReport.date >= cutoff_date)
        )

        if kindergarten_id is not None:
            query = query.filter(DailyReport.kindergarten_id == kindergarten_id)

        rows = query.all()

        if not rows:
            return {
                "completion_rate": 0.0,
                "days_analyzed": 0,
                "target_hour": target_hour,
                "period_days": days,
                "classification": "no_data",
            }

        morning_count = 0
        total_reports = 0
        day_counts: Dict[date, int] = {}

        for row in rows:
            d = row[0]
            created = row[1]
            total_reports += 1
            day_counts[d] = day_counts.get(d, 0) + 1
            if created:
                dt_utc = created.replace(tzinfo=timezone.utc) if not created.tzinfo else created
                from utils.time_utils import _JORDAN_TZ
                dt_jordan = dt_utc.astimezone(_JORDAN_TZ)
                hour = dt_jordan.hour
                if hour < target_hour:
                    morning_count += 1

        completion_rate = (morning_count / total_reports * 100.0) if total_reports > 0 else 0.0

        return {
            "completion_rate": round(completion_rate, 1),
            "days_analyzed": len(day_counts),
            "target_hour": target_hour,
            "total_reports": total_reports,
            "morning_reports": morning_count,
            "period_days": days,
            "classification": (
                "excellent" if completion_rate >= 90
                else "good" if completion_rate >= 75
                else "needs_improvement"
            ),
        }

    def overall_governance_quality(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from governance_kpi_service import compute_full_gqi

        end_date = _today()
        start_date = end_date - timedelta(days=30)
        
        gqi_data = compute_full_gqi(db, start_date, end_date, kindergarten_id)
        
        # We also need the specific sub-details expected by the observability endpoint
        rejection = self.report_rejection_rate(db, kindergarten_id=kindergarten_id)
        first_pass = self.first_pass_approval_rate(db, kindergarten_id=kindergarten_id)
        timing = self.submission_timing_distribution(db, kindergarten_id=kindergarten_id)
        morning = self.morning_routine_completion(db, kindergarten_id=kindergarten_id)

        # Mapping the centralized 7-factor GQI directly to this endpoint response
        return {
            "overall_score": gqi_data["gqi"],
            "rejection_rate": rejection,
            "first_pass_approval": first_pass,
            "submission_timing": timing,
            "morning_routine": morning,
            "status": gqi_data["health_status"],
            "details": gqi_data["sub_indicators"]
        }


governance_quality_service = GovernanceQualityService()
