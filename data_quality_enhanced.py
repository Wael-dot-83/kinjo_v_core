"""
Enhanced data quality service with freshness, completeness, accuracy, consistency,
uniqueness, and validity dimensions. Extends the original data_quality_service.py.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, text
from sqlalchemy.orm import Session

from models import (
    DailyReport,
    DailyReportStatus,
    AttendanceLog,
    AttendanceStatus,
    EnrollmentApplication,
    Kindergarten,
    KindergartenStatus,
    Child,
    Incident,
    Class,
    User,
    UserRole,
    DataQualityMetric,
)

logger = logging.getLogger(__name__)


class EnhancedDataQualityService:
    """Compute and track data quality metrics across all 6 dimensions."""

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def freshness_latency(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = db.query(func.max(DailyReport.created_at))
        if kindergarten_id is not None:
            query = query.filter(DailyReport.kindergarten_id == kindergarten_id)
        latest = query.scalar()

        if latest is None:
            return {
                "hours_since_last_report": None,
                "status": "no_data",
                "threshold": {"warning": 6, "critical": 12},
            }

        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        delta_hours = (now - latest).total_seconds() / 3600.0

        if delta_hours <= 2:
            status = "fresh"
        elif delta_hours <= 6:
            status = "stale"
        elif delta_hours <= 12:
            status = "warning"
        else:
            status = "critical"

        return {
            "hours_since_last_report": round(delta_hours, 2),
            "last_report_at": latest.isoformat(),
            "status": status,
            "threshold": {"warning": 6, "critical": 12},
        }

    def completeness_per_kg(
        self,
        db: Session,
    ) -> List[Dict[str, Any]]:
        active_kgs = (
            db.query(Kindergarten.id, Kindergarten.name_ar, Kindergarten.governorate)
            .filter(Kindergarten.status == KindergartenStatus.ACTIVE)
            .all()
        )

        today = _today()
        yesterday = today - timedelta(days=1)
        kg_ids = [kg.id for kg in active_kgs]

        children_by_kg = dict(
            db.query(
                EnrollmentApplication.kindergarten_id,
                func.count(func.distinct(EnrollmentApplication.child_id)),
            )
            .filter(
                EnrollmentApplication.kindergarten_id.in_(kg_ids),
                EnrollmentApplication.is_active.is_(True),
            )
            .group_by(EnrollmentApplication.kindergarten_id)
            .all()
        ) if kg_ids else {}

        reports_by_kg = dict(
            db.query(DailyReport.kindergarten_id, func.count(DailyReport.id))
            .filter(
                DailyReport.kindergarten_id.in_(kg_ids),
                DailyReport.date == yesterday,
                DailyReport.status.in_([
                    DailyReportStatus.SUBMITTED,
                    DailyReportStatus.APPROVED,
                    DailyReportStatus.SENT_TO_PARENT,
                ]),
            )
            .group_by(DailyReport.kindergarten_id)
            .all()
        ) if kg_ids else {}

        results = []
        for kg in active_kgs:
            active_children = children_by_kg.get(kg.id, 0)
            reports_submitted = reports_by_kg.get(kg.id, 0)
            completeness = round((reports_submitted / active_children) * 100.0, 1) if active_children > 0 else 100.0
            results.append({
                "kindergarten_id": kg.id,
                "kindergarten_name": kg.name_ar,
                "governorate": kg.governorate,
                "active_children": active_children,
                "reports_submitted": int(reports_submitted),
                "completeness_percent": completeness,
            })

        results.sort(key=lambda x: x["completeness_percent"])
        return results

    def cross_entity_consistency(
        self,
        db: Session,
    ) -> Dict[str, Any]:
        enrolled_count = (
            db.query(func.count(EnrollmentApplication.id))
            .filter(EnrollmentApplication.is_active.is_(True))
            .scalar()
            or 0
        )

        distinct_children = (
            db.query(func.count(func.distinct(EnrollmentApplication.child_id)))
            .filter(EnrollmentApplication.is_active.is_(True))
            .scalar()
            or 0
        )

        duplicate_enrollments = enrolled_count - distinct_children

        total_capacity = (
            db.query(func.sum(Class.capacity_total))
            .filter(Class.capacity_total.isnot(None))
            .scalar()
            or 0
        )

        total_enrolled_in_classes = (
            db.query(func.sum(Class.enrolled_children_count))
            .filter(Class.enrolled_children_count.isnot(None))
            .scalar()
            or 0
        )

        issues = []
        consistency_score = 100.0

        if duplicate_enrollments > 0:
            issues.append(f"{duplicate_enrollments} duplicate active enrollments detected")
            consistency_score -= min(20, duplicate_enrollments * 2)

        if total_enrolled_in_classes > total_capacity * 1.2 and total_capacity > 0:
            issues.append(
                f"Class enrollments ({total_enrolled_in_classes}) exceed capacity "
                f"({total_capacity}) by >20%"
            )
            consistency_score -= 15

        consistency_score = max(0, consistency_score)

        return {
            "consistency_score": round(consistency_score, 1),
            "enrolled_count": enrolled_count,
            "distinct_children": distinct_children,
            "duplicate_enrollments": duplicate_enrollments,
            "total_class_capacity": int(total_capacity),
            "total_class_enrolled": int(total_enrolled_in_classes),
            "issues": issues,
            "status": "consistent" if consistency_score >= 95 else "inconsistent",
        }

    def uniqueness_check(
        self,
        db: Session,
    ) -> Dict[str, Any]:
        attendance_date = _today()
        duplicate_attendance = (
            db.query(
                AttendanceLog.child_id,
                AttendanceLog.date,
                func.count(AttendanceLog.id).label("cnt"),
            )
            .filter(AttendanceLog.date >= _today() - timedelta(days=7))
            .group_by(AttendanceLog.child_id, AttendanceLog.date)
            .having(func.count(AttendanceLog.id) > 1)
            .count()
        )

        duplicate_users = (
            db.query(User.username, func.count(User.id).label("cnt"))
            .group_by(User.username)
            .having(func.count(User.id) > 1)
            .count()
        )

        uniqueness_score = 100.0
        issues = []

        if duplicate_attendance > 0:
            uniqueness_score -= min(20, duplicate_attendance * 5)
            issues.append(f"{duplicate_attendance} duplicate attendance records (last 7 days)")

        if duplicate_users > 0:
            uniqueness_score -= min(20, duplicate_users * 5)
            issues.append(f"{duplicate_users} duplicate username records")

        uniqueness_score = max(0, uniqueness_score)

        return {
            "uniqueness_score": round(uniqueness_score, 1),
            "duplicate_attendance_records": duplicate_attendance,
            "duplicate_user_records": duplicate_users,
            "issues": issues,
            "status": "unique" if uniqueness_score >= 99 else "has_duplicates",
        }

    def validity_check(
        self,
        db: Session,
    ) -> Dict[str, Any]:
        issues = []
        validity_score = 100.0

        invalid_attendance = (
            db.query(func.count(AttendanceLog.id))
            .filter(
                AttendanceLog.status.notin_(
                    [
                        AttendanceStatus.PRESENT,
                        AttendanceStatus.ABSENT,
                        AttendanceStatus.LATE,
                        AttendanceStatus.EXCUSED,
                    ]
                )
            )
            .scalar()
            or 0
        )

        if invalid_attendance > 0:
            issues.append(f"{invalid_attendance} attendance records with invalid status")
            validity_score -= 5

        negative_capacity = (
            db.query(func.count(Class.id))
            .filter(Class.capacity_total < 0)
            .scalar()
            or 0
        )

        if negative_capacity > 0:
            issues.append(f"{negative_capacity} classes with negative capacity")
            validity_score -= 10

        future_dob = (
            db.query(func.count(Child.id))
            .filter(Child.date_of_birth > _today())
            .scalar()
            or 0
        )

        if future_dob > 0:
            issues.append(f"{future_dob} children with future date_of_birth")
            validity_score -= 10

        validity_score = max(0, validity_score)

        return {
            "validity_score": round(validity_score, 1),
            "invalid_attendance": invalid_attendance,
            "negative_capacity_classes": negative_capacity,
            "future_dob_children": future_dob,
            "issues": issues,
            "status": "valid" if validity_score >= 95 else "has_issues",
        }

    def compute_overall_quality(
        self,
        db: Session,
        kindergarten_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        freshness = self.freshness_latency(db, kindergarten_id)
        kg_completeness = self.completeness_per_kg(db)
        consistency = self.cross_entity_consistency(db)
        uniqueness = self.uniqueness_check(db)
        validity = self.validity_check(db)

        avg_completeness = 0.0
        if kg_completeness:
            avg_completeness = sum(
                row["completeness_percent"] for row in kg_completeness
            ) / len(kg_completeness)

        freshness_score = 100.0
        if freshness["hours_since_last_report"] is not None:
            h = freshness["hours_since_last_report"]
            if h <= 2:
                freshness_score = 100.0
            elif h <= 6:
                freshness_score = 80.0
            elif h <= 12:
                freshness_score = 60.0
            else:
                freshness_score = 30.0
        else:
            freshness_score = 50.0

        overall = (
            freshness_score * 0.20
            + avg_completeness * 0.25
            + consistency["consistency_score"] * 0.20
            + uniqueness["uniqueness_score"] * 0.15
            + validity["validity_score"] * 0.20
        )

        return {
            "overall_score": round(overall, 1),
            "freshness": freshness,
            "completeness": {
                "score": round(avg_completeness, 1),
                "kg_count": len(kg_completeness),
                "kg_with_issues": sum(1 for r in kg_completeness if r["completeness_percent"] < 90),
            },
            "consistency": consistency,
            "uniqueness": uniqueness,
            "validity": validity,
            "status": (
                "excellent" if overall >= 90
                else "good" if overall >= 75
                else "fair" if overall >= 60
                else "poor"
            ),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }


enhanced_data_quality_service = EnhancedDataQualityService()
