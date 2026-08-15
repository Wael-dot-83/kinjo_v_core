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
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        base_filter = [DailyReport.created_at >= cutoff]
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
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        base_filter = [DailyReport.created_at >= cutoff]
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
                "first_pass_rate": 100.0,
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
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))
        base_filter = [DailyReport.created_at >= cutoff]
        if kindergarten_id is not None:
            base_filter.append(DailyReport.kindergarten_id == kindergarten_id)

        # Bucket by hour in the database. This used to select every matching
        # created_at and count hours in Python: `created_at` records when the
        # row was written rather than when the report was filed, so on
        # production every one of the 378k daily_reports fell inside the
        # 7-day window and was shipped to the app on each page load. The scan
        # itself costs ~250ms; materialising the rows cost ~2.4s on top.
        #
        # EXTRACT(hour FROM ...) is portable here: SQLAlchemy renders it
        # natively on PostgreSQL and as CAST(STRFTIME('%H', ...) AS INTEGER)
        # on SQLite. Both read the stored value, and daily_reports.created_at
        # is timestamptz with the session at UTC, so the hour matches what the
        # old Python path derived from the returned datetime. (An
        # unconditionally dialect-specific expression is what broke this page
        # in production before -- see the julianday note in admin_endpoints.)
        hour_rows = (
            db.query(
                func.extract("hour", DailyReport.created_at).label("hour"),
                func.count(DailyReport.id).label("count"),
            )
            .filter(*base_filter)
            .group_by(func.extract("hour", DailyReport.created_at))
            .all()
        )

        # NULL created_at groups into its own bucket; it counted toward the
        # old len(rows) denominator but never toward an hour, so keep it out
        # of hour_counts and in total_reports.
        total_reports = sum(int(r.count) for r in hour_rows)

        if not total_reports:
            return {
                "hour_distribution": {},
                "peak_hour": None,
                "morning_rate": 0.0,
                "total_reports": 0,
                "classification": "no_data",
            }

        hour_counts: Counter = Counter()
        for row in hour_rows:
            if row.hour is None:
                continue
            hour_counts[int(row.hour)] += int(row.count)

        distribution = {str(h): c for h, c in sorted(hour_counts.items())}
        # Iterate in hour order so an exact tie resolves to the earliest hour
        # rather than to whichever row the driver happened to return first.
        peak_hour = max(sorted(hour_counts), key=hour_counts.get) if hour_counts else None

        morning_count = sum(hour_counts.get(h, 0) for h in range(6, 10))
        morning_rate = (morning_count / total_reports) * 100.0

        return {
            "hour_distribution": distribution,
            "peak_hour": peak_hour,
            "morning_rate": round(morning_rate, 1),
            "total_reports": total_reports,
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
                hour = created.hour if created.tzinfo else created.hour
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
        rejection = self.report_rejection_rate(db, kindergarten_id=kindergarten_id)
        first_pass = self.first_pass_approval_rate(db, kindergarten_id=kindergarten_id)
        timing = self.submission_timing_distribution(db, kindergarten_id=kindergarten_id)
        morning = self.morning_routine_completion(db, kindergarten_id=kindergarten_id)

        rejection_score = max(0, 100.0 - rejection["rejection_rate"] * 2)
        first_pass_score = first_pass["first_pass_rate"]
        morning_score = morning["completion_rate"]
        timing_score = min(100, morning.get("morning_rate", 0) * 1.5)

        overall = (
            rejection_score * 0.30
            + first_pass_score * 0.25
            + morning_score * 0.25
            + timing_score * 0.20
        )

        return {
            "overall_score": round(overall, 1),
            "rejection_rate": rejection,
            "first_pass_approval": first_pass,
            "submission_timing": timing,
            "morning_routine": morning,
            "status": (
                "excellent" if overall >= 85
                else "good" if overall >= 70
                else "fair" if overall >= 55
                else "needs_improvement"
            ),
        }


governance_quality_service = GovernanceQualityService()
