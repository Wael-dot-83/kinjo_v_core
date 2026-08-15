"""
Parent engagement analytics service.
Computes notification-to-view conversion, report view rate, and parent portal activity.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, distinct
from sqlalchemy.orm import Session

from models import (
    AuditLog,
    Child,
    DailyReport,
    DailyReportStatus,
    DailyReportView,
    EnrollmentApplication,
    EnrollmentStatus,
    Kindergarten,
    KindergartenStatus,
    Message,
    MessageUserState,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    ParentProfile,
    Survey,
    SurveyResponse,
    User,
    UserRole,
)
from audit_actions import AuditAction

logger = logging.getLogger(__name__)


class ParentEngagementService:

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def report_view_rate(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff_date = _today() - timedelta(days=max(1, days))

        reports_query = db.query(func.count(DailyReport.id)).filter(
            DailyReport.date >= cutoff_date,
            DailyReport.status == DailyReportStatus.SENT_TO_PARENT,
        )
        if kindergarten_id is not None:
            reports_query = reports_query.filter(DailyReport.kindergarten_id == kindergarten_id)
        total_sent = reports_query.scalar() or 0

        if total_sent == 0:
            return {
                "view_rate": 0.0,
                "total_sent": 0,
                "viewed_count": 0,
                "period_days": days,
                "classification": "no_data",
            }

        views_query = db.query(
            func.count(distinct(DailyReportView.daily_report_id))
        ).join(
            DailyReport,
            DailyReport.id == DailyReportView.daily_report_id,
        ).filter(
            DailyReport.date >= cutoff_date,
            DailyReport.status == DailyReportStatus.SENT_TO_PARENT,
        )
        if kindergarten_id is not None:
            views_query = views_query.filter(DailyReport.kindergarten_id == kindergarten_id)
        viewed_count = views_query.scalar() or 0

        view_rate = (viewed_count / total_sent) * 100.0 if total_sent > 0 else 0.0

        return {
            "view_rate": round(view_rate, 1),
            "total_sent": int(total_sent),
            "viewed_count": int(viewed_count),
            "period_days": days,
            "classification": (
                "high" if view_rate >= 70
                else "moderate" if view_rate >= 40
                else "low"
            ),
        }

    def parent_login_frequency(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = self._utcnow_naive() - timedelta(days=max(1, days))

        parent_query = db.query(User.id).filter(
            User.role == UserRole.PARENT,
            User.deleted_at.is_(None),
        )
        if kindergarten_id is not None:
            parent_query = (
                parent_query.join(ParentProfile, ParentProfile.user_id == User.id)
                .join(Child, Child.parent_id == ParentProfile.id)
                .join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id)
                .filter(EnrollmentApplication.kindergarten_id == kindergarten_id)
            )
        parent_ids = parent_query.distinct().subquery()

        total_parents = (
            db.query(func.count(distinct(parent_ids.c.id))).scalar() or 0
        )

        if total_parents == 0:
            return {
                "avg_logins_per_parent": 0.0,
                "total_parents": 0,
                "active_parents": 0,
                "total_logins": 0,
                "period_days": days,
                "classification": "no_data",
            }

        active_parents = (
            db.query(func.count(distinct(User.id)))
            .filter(
                User.id.in_(db.query(parent_ids.c.id)),
                User.last_login_at.isnot(None),
                User.last_login_at >= cutoff,
            )
            .scalar()
            or 0
        )

        total_logins = (
            db.query(func.count(AuditLog.id))
            .filter(
                AuditLog.action == AuditAction.LOGIN_SUCCESS,
                AuditLog.created_at >= cutoff,
                AuditLog.user_id.in_(db.query(parent_ids.c.id)),
            )
            .scalar()
            or 0
        )

        avg_logins = (total_logins / total_parents) if total_parents else 0.0
        active_rate = (active_parents / total_parents) * 100.0 if total_parents else 0.0

        return {
            "avg_logins_per_parent": round(avg_logins, 2),
            "total_parents": int(total_parents),
            "active_parents": int(active_parents),
            "total_logins": int(total_logins),
            "active_rate": round(active_rate, 1),
            "period_days": days,
            "classification": (
                "high" if active_rate >= 70
                else "moderate" if active_rate >= 40
                else "low"
            ),
        }

    def nps_score(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = db.query(func.avg(SurveyResponse.nps_score))
        if kindergarten_id is not None:
            query = query.join(Survey, Survey.id == SurveyResponse.survey_id).filter(
                Survey.kindergarten_id == kindergarten_id,
            )
        avg_rating = query.scalar() or 0

        response_count_query = db.query(func.count(SurveyResponse.id))
        if kindergarten_id is not None:
            response_count_query = response_count_query.join(
                Survey, Survey.id == SurveyResponse.survey_id,
            ).filter(Survey.kindergarten_id == kindergarten_id)
        response_count = response_count_query.scalar() or 0

        if response_count == 0:
            return {
                "avg_rating": None,
                "nps_score": None,
                "response_count": 0,
                "classification": "no_data",
            }

        nps = round(avg_rating * 10, 1)
        if nps >= 50:
            classification = "good"
        elif nps >= 0:
            classification = "acceptable"
        else:
            classification = "poor"

        return {
            "avg_rating": round(float(avg_rating), 2),
            "nps_score": nps,
            "response_count": int(response_count),
            "classification": classification,
        }

    def overall_parent_engagement(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        views = self.report_view_rate(db, kindergarten_id=kindergarten_id)
        logins = self.parent_login_frequency(db, kindergarten_id=kindergarten_id)
        nps = self.nps_score(db, kindergarten_id=kindergarten_id)

        view_score = min(100, views.get("view_rate", 0) * 1.5)
        nps_score = max(0, (nps.get("nps_score") or 50) + 50)

        overall = view_score * 0.50 + nps_score * 0.50

        return {
            "overall_score": round(overall, 1),
            "report_views": views,
            "parent_logins": logins,
            "nps": nps,
            "status": (
                "engaged" if overall >= 75
                else "moderate" if overall >= 50
                else "low"
            ),
        }


parent_engagement_service = ParentEngagementService()
