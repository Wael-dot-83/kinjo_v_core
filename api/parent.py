"""
Parent domain endpoints
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import validators
from admin_security import log_audit_event
from audit_actions import AuditAction
from auth import jordan_phone_login_variants, normalize_jordan_phone
from cache_service import cache_service
from config import settings
from database import get_db
from dependencies import ParentIdentity, get_current_parent
from i18n import gettext as _api
from rate_limiter import limiter

_JORDAN_TZ = timezone(timedelta(hours=3))


def _ulang(user) -> str:
    """Return the user's preferred UI language, defaulting to Arabic."""
    return getattr(user, "preferred_language", None) or "ar"


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Parent"])

_DASHBOARD_ENROLLMENT_STATUS_PRIORITY = {
    models.EnrollmentStatus.ACTIVE: 0,
    models.EnrollmentStatus.PENDING_REVIEW: 1,
    models.EnrollmentStatus.WAITLISTED: 2,
}


def _pick_primary_enrollment(enrollment_list: list) -> Optional[models.EnrollmentApplication]:
    if not enrollment_list:
        return None
    return sorted(
        enrollment_list,
        key=lambda e: (
            _DASHBOARD_ENROLLMENT_STATUS_PRIORITY.get(e.status, len(_DASHBOARD_ENROLLMENT_STATUS_PRIORITY)),
            -(e.id or 0),
        ),
    )[0]


_PARENT_DASHBOARD_CACHE_TTL = 60
_PARENT_ENGAGEMENT_CACHE_TTL = 300


def _parent_dashboard_cache_key(user_id: int) -> str:
    return f"parent:{user_id}:dashboard"


def _normalize_phone_or_raise(raw_phone: str, lang: str, error_message: str) -> str:
    if not validators.validate_jordan_phone(raw_phone):
        raise HTTPException(status_code=400, detail=_api(error_message, lang))
    return normalize_jordan_phone(raw_phone)


@router.get("/parent/dashboard")
def get_parent_dashboard(
    parent: ParentIdentity = Depends(get_current_parent), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get comprehensive parent dashboard"""
    current_user = parent.user
    parent_profile = parent.profile

    use_cache = not settings.TESTING
    cache_key = _parent_dashboard_cache_key(current_user.id)
    if use_cache:
        cached = cache_service.get(cache_key)
        if cached is not None:
            return cached

    # Get all children
    children = db.query(models.Child).filter(
        models.Child.parent_id == parent_profile.id,
        models.Child.deleted_at.is_(None),
    ).all()

    today = datetime.now(_JORDAN_TZ).date()
    child_ids = [c.id for c in children]

    # Batch-fetch enrollments, attendance, and latest reports — avoids 3N per-child queries
    enrollments_by_child: dict = {}
    attendance_by_child: dict = {}
    latest_report_by_child: dict = {}

    if child_ids:
        enrollments_by_child = defaultdict(list)
        for e in db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id.in_(child_ids),
            models.EnrollmentApplication.status.in_(
                [
                    models.EnrollmentStatus.ACTIVE,
                    models.EnrollmentStatus.WAITLISTED,
                    models.EnrollmentStatus.PENDING_REVIEW,
                ]
            ),
        ).all():
            enrollments_by_child[e.child_id].append(e)
        attendance_by_child = {
            a.child_id: a
            for a in db.query(models.AttendanceLog)
            .filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date == today,
            )
            .all()
        }

        subq = (
            db.query(
                models.DailyReport.child_id,
                func.max(models.DailyReport.date).label("max_date"),
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
        kg_ids = {
            e.kindergarten_id
            for enrollment_list in enrollments_by_child.values()
            for e in enrollment_list
            if e.kindergarten_id
        }
        if kg_ids:
            kgs_by_id = {
                kg.id: kg for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()
            }

    children_data = []
    for child in children:
        enrollment_list = enrollments_by_child.get(child.id, [])
        primary_enrollment = _pick_primary_enrollment(enrollment_list)
        attendance = attendance_by_child.get(child.id)
        latest_report = latest_report_by_child.get(child.id)
        kg = kgs_by_id.get(primary_enrollment.kindergarten_id) if primary_enrollment else None

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
            "enrollments": [
                {
                    "id": e.id,
                    "status": e.status.value,
                    "status_ar": _ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
                    "kindergarten_id": e.kindergarten_id,
                    "kindergarten_name": (kgs_by_id[e.kindergarten_id].name_ar or kgs_by_id[e.kindergarten_id].name_en)
                    if e.kindergarten_id in kgs_by_id
                    else None,
                    "class_id": e.class_id,
                }
                for e in enrollment_list
            ],
            "attendance_today": None,
            "latest_report_date": None,
        }

        if primary_enrollment:
            child_info["enrollment"] = {
                "status": primary_enrollment.status.value,
                "kindergarten_id": primary_enrollment.kindergarten_id,
                "class_id": primary_enrollment.class_id,
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

    payload = {
        "parent": {
            "name": f"{parent_profile.first_name} {parent_profile.last_name}",
            "phone": parent_profile.phone_number,
        },
        "children": children_data,
        "total_children": len(children),
        "notifications": [],
    }
    if use_cache:
        cache_service.set(cache_key, payload, ttl_seconds=_PARENT_DASHBOARD_CACHE_TTL)
    return payload


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
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get current parent's profile"""
    current_user = parent.user
    profile = parent.profile

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
        "parent_type": profile.parent_type,
        "profile_complete": profile.profile_complete,
        "profile_completed_at": profile.profile_completed_at.isoformat() if profile.profile_completed_at else None,
        "correspondence_preference": profile.correspondence_preference,
        "notification_language": profile.notification_language,
    }


@router.get("/parent/children")
def get_parent_children(
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get current parent's children with their enrollments"""
    profile = parent.profile

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
    enrollments_by_child = defaultdict(list)
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
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get all enrollment applications for current parent's children"""
    profile = parent.profile

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

    enrollments_query = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id.in_(child_ids)
    )
    total = enrollments_query.count()

    if page is not None:
        enrollments_query = enrollments_query.order_by(models.EnrollmentApplication.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)

    enrollments = enrollments_query.all()

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

    response = {
        "total": total,
        "enrollments": enrollment_data,
    }
    if page is not None:
        response["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    return response


@router.get("/parent/attendance")
def get_parent_attendance(
    child_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get attendance history for parent's children"""
    current_user = parent.user
    profile = parent.profile

    child_ids = [
        cid for (cid,) in db.query(models.Child.id).filter(
            models.Child.parent_id == profile.id, models.Child.deleted_at.is_(None)
        ).all()
    ]

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

    query = query.order_by(models.AttendanceLog.date.desc())

    total = None
    if page is not None:
        total = query.count()
        query = query.order_by(models.AttendanceLog.id.desc()).offset((page - 1) * page_size).limit(page_size)

    records = query.all()

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

    response = {
        "total": total if total is not None else len(attendance_data),
        "attendance": attendance_data,
    }
    if page is not None:
        response["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    return response


@router.get("/parent/children-list")
def get_parent_children_simple(
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Simple children list for filter dropdowns"""
    profile = parent.profile

    children = db.query(models.Child).filter(
        models.Child.parent_id == profile.id, models.Child.deleted_at.is_(None)
    ).all()

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
    parent_type: Optional[str] = None
    correspondence_preference: Optional[bool] = None
    notification_language: Optional[str] = None
    language: Optional[str] = None  # updates user.preferred_language


@router.put("/parent/profile")
@limiter.limit(settings.RATE_LIMIT_PARENT_WRITE)
def update_parent_profile_self(
    request: Request,
    data: ParentProfileSelfUpdateRequest,
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Allow authenticated parent to update their own profile and language preference."""
    current_user = parent.user
    profile = parent.profile
    lang = _ulang(current_user)

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
        "parent_type",
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
            normalized_phone = _normalize_phone_or_raise(raw_phone, lang, "Invalid Jordanian phone number")
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
                    detail=_api("Phone number already used", lang),
                )
            profile.phone_number = normalized_phone
        else:
            profile.phone_number = None

    if data.emergency_contact_phone is not None:
        raw_emergency_phone = data.emergency_contact_phone.strip()
        if raw_emergency_phone:
            profile.emergency_contact_phone = _normalize_phone_or_raise(
                raw_emergency_phone, lang, "Invalid emergency contact phone number"
            )
        else:
            profile.emergency_contact_phone = None

    if data.notification_language is not None:
        if data.notification_language not in ("en", "ar"):
            raise HTTPException(status_code=400, detail=_api("Supported languages: ar, en", lang))
        profile.notification_language = data.notification_language

    # Update user language preference
    if data.language is not None:
        if data.language not in ("en", "ar"):
            raise HTTPException(status_code=400, detail=_api("Supported languages: ar, en", lang))
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
    cache_service.delete(_parent_dashboard_cache_key(current_user.id))

    return {"detail": _api("Saved successfully", lang)}


@router.get("/parent/daily-reports")
def get_parent_daily_reports(
    child_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    parent: ParentIdentity = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get daily reports across all parent's children (status SENT_TO_PARENT only)."""
    current_user = parent.user
    profile = parent.profile

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

    query = query.order_by(models.DailyReport.date.desc(), models.DailyReport.id.desc())

    total = None
    if page is not None:
        total = query.count()
        query = query.offset((page - 1) * page_size).limit(page_size)

    reports = query.all()
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
                "health_notes": getattr(r, "health_notes", None),
                "breakfast": getattr(r, "breakfast", None),
                "snack": getattr(r, "snack", None),
                "milk": getattr(r, "milk", None),
                "lunch": getattr(r, "lunch", None),
                "nap_start": getattr(r, "nap_start", None),
                "nap_end": getattr(r, "nap_end", None),
                "nap_duration_minutes": getattr(r, "nap_duration_minutes", None),
            }
        )

    response = {
        "total": total if total is not None else len(report_list),
        "reports": report_list,
    }
    if page is not None:
        response["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    return response
