"""
Parent domain endpoints
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

router = APIRouter(tags=["Parent"])

@router.get("/parent/dashboard")
def get_parent_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive parent dashboard"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()

    if not parent_profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    # Get all children
    children = db.query(models.Child).filter(
        models.Child.parent_id == parent_profile.id
    ).all()

    children_data = []
    for child in children:
        # Get active enrollment
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status.in_([
                models.EnrollmentStatus.ACTIVE,
                models.EnrollmentStatus.WAITLISTED,
                models.EnrollmentStatus.PENDING_REVIEW
            ])
        ).first()

        # Today's attendance
        today = date.today()
        attendance = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == child.id,
            models.AttendanceLog.date == today
        ).first()

        # Latest approved daily report
        latest_report = db.query(models.DailyReport).filter(
            models.DailyReport.child_id == child.id,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).order_by(models.DailyReport.date.desc()).first()

        child_info = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "age_months": validators.validate_age_months(child.date_of_birth),
            "enrollment": None,
            "attendance_today": None,
            "latest_report_date": None
        }

        if enrollment:
            child_info["enrollment"] = {
                "status": enrollment.status.value,
                "kindergarten_id": enrollment.kindergarten_id,
                "class_id": enrollment.class_id
            }

        if attendance:
            child_info["attendance_today"] = {
                "checked_in": attendance.check_in_at.strftime("%H:%M"),
                "checked_out": attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None
            }

        if latest_report:
            child_info["latest_report_date"] = latest_report.date

        children_data.append(child_info)

    return {
        "parent": {
            "name": f"{parent_profile.first_name} {parent_profile.last_name}",
            "phone": parent_profile.phone_number
        },
        "children": children_data,
        "total_children": len(children),
        "notifications": []  # Placeholder for notifications
    }
