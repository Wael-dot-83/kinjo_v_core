"""
Manager domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))

import models
import validators
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Manager"])

@router.get("/manager/dashboard")
def get_manager_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive manager dashboard"""
    validators.validate_manager_role(current_user)

    kindergarten_id = current_user.kindergarten_id
    if kindergarten_id is None:
        # validate_manager_role also admits ADMIN; this dashboard is
        # per-kindergarten and unscoped users have nothing to see here.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No kindergarten is associated with this account")

    # Get kindergarten info
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()
    if kindergarten is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Associated kindergarten not found")

    # Pending enrollment applications
    pending_applications = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW
    ).scalar() or 0

    # Active enrollments
    active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    # Waitlisted children
    waitlisted = db.query(func.count(models.WaitlistEntry.id)).join(
        models.EnrollmentApplication
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.WaitlistEntry.status == models.WaitlistStatus.WAITLISTED
    ).scalar() or 0

    # Today's attendance
    today = datetime.now(_JORDAN_TZ).date()
    attendance_today = db.query(func.count(models.AttendanceLog.id)).join(
        models.Child
    ).join(
        models.EnrollmentApplication
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.AttendanceLog.date == today
    ).scalar() or 0

    # Pending daily reports (submitted but not approved)
    pending_reports = db.query(func.count(models.DailyReport.id)).join(
        models.Child
    ).join(
        models.EnrollmentApplication
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.DailyReport.status == models.DailyReportStatus.SUBMITTED
    ).scalar() or 0

    # Recent incidents (last 7 days)
    week_ago = today - timedelta(days=7)
    recent_incidents = db.query(func.count(models.Incident.id)).filter(
        models.Incident.kindergarten_id == kindergarten_id,
        func.date(models.Incident.occurred_at) >= week_ago
    ).scalar() or 0

    # Attendance Trend (Last 7 days) — single GROUP BY query
    seven_days_ago = today - timedelta(days=6)
    attendance_by_date = {
        row[0]: row[1]
        for row in db.query(
            models.AttendanceLog.date,
            func.count(models.AttendanceLog.id),
        )
        .join(models.Child)
        .join(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.AttendanceLog.date >= seven_days_ago,
            models.AttendanceLog.date <= today,
        )
        .group_by(models.AttendanceLog.date)
        .all()
    }
    attendance_trend = [
        {"date": str(today - timedelta(days=6 - i)), "count": attendance_by_date.get(today - timedelta(days=6 - i), 0)}
        for i in range(7)
    ]

    # Enrollment Status Breakdown
    enrollment_stats = db.query(
        models.EnrollmentApplication.status,
        func.count(models.EnrollmentApplication.id)
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id
    ).group_by(models.EnrollmentApplication.status).all()

    enrollment_breakdown = {status.name: count for status, count in enrollment_stats}

    # Classes with enrollment counts — 3 batch GROUP BY queries instead of 3N
    classes = db.query(models.Class).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active == True
    ).all()

    class_ids = [c.id for c in classes]
    enrolled_by_class = {
        row[0]: row[1]
        for row in db.query(
            models.EnrollmentApplication.class_id,
            func.count(models.EnrollmentApplication.id),
        )
        .filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .group_by(models.EnrollmentApplication.class_id)
        .all()
    } if class_ids else {}

    present_by_class = {
        row[0]: row[1]
        for row in db.query(
            models.EnrollmentApplication.class_id,
            func.count(models.AttendanceLog.id),
        )
        .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
        .join(models.AttendanceLog, models.AttendanceLog.child_id == models.Child.id)
        .filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.AttendanceLog.date == today,
        )
        .group_by(models.EnrollmentApplication.class_id)
        .all()
    } if class_ids else {}

    pending_by_class = {
        row[0]: row[1]
        for row in db.query(
            models.EnrollmentApplication.class_id,
            func.count(models.EnrollmentApplication.id),
        )
        .filter(
            models.EnrollmentApplication.class_id.in_(class_ids),
            models.EnrollmentApplication.status.in_([
                models.EnrollmentStatus.PENDING_REVIEW,
                models.EnrollmentStatus.WAITLISTED,
            ]),
        )
        .group_by(models.EnrollmentApplication.class_id)
        .all()
    } if class_ids else {}

    classes_data = [
        {
            "id": c.id,
            "name": c.name_ar or c.name_en,
            "name_ar": c.name_ar,
            "name_en": c.name_en,
            "capacity": c.capacity_total,
            "enrolled": enrolled_by_class.get(c.id, 0),
            "present": present_by_class.get(c.id, 0),
            "pending": pending_by_class.get(c.id, 0),
        }
        for c in classes
    ]

    # Supervisor coverage: classes with at least one active assignment.
    covered_class_ids = {
        row[0]
        for row in db.query(models.SupervisorAssignment.class_id)
        .filter(
            models.SupervisorAssignment.class_id.in_(class_ids),
            models.SupervisorAssignment.deleted_at.is_(None),
        )
        .distinct()
        .all()
    } if class_ids else set()
    classes_without_supervisor = [
        {"id": c.id, "name_ar": c.name_ar, "name_en": c.name_en}
        for c in classes if c.id not in covered_class_ids
    ]
    classes_near_capacity = [
        {
            "id": c.id,
            "name_ar": c.name_ar,
            "name_en": c.name_en,
            "occupied": enrolled_by_class.get(c.id, 0),
            "capacity": c.capacity_total,
        }
        for c in classes
        if c.capacity_total and enrolled_by_class.get(c.id, 0) >= 0.9 * c.capacity_total
    ]

    supervisors_count = db.query(func.count(models.User.id)).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.kindergarten_id == kindergarten_id,
        models.User.deleted_at.is_(None),
    ).scalar() or 0

    pending_absence_requests = db.query(func.count(models.AbsenceRequest.id)).filter(
        models.AbsenceRequest.kindergarten_id == kindergarten_id,
        models.AbsenceRequest.status == models.AbsenceRequestStatus.SUBMITTED,
    ).scalar() or 0

    reports_sent_today = db.query(func.count(models.DailyReport.id)).join(
        models.Child
    ).join(
        models.EnrollmentApplication
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.DailyReport.status == models.DailyReportStatus.SENT_TO_PARENT,
        models.DailyReport.date == today,
    ).scalar() or 0

    dashboard = {
        "kindergarten": {
            "id": kindergarten.id,
            "name_ar": kindergarten.name_ar,
            "name_en": kindergarten.name_en,
            "status": kindergarten.status.value,
            "license_valid_until": kindergarten.license_valid_until
        },
        "summary": {
            "pending_applications": pending_applications,
            "active_enrollments": active_enrollments,
            "waitlisted_children": waitlisted,
            "attendance_today": attendance_today,
            "pending_daily_reports": pending_reports,
            "recent_incidents": recent_incidents,
            "pending_absence_requests": pending_absence_requests,
            "reports_sent_today": reports_sent_today,
            "supervisors_count": supervisors_count,
        },
        "charts": {
            "attendance": attendance_trend,
            "enrollment": enrollment_breakdown
        },
        "classes": classes_data,
        "classes_without_supervisor": classes_without_supervisor,
        "classes_near_capacity": classes_near_capacity,
        "alerts": []
    }

    # Add alerts
    if pending_applications > 0:
        dashboard["alerts"].append({
            "type": "pending_applications",
            "message": f"{pending_applications} enrollment applications pending review",
            "priority": "high"
        })

    if pending_reports > 0:
        dashboard["alerts"].append({
            "type": "pending_reports",
            "message": f"{pending_reports} daily reports pending approval",
            "priority": "medium"
        })

    if kindergarten.license_valid_until:
        days_until_expiry = (kindergarten.license_valid_until - today).days
        if days_until_expiry < 30:
            dashboard["alerts"].append({
                "type": "license_expiry",
                "message": f"License expires in {days_until_expiry} days",
                "priority": "critical" if days_until_expiry < 0 else "high"
            })

    return dashboard

