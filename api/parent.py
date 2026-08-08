"""
Parent domain endpoints
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user
from i18n import gettext as _api
from admin_security import log_audit_event
from audit_actions import AuditAction


def _ulang(user) -> str:
    """Return the user's preferred UI language, defaulting to Arabic."""
    return getattr(user, "preferred_language", None) or "ar"


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Parent"])


@router.get("/parent/dashboard")
def get_parent_dashboard(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get comprehensive parent dashboard"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()

    if not parent_profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    # Get all children
    children = db.query(models.Child).filter(models.Child.parent_id == parent_profile.id).all()

    today = datetime.now(_JORDAN_TZ).date()
    child_ids = [c.id for c in children]

    # Batch-fetch enrollments, attendance, and latest reports — avoids 3N per-child queries
    enrollments_by_child: dict = {}
    attendance_by_child: dict = {}
    latest_report_by_child: dict = {}

    if child_ids:
        enrollments_by_child = {
            e.child_id: e
            for e in db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id.in_(child_ids),
                models.EnrollmentApplication.status.in_(
                    [
                        models.EnrollmentStatus.ACTIVE,
                        models.EnrollmentStatus.WAITLISTED,
                        models.EnrollmentStatus.PENDING_REVIEW,
                    ]
                ),
            )
            .all()
        }
        attendance_by_child = {
            a.child_id: a
            for a in db.query(models.AttendanceLog)
            .filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date == today,
            )
            .all()
        }
        from sqlalchemy import func as _func

        subq = (
            db.query(
                models.DailyReport.child_id,
                _func.max(models.DailyReport.date).label("max_date"),
            )
            .filter(
                models.DailyReport.child_id.in_(child_ids),
                models.DailyReport.status == models.DailyReportStatus.SENT_TO_PARENT,
            )
            .group_by(models.DailyReport.child_id)
            .subquery()
        )
        for r in (
            db.query(models.DailyReport)
            .join(
                subq,
                (models.DailyReport.child_id == subq.c.child_id) & (models.DailyReport.date == subq.c.max_date),
            )
            .all()
        ):
            latest_report_by_child[r.child_id] = r

    kgs_by_id = {}
    if child_ids:
        kg_ids = {e.kindergarten_id for e in enrollments_by_child.values() if e.kindergarten_id}
        if kg_ids:
            kgs_by_id = {
                kg.id: kg for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()
            }

    children_data = []
    for child in children:
        enrollment = enrollments_by_child.get(child.id)
        attendance = attendance_by_child.get(child.id)
        latest_report = latest_report_by_child.get(child.id)
        kg = kgs_by_id.get(enrollment.kindergarten_id) if enrollment else None

        child_info = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value
            if hasattr(child.gender, "value")
            else (str(child.gender) if child.gender else None),
            "kindergarten_name": (kg.name_ar or kg.name_en) if kg else None,
            "age_months": validators.validate_age_months(child.date_of_birth),
            "enrollment": None,
            "attendance_today": None,
            "latest_report_date": None,
        }

        if enrollment:
            child_info["enrollment"] = {
                "status": enrollment.status.value,
                "kindergarten_id": enrollment.kindergarten_id,
                "class_id": enrollment.class_id,
            }

        if attendance:
            child_info["attendance_today"] = {
                "checked_in": attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None,
                "checked_out": attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None,
            }

        if latest_report:
            child_info["latest_report_date"] = (
                latest_report.date.isoformat() if isinstance(latest_report.date, date) else latest_report.date
            )

        children_data.append(child_info)

    return {
        "parent": {
            "name": f"{parent_profile.first_name} {parent_profile.last_name}",
            "phone": parent_profile.phone_number,
        },
        "children": children_data,
        "total_children": len(children),
        "notifications": [],
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
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current parent's profile"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

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
        "home_district": profile.home_district,
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
        "notification_language": profile.notification_language,
    }


@router.get("/parent/children")
def get_parent_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current parent's children with their enrollments"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    children = (
        db.query(models.Child)
        .filter(
            models.Child.parent_id == profile.id,
            models.Child.deleted_at.is_(None),
        )
        .all()
    )

    child_ids = [c.id for c in children]

    # Batch-fetch all enrollments for all children at once
    all_enrollments: list = []
    kg_ids: set = set()
    if child_ids:
        all_enrollments = (
            db.query(models.EnrollmentApplication).filter(models.EnrollmentApplication.child_id.in_(child_ids)).all()
        )
        kg_ids = {e.kindergarten_id for e in all_enrollments if e.kindergarten_id}

    # Batch-fetch all kindergartens referenced by those enrollments
    kgs_by_id = {}
    if kg_ids:
        kgs_by_id = {kg.id: kg for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()}

    # Group enrollments by child_id
    from collections import defaultdict as _dd

    enrollments_by_child = _dd(list)
    for e in all_enrollments:
        enrollments_by_child[e.child_id].append(e)

    children_data = []
    for child in children:
        enrollment_list = []
        for e in enrollments_by_child[child.id]:
            kg = kgs_by_id.get(e.kindergarten_id)
            enrollment_list.append(
                {
                    "id": e.id,
                    "kindergarten_id": e.kindergarten_id,
                    "kindergarten_name": kg.name_ar if kg else None,
                    "status": e.status.value,
                    "status_ar": _ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
                }
            )

        children_data.append(
            {
                "id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "gender": child.gender.value if child.gender else None,
                "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
                "father_name": child.father_name,
                "mother_first_name": child.mother_first_name,
                "mother_last_name": child.mother_last_name,
                "profile_complete": child.profile_complete if hasattr(child, "profile_complete") else False,
                "enrollments": enrollment_list,
            }
        )

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
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    child_ids = [
        cid
        for (cid,) in db.query(models.Child.id)
        .filter(
            models.Child.parent_id == profile.id,
            models.Child.deleted_at.is_(None),
        )
        .all()
    ]

    if not child_ids:
        return {"total": 0, "enrollments": []}

    enrollments = (
        db.query(models.EnrollmentApplication).filter(models.EnrollmentApplication.child_id.in_(child_ids)).all()
    )

    children_by_id = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}
    kg_ids = {e.kindergarten_id for e in enrollments if e.kindergarten_id}
    kgs_by_id = (
        {kg.id: kg for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()}
        if kg_ids
        else {}
    )

    enrollment_data = []
    for e in enrollments:
        child = children_by_id.get(e.child_id)
        kg = kgs_by_id.get(e.kindergarten_id)
        enrollment_data.append(
            {
                "id": e.id,
                "child_id": e.child_id,
                "child_name": f"{child.first_name} {child.last_name}" if child else None,
                "kindergarten_id": e.kindergarten_id,
                "kindergarten_name": kg.name_ar if kg else None,
                "status": e.status.value,
                "status_ar": _ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
                "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )

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
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    child_ids = [cid for (cid,) in db.query(models.Child.id).filter(models.Child.parent_id == profile.id).all()]

    if child_id:
        if child_id not in child_ids:
            raise HTTPException(
                status_code=403, detail=_api("Not authorized to view this child's attendance", _ulang(current_user))
            )
        child_ids = [child_id]

    if not child_ids:
        return {"total": 0, "attendance": []}

    query = db.query(models.AttendanceLog).filter(models.AttendanceLog.child_id.in_(child_ids))

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
        query = query.filter(models.AttendanceLog.date >= datetime.now(_JORDAN_TZ).date() - timedelta(days=30))

    records = query.order_by(models.AttendanceLog.date.desc()).all()

    # Get child names
    children = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}

    attendance_data = []
    for a in records:
        child = children.get(a.child_id)
        attendance_data.append(
            {
                "id": a.id,
                "child_id": a.child_id,
                "child_name": f"{child.first_name} {child.last_name}" if child else None,
                "date": a.date.isoformat() if isinstance(a.date, date) else a.date,
                "status": a.status.value
                if hasattr(a, "status") and a.status
                else ("PRESENT" if a.check_in_at else "ABSENT"),
                "check_in_at": a.check_in_at.strftime("%H:%M") if a.check_in_at else None,
                "check_out_at": a.check_out_at.strftime("%H:%M") if a.check_out_at else None,
                "notes": a.notes if hasattr(a, "notes") else None,
            }
        )

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
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    children = db.query(models.Child).filter(models.Child.parent_id == profile.id).all()

    return {"children": [{"id": c.id, "name": f"{c.first_name} {c.last_name}"} for c in children]}


class ParentProfileSelfUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    second_name: Optional[str] = None
    last_name: Optional[str] = None
    first_name_en: Optional[str] = None
    last_name_en: Optional[str] = None
    phone_number: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    home_governorate: Optional[str] = None
    home_district: Optional[str] = None
    home_area: Optional[str] = None
    home_address_line: Optional[str] = None
    work_address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    relationship_to_child: Optional[str] = None
    correspondence_preference: Optional[bool] = None
    notification_language: Optional[str] = None
    language: Optional[str] = None  # updates user.preferred_language


@router.put("/parent/profile")
def update_parent_profile_self(
    data: ParentProfileSelfUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow authenticated parent to update their own profile and language preference."""
    from auth import jordan_phone_login_variants, normalize_jordan_phone

    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    text_fields = [
        "first_name",
        "second_name",
        "last_name",
        "first_name_en",
        "last_name_en",
        "nationality",
        "national_id",
        "passport_number",
        "home_governorate",
        "home_district",
        "home_area",
        "home_address_line",
        "work_address",
        "emergency_contact_name",
        "emergency_contact_relationship",
        "relationship_to_child",
    ]
    for field in text_fields:
        val = getattr(data, field)
        if val is not None:
            setattr(profile, field, val.strip() or None)

    if data.gender is not None:
        profile.gender = data.gender

    if data.correspondence_preference is not None:
        profile.correspondence_preference = data.correspondence_preference

    if data.phone_number is not None:
        raw_phone = data.phone_number.strip()
        if raw_phone:
            if not validators.validate_jordan_phone(raw_phone):
                raise HTTPException(
                    status_code=400,
                    detail=_api("Invalid Jordanian phone number", _ulang(current_user)),
                )
            duplicate_phone = (
                db.query(models.ParentProfile)
                .filter(
                    models.ParentProfile.phone_number.in_(jordan_phone_login_variants(raw_phone)),
                    models.ParentProfile.user_id != current_user.id,
                    models.ParentProfile.deleted_at.is_(None),
                )
                .first()
            )
            if duplicate_phone:
                raise HTTPException(
                    status_code=400,
                    detail=_api("Phone number already used", _ulang(current_user)),
                )
            profile.phone_number = normalize_jordan_phone(raw_phone)
        else:
            profile.phone_number = None

    if data.emergency_contact_phone is not None:
        raw_emergency_phone = data.emergency_contact_phone.strip()
        if raw_emergency_phone:
            if not validators.validate_jordan_phone(raw_emergency_phone):
                raise HTTPException(
                    status_code=400,
                    detail=_api("Invalid emergency contact phone number", _ulang(current_user)),
                )
            profile.emergency_contact_phone = normalize_jordan_phone(raw_emergency_phone)
        else:
            profile.emergency_contact_phone = None

    if data.notification_language is not None:
        if data.notification_language not in ("en", "ar"):
            raise HTTPException(status_code=400, detail=_api("Supported languages: ar, en", _ulang(current_user)))
        profile.notification_language = data.notification_language

    # Update user language preference
    if data.language is not None:
        if data.language not in ("en", "ar"):
            raise HTTPException(status_code=400, detail=_api("Supported languages: ar, en", _ulang(current_user)))
        current_user.preferred_language = data.language
        if data.notification_language is None:
            profile.notification_language = data.language

    children = db.query(models.Child).filter(models.Child.parent_id == profile.id).all()
    for child in children:
        validators.mark_profile_complete_if_ready(db, child.id)

    log_audit_event(
        db=db,
        action=getattr(AuditAction, "ACCOUNT_PROFILE_UPDATED", "ACCOUNT_PROFILE_UPDATED"),
        actor=current_user,
        target_type="ParentProfile",
        target_ids=profile.id,
        after_state={"user_id": current_user.id, "language": current_user.preferred_language},
    )

    db.commit()
    db.refresh(profile)

    lang = _ulang(current_user)
    return {"detail": _api("Saved successfully", lang)}


@router.get("/parent/daily-reports")
def get_parent_daily_reports(
    child_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get daily reports across all parent's children (status SENT_TO_PARENT only)."""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))

    profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=_api("Parent profile not found", _ulang(current_user)))

    child_ids = [
        cid
        for (cid,) in db.query(models.Child.id)
        .filter(
            models.Child.parent_id == profile.id,
            models.Child.deleted_at.is_(None),
        )
        .all()
    ]

    if child_id:
        if child_id not in child_ids:
            raise HTTPException(
                status_code=403, detail=_api("Not authorized to view this child's reports", _ulang(current_user))
            )
        child_ids = [child_id]

    if not child_ids:
        return {"total": 0, "reports": []}

    query = db.query(models.DailyReport).filter(
        models.DailyReport.child_id.in_(child_ids),
        models.DailyReport.status == models.DailyReportStatus.SENT_TO_PARENT,
    )

    try:
        if start_date:
            query = query.filter(models.DailyReport.date >= date.fromisoformat(start_date))
        if end_date:
            query = query.filter(models.DailyReport.date <= date.fromisoformat(end_date))
    except ValueError:
        logger.warning("INVALID_DATE_FILTER start_date=%r end_date=%r ignored", start_date, end_date)

    reports = query.order_by(models.DailyReport.date.desc(), models.DailyReport.id.desc()).all()
    children = {c.id: c for c in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()}

    report_list = []
    for r in reports:
        c = children.get(r.child_id)
        report_list.append(
            {
                "id": r.id,
                "child_id": r.child_id,
                "child_name": f"{c.first_name} {c.last_name}" if c else None,
                "date": r.date.isoformat() if isinstance(r.date, date) else r.date,
                "status": r.status.value,
                "arrival_time": r.arrival_time,
                "leave_time": r.leave_time,
                "activities": getattr(r, "activities", None),
                "notes": getattr(r, "notes", None),
                "mood": getattr(r, "mood", None),
            }
        )

    return {
        "total": len(report_list),
        "reports": report_list,
    }
