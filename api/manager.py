"""
Manager domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
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
    today = date.today()
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

    # Attendance Trend (Last 7 days)
    attendance_trend = []
    for i in range(7):
        d = today - timedelta(days=(6-i))
        # Get simplified Arabic day name logic or just use English day name and let frontend handled it
        day_date = d
        count = db.query(func.count(models.AttendanceLog.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.AttendanceLog.date == day_date
        ).scalar() or 0
        attendance_trend.append({"date": str(day_date), "count": count})

    # Enrollment Status Breakdown
    enrollment_stats = db.query(
        models.EnrollmentApplication.status, 
        func.count(models.EnrollmentApplication.id)
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id
    ).group_by(models.EnrollmentApplication.status).all()
    
    enrollment_breakdown = {status.name: count for status, count in enrollment_stats}

    # Classes with enrollment counts
    classes = db.query(models.Class).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active == True
    ).all()
    
    classes_data = []
    for c in classes:
        enrolled_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.class_id == c.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0
        
        present_count = db.query(func.count(models.AttendanceLog.id)).join(
             models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.class_id == c.id,
            models.AttendanceLog.date == today
        ).scalar() or 0

        pending_assignment = db.query(func.count(models.EnrollmentApplication.id)).filter(
             models.EnrollmentApplication.class_id == c.id,
             models.EnrollmentApplication.status.in_([models.EnrollmentStatus.PENDING_REVIEW, models.EnrollmentStatus.WAITLISTED])
        ).scalar() or 0

        classes_data.append({
            "id": c.id,
            "name": c.name_ar or c.name_en,
            "capacity": c.capacity_total,
            "enrolled": enrolled_count,
            "present": present_count,
            "pending": pending_assignment
        })

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


# ============================================================================
# Admin Dashboard
# ============================================================================

@router.get("/admin/dashboard")
def get_admin_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive admin dashboard with system-wide statistics"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    today = date.today()
    week_ago = today - timedelta(days=7)

    # System-wide statistics
    total_kindergartens = db.query(func.count(models.Kindergarten.id)).scalar() or 0
    active_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).scalar() or 0

    # Total users by role
    user_stats = db.query(
        models.User.role,
        func.count(models.User.id)
    ).group_by(models.User.role).all()

    users_by_role = {role.name: count for role, count in user_stats}

    # Total children and enrollments
    total_children = db.query(func.count(models.Child.id)).scalar() or 0
    total_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    # Pending applications across all kindergartens
    pending_applications = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW
    ).scalar() or 0

    # Today's attendance across all kindergartens
    attendance_today = db.query(func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date == today
    ).scalar() or 0

    # Pending daily reports
    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.status == models.DailyReportStatus.SUBMITTED
    ).scalar() or 0

    # Recent incidents (last 7 days)
    recent_incidents = db.query(func.count(models.Incident.id)).filter(
        func.date(models.Incident.occurred_at) >= week_ago
    ).scalar() or 0

    # System-wide attendance trend (last 7 days)
    attendance_trend = []
    for i in range(7):
        d = today - timedelta(days=(6-i))
        count = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date == d
        ).scalar() or 0
        attendance_trend.append({"date": str(d), "count": count})

    # Enrollment status breakdown across all kindergartens
    enrollment_stats = db.query(
        models.EnrollmentApplication.status,
        func.count(models.EnrollmentApplication.id)
    ).group_by(models.EnrollmentApplication.status).all()

    enrollment_breakdown = {status.name: count for status, count in enrollment_stats}

    # Kindergarten performance overview
    kindergartens = db.query(models.Kindergarten).all()
    kg_performance = []
    for kg in kindergartens:
        # Enrollment count for this KG
        kg_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kg.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Today's attendance for this KG
        kg_attendance = db.query(func.count(models.AttendanceLog.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kg.id,
            models.AttendanceLog.date == today
        ).scalar() or 0

        # Pending reports for this KG
        kg_pending_reports = db.query(func.count(models.DailyReport.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kg.id,
            models.DailyReport.status == models.DailyReportStatus.SUBMITTED
        ).scalar() or 0

        # License status
        license_status = "valid"
        if kg.license_valid_until:
            days_until_expiry = (kg.license_valid_until - today).days
            if days_until_expiry < 0:
                license_status = "expired"
            elif days_until_expiry < 30:
                license_status = "expiring_soon"

        # Calculate total capacity from all classes in this kindergarten
        kg_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kg.id,
            models.Class.is_active == True
        ).scalar() or 0

        kg_performance.append({
            "id": kg.id,
            "name_ar": kg.name_ar,
            "name_en": kg.name_en,
            "status": kg.status.value,
            "enrollments": kg_enrollments,
            "attendance_today": kg_attendance,
            "pending_reports": kg_pending_reports,
            "license_status": license_status,
            "capacity_utilization": round((kg_enrollments / kg_capacity) * 100, 1) if kg_capacity > 0 else 0
        })

    # System alerts
    alerts = []

    # License expiry alerts
    expiring_soon = db.query(models.Kindergarten).filter(
        models.Kindergarten.license_valid_until.isnot(None),
        models.Kindergarten.license_valid_until <= today + timedelta(days=30)
    ).all()

    for kg in expiring_soon:
        days = (kg.license_valid_until - today).days
        alerts.append({
            "type": "license_expiry",
            "message": f"License for {kg.name_ar} expires in {days} days",
            "priority": "critical" if days < 0 else "high",
            "kindergarten_id": kg.id
        })

    # High pending applications
    if pending_applications > 10:
        alerts.append({
            "type": "high_pending_applications",
            "message": f"{pending_applications} applications pending review across all kindergartens",
            "priority": "high"
        })

    # Low attendance rate alert (if attendance < 70% of enrollments)
    if total_enrollments > 0:
        attendance_rate = (attendance_today / total_enrollments) * 100
        if attendance_rate < 70:
            alerts.append({
                "type": "low_attendance",
                "message": f"Today's attendance rate is only {attendance_rate:.1f}%",
                "priority": "medium"
            })

    # Recent high incident count
    if recent_incidents > 5:
        alerts.append({
            "type": "high_incidents",
            "message": f"{recent_incidents} incidents reported in the last 7 days",
            "priority": "medium"
        })

    dashboard = {
        "system_overview": {
            "total_kindergartens": total_kindergartens,
            "active_kindergartens": active_kindergartens,
            "total_users": sum(users_by_role.values()),
            "users_by_role": users_by_role,
            "total_children": total_children,
            "total_enrollments": total_enrollments
        },
        "summary": {
            "pending_applications": pending_applications,
            "attendance_today": attendance_today,
            "pending_daily_reports": pending_reports,
            "recent_incidents": recent_incidents,
            "attendance_rate": round((attendance_today / total_enrollments) * 100, 1) if total_enrollments > 0 else 0
        },
        "charts": {
            "attendance": attendance_trend,
            "enrollment": enrollment_breakdown
        },
        "kindergartens": kg_performance,
        "alerts": alerts,
        "generated_at": datetime.now().isoformat()
    }

    return dashboard
