"""
Optimized Database Queries for KinJo Platform
=============================================
This module provides optimized query patterns to prevent N+1 problems
and improve database performance through:
- Eager loading with joinedload/selectinload
- Efficient batch operations
- Query result caching
- Denormalized views for dashboards
"""
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload, selectinload, contains_eager
from sqlalchemy import func, and_, or_, case, text
from sqlalchemy.future import select
from functools import lru_cache

import models


# ============================================================================
# Enrollment Queries (Optimized)
# ============================================================================

class EnrollmentQueries:
    """Optimized enrollment-related queries"""
    
    @staticmethod
    def get_enrollment_with_related(
        db: Session,
        enrollment_id: int
    ) -> Optional[models.EnrollmentApplication]:
        """
        Get enrollment with all related data in single query
        Prevents N+1 when accessing child, kindergarten, class
        """
        return db.query(models.EnrollmentApplication).options(
            joinedload(models.EnrollmentApplication.child)
                .joinedload(models.Child.parent),
            joinedload(models.EnrollmentApplication.kindergarten),
            joinedload(models.EnrollmentApplication.assigned_class),
            joinedload(models.EnrollmentApplication.waitlist_entry)
        ).filter(
            models.EnrollmentApplication.id == enrollment_id
        ).first()
    
    @staticmethod
    def get_kindergarten_enrollments(
        db: Session,
        kindergarten_id: int,
        status_filter: Optional[models.EnrollmentStatus] = None,
        include_children: bool = True
    ) -> List[models.EnrollmentApplication]:
        """
        Get all enrollments for a kindergarten with optimized loading
        """
        query = db.query(models.EnrollmentApplication)
        
        # Always load related data efficiently
        if include_children:
            query = query.options(
                selectinload(models.EnrollmentApplication.child),
                selectinload(models.EnrollmentApplication.assigned_class)
            )
        
        query = query.filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        )
        
        if status_filter:
            query = query.filter(
                models.EnrollmentApplication.status == status_filter
            )
        
        return query.order_by(
            models.EnrollmentApplication.created_at.desc()
        ).all()
    
    @staticmethod
    def get_active_enrollment_counts_by_class(
        db: Session,
        kindergarten_id: int
    ) -> Dict[int, int]:
        """
        Get enrollment counts per class in single query
        Returns: {class_id: count}
        """
        results = db.query(
            models.EnrollmentApplication.class_id,
            func.count(models.EnrollmentApplication.id).label('count')
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.class_id.isnot(None)
        ).group_by(
            models.EnrollmentApplication.class_id
        ).all()
        
        return {r.class_id: r.count for r in results}


# ============================================================================
# Attendance Queries (Optimized)
# ============================================================================

class AttendanceQueries:
    """Optimized attendance-related queries"""
    
    @staticmethod
    def get_daily_attendance_with_children(
        db: Session,
        kindergarten_id: int,
        target_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get attendance for a day with child info in optimized query
        Returns denormalized data for fast access
        """
        # Subquery to get enrolled children IDs
        enrolled_children = db.query(
            models.EnrollmentApplication.child_id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).subquery()
        
        # Main query with join
        results = db.query(
            models.AttendanceLog,
            models.Child
        ).join(
            models.Child,
            models.AttendanceLog.child_id == models.Child.id
        ).filter(
            models.AttendanceLog.date == target_date,
            models.AttendanceLog.child_id.in_(select(enrolled_children))
        ).all()
        
        return [
            {
                "attendance_id": log.id,
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "check_in_at": log.check_in_at,
                "check_out_at": log.check_out_at,
                "method": log.method.value,
                "dropped_by": log.dropped_by_name,
                "picked_by": log.picked_by_name
            }
            for log, child in results
        ]
    
    @staticmethod
    def get_attendance_summary(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get aggregated attendance statistics in single query
        """
        # Get expected child count
        enrolled_count = db.query(
            func.count(models.EnrollmentApplication.id)
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar()
        
        # Get attendance counts by day
        daily_counts = db.query(
            models.AttendanceLog.date,
            func.count(models.AttendanceLog.id).label('present_count')
        ).join(
            models.EnrollmentApplication,
            and_(
                models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
                models.EnrollmentApplication.kindergarten_id == kindergarten_id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            )
        ).filter(
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date
        ).group_by(
            models.AttendanceLog.date
        ).all()
        
        # Calculate statistics
        total_days = len(daily_counts)
        total_present = sum(d.present_count for d in daily_counts)
        expected_total = enrolled_count * total_days if total_days > 0 else 0
        
        return {
            "enrolled_children": enrolled_count,
            "days_tracked": total_days,
            "total_present": total_present,
            "expected_total": expected_total,
            "attendance_rate": (total_present / expected_total * 100) if expected_total > 0 else 0,
            "daily_breakdown": [
                {"date": d.date.isoformat(), "present": d.present_count}
                for d in daily_counts
            ]
        }
    
    @staticmethod
    def get_children_attendance_status(
        db: Session,
        child_ids: List[int],
        target_date: date
    ) -> Dict[int, bool]:
        """
        Batch check attendance status for multiple children
        Returns: {child_id: is_present}
        """
        present_children = db.query(
            models.AttendanceLog.child_id
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date == target_date
        ).all()
        
        present_set = {r.child_id for r in present_children}
        return {cid: cid in present_set for cid in child_ids}


# ============================================================================
# Supervisor Queries (Optimized)
# ============================================================================

class SupervisorQueries:
    """Optimized supervisor-related queries"""
    
    @staticmethod
    def get_supervisor_dashboard_data(
        db: Session,
        supervisor_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """
        Get all dashboard data in optimized queries
        Minimizes database round trips
        """
        # Get assigned classes with enrollment counts in single query
        classes_data = db.query(
            models.Class,
            func.count(models.EnrollmentApplication.id).label('enrolled_count')
        ).join(
            models.SupervisorAssignment,
            models.SupervisorAssignment.class_id == models.Class.id
        ).outerjoin(
            models.EnrollmentApplication,
            and_(
                models.EnrollmentApplication.class_id == models.Class.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            )
        ).filter(
            models.SupervisorAssignment.supervisor_id == supervisor_id,
            models.SupervisorAssignment.start_date <= target_date,
            or_(
                models.SupervisorAssignment.end_date.is_(None),
                models.SupervisorAssignment.end_date >= target_date
            )
        ).group_by(models.Class.id).all()
        
        class_ids = [c.id for c, _ in classes_data]
        
        # Get children IDs in assigned classes
        children_in_classes = db.query(
            models.EnrollmentApplication.child_id,
            models.EnrollmentApplication.class_id
        ).filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()
        
        child_ids = [c.child_id for c in children_in_classes]
        
        # Get attendance for today
        attendance_data = db.query(
            models.AttendanceLog.child_id,
            models.AttendanceLog.check_in_at,
            models.AttendanceLog.check_out_at
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date == target_date
        ).all()
        
        present_children = {a.child_id for a in attendance_data}
        
        # Get pending reports
        reports_done = db.query(
            models.DailyReport.child_id
        ).filter(
            models.DailyReport.child_id.in_(child_ids),
            models.DailyReport.date == target_date
        ).all()
        
        reports_done_set = {r.child_id for r in reports_done}
        
        return {
            "classes": [
                {
                    "id": c.id,
                    "name_ar": c.name_ar,
                    "name_en": c.name_en,
                    "capacity": c.capacity_total,
                    "enrolled": count,
                    "age_range": f"{c.min_age_months}-{c.max_age_months} months"
                }
                for c, count in classes_data
            ],
            "total_children": len(child_ids),
            "attendance_summary": {
                "present": len(present_children),
                "absent": len(child_ids) - len(present_children),
                "checked_out": sum(1 for a in attendance_data if a.check_out_at)
            },
            "reports_pending": len(child_ids) - len(reports_done_set),
            "reports_completed": len(reports_done_set)
        }
    
    @staticmethod
    def get_class_children_with_status(
        db: Session,
        class_id: int,
        target_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get children in class with today's status
        Single optimized query
        """
        results = db.query(
            models.Child,
            models.AttendanceLog,
            models.DailyReport
        ).select_from(
            models.EnrollmentApplication
        ).join(
            models.Child,
            models.Child.id == models.EnrollmentApplication.child_id
        ).outerjoin(
            models.AttendanceLog,
            and_(
                models.AttendanceLog.child_id == models.Child.id,
                models.AttendanceLog.date == target_date
            )
        ).outerjoin(
            models.DailyReport,
            and_(
                models.DailyReport.child_id == models.Child.id,
                models.DailyReport.date == target_date
            )
        ).filter(
            models.EnrollmentApplication.class_id == class_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()
        
        return [
            {
                "id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "gender": child.gender.value,
                "is_present": attendance is not None,
                "check_in_at": attendance.check_in_at.isoformat() if attendance else None,
                "check_out_at": attendance.check_out_at.isoformat() if attendance and attendance.check_out_at else None,
                "has_daily_report": report is not None,
                "report_status": report.status.value if report else None
            }
            for child, attendance, report in results
        ]


# ============================================================================
# KPI Queries (Optimized)
# ============================================================================

class KPIQueries:
    """Optimized KPI calculation queries"""
    
    @staticmethod
    def get_attendance_rate_optimized(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> float:
        """
        Calculate attendance rate using aggregated query
        """
        # Subquery for active enrollments
        active_children = db.query(
            models.EnrollmentApplication.child_id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
        
        # Count enrolled children
        enrolled_count = active_children.count()
        
        if enrolled_count == 0:
            return 0.0
        
        # Count operating days (exclude closed days)
        closed_days = db.query(
            func.count(models.OperatingCalendar.id)
        ).filter(
            models.OperatingCalendar.kindergarten_id == kindergarten_id,
            models.OperatingCalendar.date >= start_date,
            models.OperatingCalendar.date <= end_date,
            models.OperatingCalendar.is_open == False
        ).scalar()
        
        total_days = (end_date - start_date).days + 1
        operating_days = total_days - closed_days
        
        if operating_days <= 0:
            return 0.0
        
        # Count actual attendance
        attendance_count = db.query(
            func.count(models.AttendanceLog.id)
        ).filter(
            models.AttendanceLog.child_id.in_(active_children),
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date
        ).scalar()
        
        expected = enrolled_count * operating_days
        return (attendance_count / expected * 100) if expected > 0 else 0.0
    
    @staticmethod
    def get_incident_statistics(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get incident statistics in single query with grouping
        """
        # All incidents
        results = db.query(
            models.Incident.severity_level,
            func.count(models.Incident.id).label('count')
        ).filter(
            models.Incident.kindergarten_id == kindergarten_id,
            models.Incident.occurred_at >= datetime.combine(start_date, datetime.min.time()),
            models.Incident.occurred_at <= datetime.combine(end_date, datetime.max.time())
        ).group_by(
            models.Incident.severity_level
        ).all()
        
        stats = {level.value: 0 for level in models.SeverityLevel}
        for r in results:
            stats[r.severity_level.value] = r.count
        
        total = sum(stats.values())
        serious = stats.get('high', 0) + stats.get('critical', 0)
        
        return {
            "total_incidents": total,
            "serious_incidents": serious,
            "by_severity": stats
        }
    
    @staticmethod
    def get_ratio_compliance_summary(
        db: Session,
        kindergarten_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get ratio compliance summary
        """
        results = db.query(
            func.sum(models.RatioCompliance.operating_minutes).label('total_operating'),
            func.sum(models.RatioCompliance.compliant_minutes).label('total_compliant'),
            func.avg(models.RatioCompliance.staff_count_avg).label('avg_staff'),
            func.avg(models.RatioCompliance.child_count_avg).label('avg_children')
        ).filter(
            models.RatioCompliance.kindergarten_id == kindergarten_id,
            models.RatioCompliance.date >= start_date,
            models.RatioCompliance.date <= end_date
        ).first()
        
        total_operating = results.total_operating or 0
        total_compliant = results.total_compliant or 0
        
        return {
            "total_operating_minutes": total_operating,
            "total_compliant_minutes": total_compliant,
            "compliance_rate": (total_compliant / total_operating * 100) if total_operating > 0 else 0,
            "average_staff": round(results.avg_staff or 0, 1),
            "average_children": round(results.avg_children or 0, 1)
        }


# ============================================================================
# Batch Operations (Optimized)
# ============================================================================

class BatchOperations:
    """Batch database operations for improved performance"""
    
    @staticmethod
    def bulk_create_attendance(
        db: Session,
        attendance_records: List[Dict[str, Any]]
    ) -> List[models.AttendanceLog]:
        """
        Create multiple attendance records efficiently
        """
        logs = [
            models.AttendanceLog(
                child_id=record['child_id'],
                date=record['date'],
                check_in_at=record['check_in_at'],
                method=record['method'],
                dropped_by_name=record.get('dropped_by_name')
            )
            for record in attendance_records
        ]
        
        db.bulk_save_objects(logs)
        db.commit()
        
        return logs
    
    @staticmethod
    def bulk_update_report_status(
        db: Session,
        report_ids: List[int],
        new_status: models.DailyReportStatus,
        approved_by: Optional[int] = None
    ) -> int:
        """
        Update multiple reports in single query
        Returns: number of updated records
        """
        update_data = {"status": new_status}
        if new_status == models.DailyReportStatus.APPROVED and approved_by:
            update_data["approved_by"] = approved_by
            update_data["approved_at"] = datetime.now()
        
        result = db.query(models.DailyReport).filter(
            models.DailyReport.id.in_(report_ids)
        ).update(update_data, synchronize_session='fetch')
        
        db.commit()
        return result


# ============================================================================
# Query Result Caching
# ============================================================================

class CachedQueries:
    """
    Queries with result caching for frequently accessed data
    Note: In production, use Redis or similar for distributed caching
    """
    
    @staticmethod
    @lru_cache(maxsize=100)
    def get_kindergarten_classes(kindergarten_id: int) -> tuple:
        """
        Cache kindergarten class list (rarely changes)
        Note: Returns tuple for hashability, convert to list when using
        """
        # This would need db session passed differently in production
        # Documenting the pattern
        pass
    
    @staticmethod
    def invalidate_class_cache(kindergarten_id: int):
        """Invalidate cache when classes are modified"""
        CachedQueries.get_kindergarten_classes.cache_clear()
