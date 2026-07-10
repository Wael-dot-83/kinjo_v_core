"""Data quality and realtime dashboard service layer."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from utils.time_utils import today_amman as _today


@dataclass
class DataQualityResult:
    metric: str
    score: float
    issues: List[str]
    timestamp: datetime


class DataQualityService:
    """Compute quality KPIs and realtime dashboard payloads from live data."""

    @staticmethod
    def _active_enrollment_filter(query, kindergarten_id: Optional[int] = None):
        query = query.filter(models.EnrollmentApplication.is_active.is_(True))
        if kindergarten_id is not None:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
        return query

    @staticmethod
    def _safe_rate(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 100.0
        return round((numerator / denominator) * 100.0, 2)

    def _child_completeness(self, db: Session, kindergarten_id: Optional[int]) -> Dict[str, int]:
        base = db.query(models.Child.id).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id,
        )
        base = self._active_enrollment_filter(base, kindergarten_id)

        total = base.distinct().count()

        complete = base.filter(
            models.Child.first_name.isnot(None),
            models.Child.last_name.isnot(None),
            models.Child.date_of_birth.isnot(None),
            models.Child.gender.isnot(None),
        ).distinct().count()
        return {"total": total, "complete": complete}

    def _kindergarten_completeness(self, db: Session, kindergarten_id: Optional[int]) -> Dict[str, int]:
        base = db.query(models.Kindergarten.id)
        if kindergarten_id is not None:
            base = base.filter(models.Kindergarten.id == kindergarten_id)
        else:
            base = base.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)

        total = base.count()
        complete = base.filter(
            models.Kindergarten.name_ar.isnot(None),
            models.Kindergarten.governorate.isnot(None),
            models.Kindergarten.district.isnot(None),
            models.Kindergarten.area.isnot(None),
            models.Kindergarten.address_line.isnot(None),
            models.Kindergarten.contact_phone.isnot(None),
        ).count()
        return {"total": total, "complete": complete}

    def _timeliness_score(self, db: Session, kindergarten_id: Optional[int]) -> float:
        """Score based on yesterday daily-report completion for active children."""
        report_date = _today() - timedelta(days=1)
        active_children_q = db.query(models.EnrollmentApplication.child_id)
        active_children_q = self._active_enrollment_filter(active_children_q, kindergarten_id)
        active_child_ids = [child_id for (child_id,) in active_children_q.distinct().all()]

        if not active_child_ids:
            return 100.0

        submitted_count = (
            db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.child_id.in_(active_child_ids),
                models.DailyReport.date == report_date,
                models.DailyReport.status.in_(
                    [
                        models.DailyReportStatus.SUBMITTED,
                        models.DailyReportStatus.APPROVED,
                        models.DailyReportStatus.SENT_TO_PARENT,
                    ]
                ),
            )
            .scalar()
            or 0
        )
        return self._safe_rate(int(submitted_count), len(active_child_ids))

    async def check_data_quality(
        self,
        entity_type: str,
        entity_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> DataQualityResult:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized_entity = (entity_type or "NETWORK").upper()

        if db is None:
            return DataQualityResult(metric=normalized_entity, score=100.0, issues=[], timestamp=now)

        kg_completeness = self._kindergarten_completeness(
            db, entity_id if normalized_entity == "KINDERGARTEN" else None
        )
        child_completeness = self._child_completeness(
            db, entity_id if normalized_entity == "KINDERGARTEN" else None
        )

        kg_score = self._safe_rate(kg_completeness["complete"], kg_completeness["total"])
        child_score = self._safe_rate(child_completeness["complete"], child_completeness["total"])
        timeliness_score = self._timeliness_score(
            db, entity_id if normalized_entity == "KINDERGARTEN" else None
        )
        consistency_score = round(min(100.0, (kg_score * 0.4 + child_score * 0.4 + timeliness_score * 0.2)), 2)

        overall = round((kg_score * 0.35 + child_score * 0.35 + timeliness_score * 0.2 + consistency_score * 0.1), 2)

        issues: List[str] = []
        if kg_score < 95:
            issues.append("kindergarten_profile_completeness_below_threshold")
        if child_score < 95:
            issues.append("child_profile_completeness_below_threshold")
        if timeliness_score < 85:
            issues.append("daily_report_timeliness_below_threshold")

        return DataQualityResult(
            metric=normalized_entity,
            score=overall,
            issues=issues,
            timestamp=now,
        )

    async def get_overall_quality_score(self, db: Optional[Session] = None) -> float:
        result = await self.check_data_quality("NETWORK", db=db)
        return result.score

    async def get_quality_trends(self, db: Optional[Session] = None, days: int = 30) -> List[Dict[str, Any]]:
        if db is None:
            return []

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, days))
        rows = (
            db.query(models.DataQualityMetric)
            .filter(models.DataQualityMetric.evaluated_at >= cutoff)
            .order_by(models.DataQualityMetric.evaluated_at.asc())
            .all()
        )

        trend_points: List[Dict[str, Any]] = []
        for row in rows:
            trend_points.append(
                {
                    "evaluated_at": row.evaluated_at.isoformat(),
                    "completeness_percent": row.completeness_percent,
                    "accuracy_score": row.accuracy_score,
                    "timeliness_score": row.timeliness_score,
                    "consistency_score": row.consistency_score,
                }
            )
        return trend_points

    async def get_realtime_dashboard_data(
        self,
        db: Session,
        kindergarten_id: int,
        user_role: str,
    ) -> Dict[str, Any]:
        """Return a websocket-safe realtime dashboard payload for manager/supervisor scopes."""
        today = _today()

        active_children_count = (
            self._active_enrollment_filter(
                db.query(models.EnrollmentApplication.child_id).distinct(),
                kindergarten_id,
            ).count()
        )

        present_today_count = (
            db.query(func.count(models.AttendanceLog.id))
            .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
            .filter(
                models.Class.kindergarten_id == kindergarten_id,
                models.AttendanceLog.date == today,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            .scalar()
            or 0
        )

        pending_reports_count = (
            db.query(func.count(models.DailyReport.id))
            .filter(
                models.DailyReport.kindergarten_id == kindergarten_id,
                models.DailyReport.date == today,
                models.DailyReport.status.in_(
                    [models.DailyReportStatus.DRAFT, models.DailyReportStatus.SUBMITTED]
                ),
            )
            .scalar()
            or 0
        )

        incidents_today_count = (
            db.query(func.count(models.Incident.id))
            .filter(
                models.Incident.kindergarten_id == kindergarten_id,
                func.date(models.Incident.created_at) == today,
            )
            .scalar()
            or 0
        )

        attendance_rate = self._safe_rate(int(present_today_count), int(active_children_count))
        quality_result = await self.check_data_quality("KINDERGARTEN", kindergarten_id, db=db)

        health_score = round(
            (
                attendance_rate * 0.45
                + quality_result.score * 0.45
                + max(0.0, 100.0 - (float(incidents_today_count) * 10.0)) * 0.10
            ),
            2,
        )

        validation_status = "passed"
        if health_score < 60:
            validation_status = "critical"
        elif health_score < 80:
            validation_status = "warning"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "kindergarten_id": kindergarten_id,
                "role": user_role,
            },
            "system_overview": {
                "active_children": int(active_children_count),
                "present_today": int(present_today_count),
                "pending_reports": int(pending_reports_count),
                "incidents_today": int(incidents_today_count),
                "attendance_rate": attendance_rate,
            },
            "health_score": health_score,
            "validation_status": validation_status,
            "data_quality": {
                "overall_quality": quality_result.score,
                "issues": quality_result.issues,
                "last_evaluated_at": quality_result.timestamp.isoformat(),
            },
        }


# Module-level singleton consumed by analytics_ws and other callers.
# (Restored: dropped during the agency-reports extraction refactor; present on
# main and other branches. Without it, `from data_quality_service import
# data_quality_service` fails once the app import gets past the frontend layer.)
data_quality_service = DataQualityService()
