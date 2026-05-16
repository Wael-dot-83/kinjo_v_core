"""
Parent domain endpoints
"""
import logging

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

logger = logging.getLogger(__name__)
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

        # Latest approved or sent-to-parent daily report
        latest_report = db.query(models.DailyReport).filter(
            models.DailyReport.child_id == child.id,
            models.DailyReport.status.in_([
                models.DailyReportStatus.APPROVED,
                models.DailyReportStatus.SENT_TO_PARENT,
            ])
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
                "checked_in": attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None,
                "checked_out": attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None
            }

        if latest_report:
            child_info["latest_report_date"] = latest_report.date.isoformat() if isinstance(latest_report.date, date) else latest_report.date

        children_data.append(child_info)

    return {
        "parent": {
            "name": f"{parent_profile.first_name} {parent_profile.last_name}",
            "phone": parent_profile.phone_number
        },
        "children": children_data,
        "total_children": len(children),
        "notifications": []
    }


# --- Arabic status mapping ---
_ENROLLMENT_STATUS_AR = {
    "DRAFT": "مسودة",
    "SUBMITTED": "مقدّم",
    "PENDING_REVIEW": "قيد المراجعة",
    "ACCEPTED": "مقبول",
    "REJECTED": "مرفوض",
    "WITHDRAWN": "منسحب",
    "WAITLISTED": "قائمة الانتظار",
    "ACTIVE": "نشط",
}


@router.get("/parent/profile")
def get_parent_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current parent's profile"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    return {
        "id": profile.id,
        "user_id": current_user.id,
        "first_name": profile.first_name,
        "second_name": profile.second_name,
        "last_name": profile.last_name,
        "first_name_en": profile.first_name_en,
        "last_name_en": profile.last_name_en,
        "phone_number": profile.phone_number,
        "email": current_user.email,
        "username": current_user.username,
        "gender": profile.gender.value if profile.gender else None,
        "nationality": profile.nationality,
        "national_id": profile.national_id,
        "passport_number": profile.passport_number,
        "home_governorate": profile.home_governorate,
        "home_city": profile.home_city,
        "home_area": profile.home_area,
        "home_address_line": profile.home_address_line,
        "work_address": profile.work_address,
        "emergency_contact_name": profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "emergency_contact_relationship": profile.emergency_contact_relationship,
        "relationship_to_child": profile.relationship_to_child,
        "profile_complete": profile.profile_complete,
        "profile_completed_at": profile.profile_completed_at.isoformat() if profile.profile_completed_at else None,
        "correspondence_preference": profile.correspondence_preference,
    }


@router.get("/parent/children")
def get_parent_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current parent's children with their enrollments"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    children = db.query(models.Child).filter(
        models.Child.parent_id == profile.id
    ).all()

    children_data = []
    for child in children:
        enrollments = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id
        ).all()

        enrollment_list = []
        for e in enrollments:
            kg = db.query(models.Kindergarten).filter(
                models.Kindergarten.id == e.kindergarten_id
            ).first()
            enrollment_list.append({
                "id": e.id,
                "kindergarten_id": e.kindergarten_id,
                "kindergarten_name": kg.name_ar if kg else None,
                "status": e.status.value,
                "status_ar": _ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
            })

        children_data.append({
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value if child.gender else None,
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "father_name": child.father_name,
            "mother_first_name": child.mother_first_name,
            "mother_last_name": child.mother_last_name,
            "profile_complete": child.profile_complete if hasattr(child, 'profile_complete') else False,
            "enrollments": enrollment_list,
        })

    return {
        "total": len(children_data),
        "children": children_data,
    }


@router.get("/parent/enrollments")
def get_parent_enrollments(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all enrollment applications for current parent's children"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    child_ids = [
        cid for (cid,) in db.query(models.Child.id).filter(
            models.Child.parent_id == profile.id
        ).all()
    ]

    if not child_ids:
        return {"total": 0, "enrollments": []}

    enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id.in_(child_ids)
    ).all()

    enrollment_data = []
    for e in enrollments:
        child = db.query(models.Child).filter(models.Child.id == e.child_id).first()
        kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == e.kindergarten_id).first()
        enrollment_data.append({
            "id": e.id,
            "child_id": e.child_id,
            "child_name": f"{child.first_name} {child.last_name}" if child else None,
            "kindergarten_id": e.kindergarten_id,
            "kindergarten_name": kg.name_ar if kg else None,
            "status": e.status.value,
            "status_ar": _ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
            "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return {
        "total": len(enrollment_data),
        "enrollments": enrollment_data,
    }


@router.get("/parent/attendance")
def get_parent_attendance(
    child_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get attendance history for parent's children"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    child_ids = [
        cid for (cid,) in db.query(models.Child.id).filter(
            models.Child.parent_id == profile.id
        ).all()
    ]

    if child_id:
        if child_id not in child_ids:
            raise HTTPException(status_code=403, detail="Not authorized to view this child's attendance")
        child_ids = [child_id]

    if not child_ids:
        return {"total": 0, "attendance": []}

    query = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id.in_(child_ids)
    )

    # Date filters
    try:
        if start_date:
            query = query.filter(models.AttendanceLog.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(models.AttendanceLog.date <= date.fromisoformat(end_date))
    except ValueError:
        logger.warning("INVALID_DATE_FILTER start_date=%r end_date=%r ignored — not ISO format", start_date, end_date)

    # Default: last 30 days
    if not start_date and not end_date:
        query = query.filter(models.AttendanceLog.date >= date.today() - timedelta(days=30))

    records = query.order_by(models.AttendanceLog.date.desc()).all()

    # Get child names
    children = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}

    attendance_data = []
    for a in records:
        child = children.get(a.child_id)
        attendance_data.append({
            "id": a.id,
            "child_id": a.child_id,
            "child_name": f"{child.first_name} {child.last_name}" if child else None,
            "date": a.date.isoformat() if isinstance(a.date, date) else a.date,
            "status": a.status.value if hasattr(a, 'status') and a.status else ("PRESENT" if a.check_in_at else "ABSENT"),
            "check_in_at": a.check_in_at.strftime("%H:%M") if a.check_in_at else None,
            "check_out_at": a.check_out_at.strftime("%H:%M") if a.check_out_at else None,
            "notes": a.notes if hasattr(a, 'notes') else None,
        })

    return {
        "total": len(attendance_data),
        "attendance": attendance_data,
    }


@router.get("/parent/children-list")
def get_parent_children_simple(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Simple children list for filter dropdowns"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    children = db.query(models.Child).filter(
        models.Child.parent_id == profile.id
    ).all()

    return {
        "children": [
            {"id": c.id, "name": f"{c.first_name} {c.last_name}"}
            for c in children
        ]
    }
