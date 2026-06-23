"""
Enrollment analytics service.
Computes funnel drop-off rates, turnaround times, and waitlist conversion.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from models import (
    EnrollmentApplication,
    EnrollmentStatus,
    WaitlistEntry,
    WaitlistStatus,
    Kindergarten,
    KindergartenStatus,
)

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    "DRAFT",
    "SUBMITTED",
    "PENDING_REVIEW",
    "ACCEPTED",
    "ACTIVE",
]


class EnrollmentAnalyticsService:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def enrollment_funnel(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        statuses = list(EnrollmentStatus)
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))

        results = []
        for stage in statuses:
            query = db.query(func.count(EnrollmentApplication.id)).filter(
                EnrollmentApplication.status == stage,
            )
            if kindergarten_id is not None:
                query = query.filter(EnrollmentApplication.kindergarten_id == kindergarten_id)
            count = query.scalar() or 0
            results.append({"stage": stage.value, "count": int(count)})

        total = sum(r["count"] for r in results)
        if total == 0:
            return {
                "stages": [],
                "total_applications": 0,
                "drop_off_rates": {},
                "classification": "no_data",
            }

        previous_count = None
        drop_off_rates = {}
        for r in results:
            if previous_count is not None and previous_count > 0:
                drop_off = ((previous_count - r["count"]) / previous_count) * 100.0
                drop_off_rates[r["stage"]] = max(0, round(drop_off, 1))
            previous_count = r["count"]

        first_stage = results[0]["count"] if results else 0
        last_stage = results[-1]["count"] if results else 0
        overall_conversion = (last_stage / first_stage * 100.0) if first_stage > 0 else 0

        return {
            "stages": results,
            "total_applications": total,
            "drop_off_rates": drop_off_rates,
            "overall_conversion_rate": round(overall_conversion, 1),
            "period_days": days,
            "classification": (
                "healthy" if overall_conversion >= 50
                else "concerning" if overall_conversion >= 25
                else "critical"
            ),
        }

    def enrollment_turnaround(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))

        query = db.query(EnrollmentApplication).filter(
            EnrollmentApplication.status.in_([
                EnrollmentStatus.ACCEPTED,
                EnrollmentStatus.ACTIVE,
                EnrollmentStatus.REJECTED,
            ]),
        )
        if kindergarten_id is not None:
            query = query.filter(EnrollmentApplication.kindergarten_id == kindergarten_id)

        apps = query.all()
        if not apps:
            return {
                "avg_hours": None,
                "median_hours": None,
                "p95_hours": None,
                "total_processed": 0,
                "fast_processed": 0,
                "slow_processed": 0,
                "classification": "no_data",
            }

        durations_hours = []
        fast = 0
        slow = 0
        for app in apps:
            submitted_at = None
            resolved_at = None
            if hasattr(app, "submitted_at") and app.submitted_at:
                submitted_at = app.submitted_at
            elif app.created_at:
                submitted_at = app.created_at
            if hasattr(app, "reviewed_at") and app.reviewed_at:
                resolved_at = app.reviewed_at
            elif app.updated_at:
                resolved_at = app.updated_at

            if submitted_at and resolved_at:
                if submitted_at.tzinfo is None:
                    submitted_at = submitted_at.replace(tzinfo=timezone.utc)
                if resolved_at.tzinfo is None:
                    resolved_at = resolved_at.replace(tzinfo=timezone.utc)
                hours = (resolved_at - submitted_at).total_seconds() / 3600.0
                if hours >= 0:
                    durations_hours.append(hours)
                    if hours <= 24:
                        fast += 1
                    elif hours > 72:
                        slow += 1

        if not durations_hours:
            return {
                "avg_hours": None,
                "median_hours": None,
                "p95_hours": None,
                "total_processed": 0,
                "fast_processed": 0,
                "slow_processed": 0,
                "classification": "no_data",
            }

        durations_hours.sort()
        n = len(durations_hours)
        avg = sum(durations_hours) / n
        median = durations_hours[n // 2]
        p95 = durations_hours[min(int(n * 0.95), n - 1)]

        return {
            "avg_hours": round(avg, 1),
            "median_hours": round(median, 1),
            "p95_hours": round(p95, 1),
            "total_processed": len(durations_hours),
            "fast_processed": fast,
            "slow_processed": slow,
            "period_days": days,
            "classification": (
                "fast" if median <= 24
                else "acceptable" if median <= 48
                else "slow"
            ),
        }

    def waitlist_conversion_rate(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        base_query = db.query(func.count(WaitlistEntry.id)).join(
            EnrollmentApplication,
            WaitlistEntry.enrollment_id == EnrollmentApplication.id,
        )
        if kindergarten_id is not None:
            base_query = base_query.filter(
                EnrollmentApplication.kindergarten_id == kindergarten_id
            )
        total_offered = base_query.scalar() or 0

        if total_offered == 0:
            return {
                "conversion_rate": 0.0,
                "total_offered": 0,
                "accepted_count": 0,
                "expired_count": 0,
                "classification": "no_data",
            }

        accepted_query = db.query(func.count(WaitlistEntry.id)).join(
            EnrollmentApplication,
            WaitlistEntry.enrollment_id == EnrollmentApplication.id,
        ).filter(
            WaitlistEntry.status == WaitlistStatus.ACCEPTED,
        )
        if kindergarten_id is not None:
            accepted_query = accepted_query.filter(
                EnrollmentApplication.kindergarten_id == kindergarten_id
            )
        accepted_count = accepted_query.scalar() or 0

        expired_query = db.query(func.count(WaitlistEntry.id)).join(
            EnrollmentApplication,
            WaitlistEntry.enrollment_id == EnrollmentApplication.id,
        ).filter(
            WaitlistEntry.status.in_([WaitlistStatus.EXPIRED, WaitlistStatus.DECLINED]),
        )
        if kindergarten_id is not None:
            expired_query = expired_query.filter(
                EnrollmentApplication.kindergarten_id == kindergarten_id
            )
        expired_count = expired_query.scalar() or 0

        conversion_rate = (accepted_count / total_offered) * 100.0 if total_offered > 0 else 0.0

        return {
            "conversion_rate": round(conversion_rate, 1),
            "total_offered": int(total_offered),
            "accepted_count": int(accepted_count),
            "expired_count": int(expired_count),
            "pending_count": int(total_offered) - int(accepted_count) - int(expired_count),
            "classification": (
                "high" if conversion_rate >= 70
                else "moderate" if conversion_rate >= 50
                else "low"
            ),
        }

    def overall_enrollment_analytics(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        funnel = self.enrollment_funnel(db, kindergarten_id=kindergarten_id)
        turnaround = self.enrollment_turnaround(db, kindergarten_id=kindergarten_id)
        waitlist = self.waitlist_conversion_rate(db, kindergarten_id=kindergarten_id)

        overall = {
            "funnel": funnel,
            "turnaround": turnaround,
            "waitlist": waitlist,
        }

        funnel_score = funnel.get("overall_conversion_rate", 0)
        turnaround_score = 100.0 if turnaround.get("median_hours") is not None else 50.0
        if turnaround.get("median_hours") is not None:
            if turnaround["median_hours"] <= 24:
                turnaround_score = 100.0
            elif turnaround["median_hours"] <= 48:
                turnaround_score = 75.0
            else:
                turnaround_score = 50.0
        waitlist_score = waitlist.get("conversion_rate", 0)

        overall["overall_health"] = round(
            (funnel_score * 0.33 + turnaround_score * 0.34 + waitlist_score * 0.33),
            1,
        )
        return overall


enrollment_analytics_service = EnrollmentAnalyticsService()
