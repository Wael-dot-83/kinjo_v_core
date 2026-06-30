"""
Manager domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
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

    # Get kindergarten info
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

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
            "capacity": c.capacity_total,
            "enrolled": enrolled_by_class.get(c.id, 0),
            "present": present_by_class.get(c.id, 0),
            "pending": pending_by_class.get(c.id, 0),
        }
        for c in classes
    ]

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
            "recent_incidents": recent_incidents
        },
        "charts": {
            "attendance": attendance_trend,
            "enrollment": enrollment_breakdown
        },
        "classes": classes_data,
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

