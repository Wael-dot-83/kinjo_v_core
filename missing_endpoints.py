"""
Missing Critical Endpoints - Implementation
Adds CRUD operations and complete workflows

P3-A AUDIT RESULT (2026-06-14):
  26 routes audited. None conflict with admin_endpoints.py (all are in user-facing
  namespaces: /users/me, /notifications, /search, /communication, /kindergartens,
  /classes, /safety, /reports, /parent-profiles, /children, /manager, /enrollments,
  /attendance, /daily-reports, /curriculum).

  This module is mounted at /api in main.py (after admin_router), so there is no
  overlap with /api/admin/* routes. Safe to keep as-is. Future work: migrate each
  domain into its own router file (e.g., api/attendance.py, api/curriculum.py).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator, model_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

import models
import validators
import kpi_service as _kpi_svc
from config import settings
from database import get_db, engine as _db_engine
from dependencies import get_current_user
from auth import get_password_hash, normalize_email, normalize_jordan_phone, jordan_phone_login_variants, PasswordValidator


router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
if settings.TESTING:
    limiter.enabled = False


def _log_access_denied(
    db: Session,
    user: models.User,
    action: str,
    details: Optional[str],
    request: Request,
    entity_type: str = "User"
) -> None:
    ip_address = request.client.host if request.client else None
    try:
        validators.log_audit_action(
            db=db,
            user_id=user.id,
            action="ACCESS_DENIED",
            entity_type=entity_type,
            entity_id=None,
            details=f"{action}: {details}" if details else action,
            ip_address=ip_address,
            sensitivity_level=2
        )
    except Exception:
        pass

DUPLICATE_ERROR_MAP = {
    "name_ar": {"code": "error_duplicate_name_ar", "message": "This Arabic name is already registered."},
    "name_en": {"code": "error_duplicate_name_en", "message": "This English name is already registered."},
    "contact_phone": {"code": "error_duplicate_phone", "message": "This phone number is already registered."},
    "contact_email": {"code": "error_duplicate_email", "message": "This email is already registered."},
    "license_number": {"code": "error_duplicate_license", "message": "This license number is already registered."},
}


def _active_manager_for_kindergarten(
    db: Session,
    kindergarten_id: Optional[int],
    exclude_user_id: Optional[int] = None,
) -> Optional[models.User]:
    if not kindergarten_id:
        return None
    query = db.query(models.User).filter(
        models.User.role == models.UserRole.MANAGER,
        models.User.kindergarten_id == kindergarten_id,
        models.User.deleted_at.is_(None),
    )
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)
    return query.first()


def _validate_single_manager_assignment(
    db: Session,
    role: models.UserRole,
    kindergarten_id: Optional[int],
    exclude_user_id: Optional[int] = None,
) -> None:
    if role != models.UserRole.MANAGER:
        return
    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Manager accounts must be assigned to a kindergarten")
    if _active_manager_for_kindergarten(db, kindergarten_id, exclude_user_id=exclude_user_id):
        raise HTTPException(status_code=400, detail="This kindergarten already has a manager")


# ============================================================================
# User Profile Endpoints
# ============================================================================

class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    login_identifier_type: str = "email"
    role: str
    status: str
    kindergarten_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    parent_type: Optional[str] = None
    national_id: Optional[str] = None
    nationality: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CurrentUserUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    parent_type: Optional[str] = Field(default=None, pattern="^(FATHER|MOTHER|OTHER)$")
    national_id: Optional[str] = Field(default=None, max_length=50)
    nationality: Optional[str] = Field(default=None, max_length=100)

    @field_validator("email", mode="before")
    @classmethod
    def blank_email_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone")
    @classmethod
    def normalize_profile_phone(cls, value):
        if value is None:
            return None
        if not value.strip():
            return None  # treat blank as "no change" — mirrors blank_email_to_none
        return normalize_jordan_phone(value)


class CurrentPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.put("/users/me/password")
def change_current_user_password(
    password_data: CurrentPasswordChange,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change the current user's password after verifying the old password."""
    from auth import get_password_hash, verify_password

    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    is_valid_password, password_error = PasswordValidator.validate(password_data.new_password)
    if not is_valid_password:
        raise HTTPException(status_code=400, detail=password_error)
    if PasswordValidator.check_breached(password_data.new_password):
        raise HTTPException(status_code=400, detail="This password has appeared in a data breach. Please choose a different password.")

    try:
        current_user.hashed_password = get_password_hash(password_data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="PASSWORD_CHANGED",
        entity_type="User",
        entity_id=current_user.id,
        sensitivity_level=3
    )
    return {"message": "Password updated successfully"}


@router.get("/users/me/parent-info")
def get_parent_info(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return parent type, full name, national ID and nationality for JS wizard logic."""
    profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not profile:
        return {"parent_type": None, "full_name": None, "profile_complete": False}

    full_name_parts = [profile.first_name, profile.second_name, profile.last_name]
    full_name = " ".join(p for p in full_name_parts if p)
    profile_complete = bool(profile.parent_type and profile.national_id)

    return {
        "parent_type":      profile.parent_type,
        "full_name":        full_name,
        "national_id":      profile.national_id,
        "nationality":      profile.nationality,
        "profile_complete": profile_complete,
    }


@router.get("/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return paginated notification list for the current user."""
    rows = db.execute(
        text(
            "SELECT id, notification_type, status, payload, created_at "
            "FROM notifications "
            "WHERE user_id = :user_id "
            "ORDER BY created_at DESC "
            "LIMIT :limit"
        ),
        {"user_id": current_user.id, "limit": limit}
    ).fetchall()

    import json as _json

    items = []
    for row in rows:
        payload = {}
        if row.payload:
            try:
                payload = _json.loads(row.payload) if isinstance(row.payload, str) else row.payload
            except Exception:
                pass
        title = (
            payload.get("title")
            or payload.get("subject")
            or row.notification_type.replace("_", " ").title()
            if row.notification_type else "إشعار"
        )
        message = payload.get("message") or payload.get("body") or ""
        is_read = (row.status or "SENT") == "READ"
        created_display = ""
        if row.created_at:
            try:
                from datetime import timezone as _tz
                dt = row.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                created_display = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                created_display = str(row.created_at)[:16]
        items.append({
            "id": row.id,
            "title": title,
            "message": message,
            "is_read": is_read,
            "notification_type": row.notification_type,
            "created_at_display": created_display,
        })

    return {"items": items, "total": len(items)}


@router.get("/notifications/unread-count")
def get_unread_notification_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return unread notification count for the navbar badge."""
    count = db.execute(
        text(
            "SELECT COUNT(*) FROM notifications "
            "WHERE user_id = :user_id AND COALESCE(status, 'SENT') != 'READ'"
        ),
        {"user_id": current_user.id}
    ).scalar() or 0
    return {"count": int(count)}


@router.post("/notifications/read-all")
def mark_notifications_read(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all current-user notifications as read."""
    result = db.execute(
        text("UPDATE notifications SET status = 'READ' WHERE user_id = :user_id"),
        {"user_id": current_user.id}
    )
    db.commit()
    return {"updated": result.rowcount or 0}


@router.get("/search")
def global_search(
    q: str = Query(..., min_length=2, max_length=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Global navigation search across scoped children, parents, and kindergartens."""
    term = f"%{q.strip()}%"
    results = []

    kg_query = db.query(models.Kindergarten)
    if current_user.role != models.UserRole.ADMIN:
        kg_query = kg_query.filter(models.Kindergarten.id == current_user.kindergarten_id)
    for kg in kg_query.filter(or_(
        models.Kindergarten.name_ar.ilike(term),
        models.Kindergarten.name_en.ilike(term),
        models.Kindergarten.contact_phone.ilike(term)
    )).limit(5):
        results.append({
            "type": "kindergarten",
            "title": kg.name_ar or kg.name_en,
            "subtitle": kg.city or kg.governorate,
            "url": f"/kindergartens/{kg.id}",
        })

    children_query = db.query(models.Child, models.EnrollmentApplication).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.Child.id
    )
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        children_query = children_query.filter(models.Child.parent_id == (parent_profile.id if parent_profile else -1))
    elif current_user.role != models.UserRole.ADMIN:
        children_query = children_query.filter(
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id
        )
    for child, enrollment in children_query.filter(or_(
        models.Child.first_name.ilike(term),
        models.Child.last_name.ilike(term),
        (models.Child.first_name + " " + models.Child.last_name).ilike(term)
    )).limit(5):
        results.append({
            "type": "child",
            "title": f"{child.first_name} {child.last_name}",
            "subtitle": f"KG #{enrollment.kindergarten_id}",
            "url": f"/children/{child.id}",
        })

    if current_user.role in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        users_query = db.query(models.User)
        if current_user.role == models.UserRole.MANAGER:
            users_query = users_query.filter(models.User.kindergarten_id == current_user.kindergarten_id)
        for user in users_query.filter(or_(
            models.User.username.ilike(term),
            models.User.email.ilike(term)
        )).limit(5):
            results.append({
                "type": "parent" if user.role == models.UserRole.PARENT else "user",
                "title": user.username,
                "subtitle": user.email,
                "url": f"/admin/users/{user.id}/edit" if current_user.role == models.UserRole.ADMIN else "#",
            })

    return {"results": results[:10]}


@router.get("/communication/stats")
def get_communication_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggregate communication dashboard counts and recent activity."""
    message_query = db.query(models.Message)
    event_query = db.query(models.Event)
    survey_query = db.query(models.Survey)

    if current_user.role != models.UserRole.ADMIN:
        message_query = message_query.filter(models.Message.kindergarten_id == current_user.kindergarten_id)
        event_query = event_query.filter(models.Event.kindergarten_id == current_user.kindergarten_id)
        survey_query = survey_query.filter(models.Survey.kindergarten_id == current_user.kindergarten_id)

    _unread_msg_ids = (
        db.query(models.MessageRecipient.message_id)
        .filter(
            models.MessageRecipient.recipient_user_id == current_user.id,
            models.MessageRecipient.read_at.is_(None),
        )
        .scalar_subquery()
    )
    unread_messages = message_query.filter(
        models.Message.id.in_(_unread_msg_ids),
    ).count()

    now = datetime.now()
    upcoming_events = event_query.filter(models.Event.start_at >= now, models.Event.deleted_at.is_(None)).count()
    active_surveys = survey_query.filter(
        models.Survey.start_date <= date.today(),
        models.Survey.end_date >= date.today(),
        models.Survey.deleted_at.is_(None)
    ).count()

    activities = []
    for message in message_query.order_by(models.Message.created_at.desc()).limit(5):
        activities.append({
            "type": "message",
            "title": message.subject or message.message_body[:60],
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "status": "sent",
        })
    for event in event_query.filter(models.Event.deleted_at.is_(None)).order_by(models.Event.created_at.desc()).limit(5):
        activities.append({
            "type": "event",
            "title": event.title,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "status": "published",
        })
    for survey in survey_query.filter(models.Survey.deleted_at.is_(None)).order_by(models.Survey.created_at.desc()).limit(5):
        activities.append({
            "type": "survey",
            "title": survey.title,
            "created_at": survey.created_at.isoformat() if survey.created_at else None,
            "status": "published",
        })

    activities.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {
        "unread_messages": unread_messages,
        "upcoming_events": upcoming_events,
        "active_surveys": active_surveys,
        "recent_activity": activities[:10],
    }


# ============================================================================
# Admin User Management Endpoints
# ============================================================================

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: models.UserRole
    kindergarten_id: Optional[int] = None

class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[models.UserRole] = None
    status: Optional[models.UserStatus] = None
    kindergarten_id: Optional[int] = None


# Password Reset Endpoints
class PasswordResetRequest(BaseModel):
    identifier: str  # email or phone number

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
    confirm_password: str

class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
    admin_password: str = Field(..., min_length=8)


# Bulk Operations Endpoints
class BulkStatusUpdate(BaseModel):
    user_ids: List[int]
    new_status: models.UserStatus

class BulkDeleteRequest(BaseModel):
    user_ids: List[int]

class BulkCreateRequest(BaseModel):
    users: List[UserCreate]


class KindergartenCreate(BaseModel):
    name_ar: str
    name_en: Optional[str] = None
    governorate: str
    city: str
    area: str
    address_line: str
    contact_phone: str
    contact_email: Optional[EmailStr] = None
    operating_hours_start: Optional[str] = None
    operating_hours_end: Optional[str] = None
    license_number: Optional[str] = None
    license_valid_until: Optional[date] = None

    @field_validator("contact_email", mode="before")
    def normalize_email(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
            value = value.lower()
        return value

    @field_validator("license_number", "license_valid_until", mode="before")
    def blank_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("contact_phone")
    def strip_phone(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("governorate")
    def validate_governorate(cls, value):
        if not validators.validate_jordan_governorate(value):
            raise ValueError(f"Invalid governorate: {value}. Must be one of: {', '.join(settings.JORDAN_GOVERNORATES)}")
        return value


def detect_kindergarten_duplicate(db: Session, data: KindergartenCreate, exclude_id: Optional[int] = None) -> Optional[str]:
    filters = [
        models.Kindergarten.name_ar == data.name_ar,
        models.Kindergarten.contact_phone == data.contact_phone,
    ]
    if data.name_en:
        filters.append(models.Kindergarten.name_en == data.name_en)
    if data.contact_email:
        filters.append(models.Kindergarten.contact_email == data.contact_email)
    if data.license_number:
        filters.append(models.Kindergarten.license_number == data.license_number)

    if not filters:
        return None

    query = db.query(models.Kindergarten).filter(or_(*filters))
    if exclude_id:
        query = query.filter(models.Kindergarten.id != exclude_id)

    duplicate = query.first()
    if not duplicate:
        return None

    # Return the most relevant conflicting field for a clearer message
    if duplicate.contact_phone == data.contact_phone:
        return "contact_phone"
    if data.contact_email and duplicate.contact_email == data.contact_email:
        return "contact_email"
    if data.license_number and duplicate.license_number == data.license_number:
        return "license_number"
    if duplicate.name_ar == data.name_ar:
        return "name_ar"
    if data.name_en and duplicate.name_en == data.name_en:
        return "name_en"
    return "name_ar"

class KindergartenResponse(KindergartenCreate):
    id: int
    status: models.KindergartenStatus

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Class CRUD Endpoints
# ============================================================================

# ============================================================================
# Kindergarten Services/Facilities CRUD Endpoints
# ============================================================================

class KindergartenServiceCreate(BaseModel):
    kindergarten_id: int
    service_name: str
    description: str
    enabled_flag: Optional[bool] = True

class KindergartenServiceResponse(KindergartenServiceCreate):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class KindergartenServiceUpdate(BaseModel):
    service_name: Optional[str] = None
    description: Optional[str] = None
    enabled_flag: Optional[bool] = None


@router.get("/kindergartens/{kindergarten_id}/kpi-snapshot")
def get_kindergarten_kpi_snapshot(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return KPI snapshot (occupancy, governance, parent satisfaction) for the KPI sidebar."""
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == models.UserRole.MANAGER:
        validators.validate_kindergarten_scope(current_user, kindergarten_id)

    # Occupancy: active enrollments / total class capacity
    total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active.is_(True)
    ).scalar() or 0
    active_enrolled = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0
    occupancy_pct = round((active_enrolled / total_capacity) * 100, 1) if total_capacity > 0 else 0.0

    # Governance and parent satisfaction via KPIService
    today = date.today()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        period_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    governance_score = _kpi_svc.KPIService.compute_governance_quality_index(
        db, kindergarten_id, period_start, period_end
    )
    satisfaction_score = _kpi_svc.KPIService.compute_parent_satisfaction_score(
        db, kindergarten_id, period_start, period_end
    )

    return {
        "occupancy_pct": occupancy_pct,
        "occupancy_enrolled": active_enrolled,
        "occupancy_capacity": total_capacity,
        "governance_score": governance_score,
        "satisfaction_score": satisfaction_score,
    }


class ClassCreate(BaseModel):
    kindergarten_id: int
    name_ar: str
    name_en: Optional[str] = None
    capacity_total: int
    min_age_months: int
    max_age_months: int

class ClassResponse(ClassCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class ClassUpdate(BaseModel):
    name_ar: Optional[str] = None
    name_en: Optional[str] = None
    capacity_total: Optional[int] = None
    min_age_months: Optional[int] = None
    max_age_months: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/classes/{class_id}/children")
def get_children_in_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return children actively enrolled in the given class — used for incident form dropdowns."""
    cls = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if current_user.role != models.UserRole.ADMIN:
        if cls.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")

    enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
    ).all()

    children = []
    for e in enrollments:
        if e.child and not e.child.deleted_at:
            c = e.child
            children.append({
                "id": c.id,
                "name": f"{c.first_name} {c.last_name}".strip(),
                "first_name": c.first_name,
                "last_name": c.last_name,
            })
    return {"children": children}


@router.get("/classes/{class_id}/supervisors")
def get_supervisors_in_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return supervisors assigned to the given class — used for incident form dropdowns."""
    cls = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if current_user.role != models.UserRole.ADMIN:
        if cls.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")

    from datetime import date as _date
    today = _date.today()
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.class_id == class_id,
        models.SupervisorAssignment.start_date <= today,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= today,
        ),
        models.SupervisorAssignment.deleted_at.is_(None),
    ).all()

    supervisors = []
    seen = set()
    for a in assignments:
        if a.supervisor and a.supervisor_id not in seen:
            seen.add(a.supervisor_id)
            s = a.supervisor
            supervisors.append({
                "id": s.id,
                "name": s.username,
                "is_primary": a.is_primary,
            })
    return {"supervisors": supervisors}


@router.get("/safety/analytics")
def get_safety_analytics(
    kindergarten_id: Optional[int] = None,
    governorate: Optional[str] = None,
    incident_type: Optional[str] = None,
    classification: Optional[str] = None,
    severity: Optional[str] = None,
    parent_informed: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin-only safety analytics endpoint — aggregate incident statistics."""
    validators.validate_admin_role(current_user)

    # Base query — always exclude soft-deleted incidents
    query = db.query(models.Incident).filter(models.Incident.deleted_at.is_(None))

    if kindergarten_id:
        query = query.filter(models.Incident.kindergarten_id == kindergarten_id)

    if incident_type:
        try:
            query = query.filter(models.Incident.type == models.IncidentType(incident_type.upper()))
        except ValueError:
            pass

    if classification:
        query = query.filter(
            func.upper(models.Incident.classification) == classification.upper()
        )

    if severity:
        try:
            query = query.filter(models.Incident.severity_level == models.SeverityLevel(severity.upper()))
        except ValueError:
            pass

    if parent_informed is not None and parent_informed != "":
        pi_bool = parent_informed.lower() in ("true", "1", "yes")
        query = query.filter(models.Incident.parent_informed == pi_bool)

    if date_from:
        try:
            df = datetime.fromisoformat(date_from)
            query = query.filter(models.Incident.occurred_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            # inclusive end-of-day
            if "T" not in date_to:
                dt = dt.replace(hour=23, minute=59, second=59)
            query = query.filter(models.Incident.occurred_at <= dt)
        except ValueError:
            pass

    if governorate:
        query = query.join(
            models.Kindergarten,
            models.Incident.kindergarten_id == models.Kindergarten.id,
            isouter=False,
        )
        query = query.filter(models.Kindergarten.governorate == governorate)

    incidents = query.all()

    total = len(incidents)
    open_count = sum(1 for i in incidents if not i.closed_at)
    closed_count = total - open_count
    informed_count = sum(1 for i in incidents if i.parent_informed)
    not_informed_count = total - informed_count

    # Aggregation buckets
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    by_kg_id: dict[int, int] = {}
    by_child_id: dict[int, int] = {}
    by_month: dict[str, int] = {}

    for inc in incidents:
        sev_key = inc.severity_level.value if inc.severity_level else "UNKNOWN"
        by_severity[sev_key] = by_severity.get(sev_key, 0) + 1

        type_key = inc.type.value if inc.type else "UNKNOWN"
        by_type[type_key] = by_type.get(type_key, 0) + 1

        cls_key = (inc.classification or "OTHER").upper()
        by_classification[cls_key] = by_classification.get(cls_key, 0) + 1

        if inc.kindergarten_id:
            by_kg_id[inc.kindergarten_id] = by_kg_id.get(inc.kindergarten_id, 0) + 1

        if inc.child_id:
            by_child_id[inc.child_id] = by_child_id.get(inc.child_id, 0) + 1

        if inc.occurred_at:
            month_key = inc.occurred_at.strftime("%Y-%m")
            by_month[month_key] = by_month.get(month_key, 0) + 1

    # Build by_kindergarten list with names
    kg_ids = list(by_kg_id.keys())
    kg_map: dict[int, models.Kindergarten] = {}
    if kg_ids:
        for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all():
            kg_map[kg.id] = kg

    HIGH_RISK_THRESHOLD = 5
    by_kindergarten = sorted(
        [
            {
                "id": kg_id,
                "name_ar": kg_map[kg_id].name_ar if kg_id in kg_map else f"روضة #{kg_id}",
                "name_en": kg_map[kg_id].name_en if kg_id in kg_map else f"Kindergarten #{kg_id}",
                "count": count,
                "is_high_risk": count >= HIGH_RISK_THRESHOLD,
            }
            for kg_id, count in by_kg_id.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )
    high_risk_count = sum(1 for x in by_kindergarten if x["is_high_risk"])

    # Build repeated_children list with names
    child_ids = [cid for cid, cnt in by_child_id.items() if cnt > 1]
    child_map: dict[int, models.Child] = {}
    if child_ids:
        for child in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all():
            child_map[child.id] = child

    repeated_children = sorted(
        [
            {
                "id": child_id,
                "name_ar": (
                    f"{child_map[child_id].first_name} {child_map[child_id].last_name}"
                    if child_id in child_map
                    else f"طفل #{child_id}"
                ),
                "name_en": (
                    f"{child_map[child_id].first_name} {child_map[child_id].last_name}"
                    if child_id in child_map
                    else f"Child #{child_id}"
                ),
                "count": cnt,
            }
            for child_id, cnt in by_child_id.items()
            if cnt > 1
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Monthly trend — sort by month key
    trend = [{"month": m, "count": c} for m, c in sorted(by_month.items())]

    return {
        "total": total,
        "open": open_count,
        "closed": closed_count,
        "parent_informed": informed_count,
        "parent_not_informed": not_informed_count,
        "by_severity": by_severity,
        "by_type": by_type,
        "by_classification": by_classification,
        "by_kindergarten": by_kindergarten,
        "high_risk_count": high_risk_count,
        "repeated_children": repeated_children,
        "trend": trend,
    }


# ============================================================================
# Class Assignment Endpoint
# ============================================================================


# ============================================================================
# Manager Dashboard
# ============================================================================

# ============================================================================


@router.get("/reports")
def get_reports(
    shared_with_parent: Optional[bool] = None,
    child_id: Optional[int] = None,
    report_type: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get reports list, filtered by query params"""
    query = db.query(models.DailyReport)

    if current_user.role == models.UserRole.PARENT:
        # Parents only see approved reports for their own children
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return {"reports": []}
        child_ids = [c.id for c in db.query(models.Child).filter(
            models.Child.parent_id == parent_profile.id
        ).all()]
        query = query.filter(
            models.DailyReport.child_id.in_(child_ids),
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        )
    elif current_user.role in (models.UserRole.SUPERVISOR, models.UserRole.MANAGER):
        # Scope to the user's own kindergarten
        if current_user.kindergarten_id:
            query = query.filter(
                models.DailyReport.kindergarten_id == current_user.kindergarten_id
            )
        else:
            return {"reports": []}
    # ADMIN sees all — no additional filter

    if child_id:
        query = query.filter(models.DailyReport.child_id == child_id)

    reports = query.order_by(models.DailyReport.date.desc()).limit(50).all()

    return {
        "reports": [
            {
                "id": r.id,
                "child_id": r.child_id,
                "date": r.date.isoformat() if r.date else None,
                "status": r.status.value,
                "activities": r.activities,
                "notes": r.notes,
                "report_type": "PROGRESS",
            }
            for r in reports
        ]
    }


# ============================================================================
# TASK MANAGEMENT API
# ============================================================================

class TaskCreate(BaseModel):
    """Schema for creating a task"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = Field(default="MEDIUM")
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


class TaskUpdate(BaseModel):
    """Schema for updating a task"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


class TaskResponse(BaseModel):
    """Schema for task response"""
    id: int
    kindergarten_id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    assigned_to: Optional[int]
    created_by: int
    due_date: Optional[date]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Parent Registration Endpoint
# ============================================================================

class ParentRegistrationRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    second_name: Optional[str] = Field(default=None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    first_name_en: Optional[str] = Field(default=None, max_length=100)
    last_name_en: Optional[str] = Field(default=None, max_length=100)
    phone_number: str = Field(..., max_length=20)
    gender: str
    nationality: str = Field(..., min_length=1, max_length=100)
    national_id: Optional[str] = Field(default=None, max_length=50)
    passport_number: Optional[str] = Field(default=None, max_length=50)
    home_governorate: str = Field(..., min_length=1, max_length=100)
    home_city: str = Field(..., min_length=1, max_length=100)
    home_area: str = Field(..., min_length=1, max_length=100)
    home_address_line: str = Field(..., min_length=1, max_length=2000)
    correspondence_preference: Optional[bool] = True
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=128)
    primary_login_method: str = Field(default="email")

    @field_validator("email", mode="before")
    @classmethod
    def blank_registration_email_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone_number")
    @classmethod
    def normalize_registration_phone(cls, value):
        return normalize_jordan_phone(value)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value):
        normalized = value.strip().upper()
        if normalized not in {models.Gender.MALE.value, models.Gender.FEMALE.value}:
            raise ValueError("Invalid gender")
        return normalized

    @field_validator("primary_login_method")
    @classmethod
    def validate_primary_login_method(cls, value):
        normalized = value.strip().lower()
        if normalized not in {"email", "phone"}:
            raise ValueError("primary_login_method must be email or phone")
        return normalized

    @field_validator("home_governorate")
    @classmethod
    def validate_home_governorate(cls, value):
        if not validators.validate_jordan_governorate(value):
            raise ValueError(f"Invalid governorate: {value}. Must be one of: {', '.join(settings.JORDAN_GOVERNORATES)}")
        return value

    @model_validator(mode="after")
    def validate_primary_identifier(self):
        if self.primary_login_method == "email" and self.email is None:
            raise ValueError("Email is required when email is the primary login method.")
        return self


# ============================================================================
# Parent Profile Update
# ============================================================================

class ParentProfileUpdate(BaseModel):
    model_config = {"extra": "ignore"}
    first_name: Optional[str] = None
    second_name: Optional[str] = None
    last_name: Optional[str] = None
    first_name_en: Optional[str] = None
    last_name_en: Optional[str] = None
    phone_number: Optional[str] = None
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    home_governorate: Optional[str] = None
    home_city: Optional[str] = None
    home_area: Optional[str] = None
    home_address_line: Optional[str] = None
    work_address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    correspondence_preference: Optional[bool] = None


@router.put("/parent-profiles/{profile_id}")
def update_parent_profile(
    profile_id: int,
    body: ParentProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Partial update of a parent's own profile. Only the owning PARENT user may edit."""
    profile = db.query(models.ParentProfile).filter(models.ParentProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorised")
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(profile, field, value)

    required = ["first_name", "last_name", "phone_number", "home_governorate",
                "home_city", "home_area", "home_address_line", "nationality"]
    if all(getattr(profile, f) for f in required):
        profile.profile_complete = True
        if not profile.profile_completed_at:
            profile.profile_completed_at = datetime.now(timezone.utc)

    db.commit()
    return {"id": profile.id, "profile_complete": profile.profile_complete}


# ============================================================================
# Enrollment Endpoints
# ============================================================================

class EnrollmentApplicationRequest(BaseModel):
    # Child fields
    first_name: str
    last_name: str
    gender: str
    date_of_birth: str          # ISO format
    kindergarten_id: int

    # Father fields (required when parent_type == MOTHER or OTHER)
    father_name: Optional[str] = None
    father_national_id: Optional[str] = None
    father_nationality: Optional[str] = None
    father_phone: Optional[str] = None

    # Mother fields (required when parent_type == FATHER or OTHER)
    mother_first_name: Optional[str] = None
    mother_last_name: Optional[str] = None
    mother_nationality: Optional[str] = None
    mother_national_id: Optional[str] = None
    mother_passport_number: Optional[str] = None
    mother_phone: Optional[str] = None

    # Corresponding guardian selection
    corresponding_type: Optional[str] = None


# ── Corresponding guardian assignment (manager) ──────────────────────────────

class CorrespondingAssignRequest(BaseModel):
    contact_name: str
    contact_phone: str
    relationship: str  # ولي أمر / قريب / أخصائي اجتماعي / أخرى
    note: Optional[str] = None


@router.patch("/children/{child_id}/corresponding")
def assign_corresponding(
    child_id: int,
    payload: CorrespondingAssignRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a primary guardian contact for a PENDING_MANAGER child (Manager only)"""
    validators.validate_manager_role(current_user)

    child = db.query(models.Child).filter(
        models.Child.id == child_id,
        models.Child.deleted_at.is_(None)
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify child belongs to this manager's kindergarten
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=403, detail="Child does not belong to your kindergarten")

    if child.corresponding_type != "PENDING_MANAGER":
        raise HTTPException(status_code=400, detail="Child does not require a corresponding assignment")

    # Validate phone
    from auth import normalize_jordan_phone
    try:
        norm_phone = normalize_jordan_phone(payload.contact_phone.strip())
    except Exception:
        norm_phone = payload.contact_phone.strip()
    if not validators.validate_jordan_phone(norm_phone):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    child.corresponding_type = "GUARDIAN"
    child.corresponding_phone = norm_phone
    child.corresponding_pending_reason = None
    db.commit()

    validators.log_audit_action(
        db=db, user_id=current_user.id,
        action="CORRESPONDING_ASSIGNED",
        entity_type="Child", entity_id=child.id,
        details=f"name={payload.contact_name}, phone={norm_phone}, relationship={payload.relationship}",
        sensitivity_level=2
    )

    return {"ok": True, "child_id": child_id, "corresponding_type": "GUARDIAN", "phone": norm_phone}


@router.get("/manager/pending-corresponding")
def get_pending_corresponding(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List children awaiting primary guardian assignment (Manager only)"""
    validators.validate_manager_role(current_user)
    kindergarten_id = current_user.kindergarten_id

    rows = (
        db.query(models.Child, models.EnrollmentApplication)
        .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
        .filter(
            models.Child.corresponding_type == "PENDING_MANAGER",
            models.Child.deleted_at.is_(None),
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        )
        .all()
    )

    children = [
        {
            "child_id": child.id,
            "full_name": f"{child.first_name} {child.last_name}",
            "father_name": child.father_name,
            "enrollment_id": enrollment.id,
            "enrollment_date": enrollment.created_at.isoformat() if enrollment.created_at else None,
            "pending_reason": child.corresponding_pending_reason,
        }
        for child, enrollment in rows
    ]

    return {"count": len(children), "children": children}


@router.post("/enrollments/{enrollment_id}/review")
def review_enrollment_plural_alias(
    enrollment_id: int,
    decision: Optional[str] = Query(default=None, description="accept or reject"),
    reason: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compatibility endpoint for frontend plural enrollment review path."""
    from api.enrollment import review_enrollment
    if decision is None:
        decision = "accept"
    return review_enrollment(
        enrollment_id=enrollment_id,
        decision=decision,
        reason=reason,
        current_user=current_user,
        db=db
    )


# ============================================================================
# Attendance Endpoints
# ============================================================================

class AttendanceMarkRequest(BaseModel):
    child_id: int
    status: str = Field(..., pattern="^(PRESENT|ABSENT|LATE|EXCUSED|present|absent|late|excused)$")


class AttendanceBulkRequest(BaseModel):
    child_ids: List[int]
    status: str = Field(..., pattern="^(PRESENT|ABSENT|LATE|EXCUSED|present|absent|late|excused)$")


class AbsenceRequestCreate(BaseModel):
    child_id: int
    from_date: date
    to_date: date
    reason: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None


def _active_enrollment_for_child(db: Session, child_id: int) -> Optional[models.EnrollmentApplication]:
    return db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).order_by(models.EnrollmentApplication.id.desc()).first()


def _coerce_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@router.post("/attendance")
def mark_attendance(
    attendance_data: AttendanceMarkRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compatibility endpoint for simple attendance actions from the UI."""
    status_value = attendance_data.status.upper()
    if status_value in {"PRESENT", "LATE"}:
        from api.attendance_routes import check_in_child
        try:
            return check_in_child(
                child_id=attendance_data.child_id,
                method="manual",
                dropped_by_name=current_user.username,
                current_user=current_user,
                db=db
            )
        except HTTPException as exc:
            if exc.status_code == 400 and "already checked in" in str(exc.detail):
                return {"child_id": attendance_data.child_id, "status": status_value, "message": "Attendance already recorded"}
            raise

    child = db.query(models.Child).filter(models.Child.id == attendance_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    enrollment = _active_enrollment_for_child(db, attendance_data.child_id)
    if not enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)

    from utils.time_utils import today_amman
    today = today_amman()
    existing = db.execute(
        text(
            "SELECT id FROM absence_requests "
            "WHERE child_id = :child_id AND start_date = :start_date AND end_date = :end_date"
        ),
        {"child_id": child.id, "start_date": today, "end_date": today}
    ).first()
    if not existing:
        db.execute(
            text(
                "INSERT INTO absence_requests "
                "(parent_id, child_id, kindergarten_id, class_id, start_date, end_date, reason, status, created_at) "
                "VALUES (:parent_id, :child_id, :kindergarten_id, :class_id, :start_date, :end_date, :reason, 'APPROVED', :created_at)"
            ),
            {
                "parent_id": child.parent_id,
                "child_id": child.id,
                "kindergarten_id": enrollment.kindergarten_id,
                "class_id": enrollment.class_id,
                "start_date": today,
                "end_date": today,
                "reason": status_value.lower(),
                "created_at": datetime.now(),
            }
        )
        db.commit()
    return {"child_id": child.id, "status": status_value.lower()}


@router.post("/attendance/bulk")
def bulk_mark_attendance(
    bulk_data: AttendanceBulkRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk compatibility endpoint for attendance UI."""
    updated = 0
    errors = []
    for child_id in bulk_data.child_ids:
        try:
            mark_attendance(
                AttendanceMarkRequest(child_id=child_id, status=bulk_data.status),
                current_user=current_user,
                db=db
            )
            updated += 1
        except HTTPException as exc:
            errors.append({"child_id": child_id, "detail": exc.detail})
    return {"updated": updated, "errors": errors}


@router.get("/attendance/absence-requests")
def list_absence_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List absence requests scoped to the current user."""
    params = {}
    where = []
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return {"requests": []}
        where.append("ar.parent_id = :parent_id")
        params["parent_id"] = parent_profile.id
    elif current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        where.append("ar.kindergarten_id = :kindergarten_id")
        params["kindergarten_id"] = current_user.kindergarten_id
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = db.execute(
        text(
            "SELECT ar.*, c.first_name, c.last_name FROM absence_requests ar "
            "JOIN children c ON c.id = ar.child_id "
            f"{where_sql} ORDER BY ar.created_at DESC"
        ),
        params
    ).mappings().all()
    return {
        "requests": [
            {
                "id": row["id"],
                "child_id": row["child_id"],
                "child_name": f"{row['first_name']} {row['last_name']}",
                "from_date": str(row["start_date"]),
                "to_date": str(row["end_date"]),
                "reason": row["reason"],
                "notes": row["decision_note"],
                "status": str(row["status"]).lower(),
                "created_at": str(row["created_at"]) if row["created_at"] else None,
            }
            for row in rows
        ]
    }


@router.post("/attendance/absence-requests", status_code=status.HTTP_201_CREATED)
def create_absence_request(
    absence_data: AbsenceRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create an absence request for a parent's child."""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")
    if absence_data.to_date < absence_data.from_date:
        raise HTTPException(status_code=400, detail="to_date must be on or after from_date")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    child = db.query(models.Child).filter(
        models.Child.id == absence_data.child_id,
        models.Child.parent_id == parent_profile.id
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    enrollment = _active_enrollment_for_child(db, child.id)
    if not enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")

    # Check for overlapping pending/approved requests for the same child
    overlap = db.execute(
        text(
            "SELECT id FROM absence_requests "
            "WHERE child_id = :child_id AND status IN ('PENDING', 'APPROVED') "
            "AND start_date <= :end_date AND end_date >= :start_date "
            "LIMIT 1"
        ),
        {
            "child_id": child.id,
            "start_date": absence_data.from_date,
            "end_date": absence_data.to_date,
        }
    ).fetchone()
    if overlap:
        raise HTTPException(status_code=409, detail="Overlapping absence request exists for the same period")

    result = db.execute(
        text(
            "INSERT INTO absence_requests "
            "(parent_id, child_id, kindergarten_id, class_id, start_date, end_date, reason, status, decision_note, created_at) "
            "VALUES (:parent_id, :child_id, :kindergarten_id, :class_id, :start_date, :end_date, :reason, 'PENDING', :notes, :created_at)"
        ),
        {
            "parent_id": parent_profile.id,
            "child_id": child.id,
            "kindergarten_id": enrollment.kindergarten_id,
            "class_id": enrollment.class_id,
            "start_date": absence_data.from_date,
            "end_date": absence_data.to_date,
            "reason": absence_data.reason,
            "notes": absence_data.notes,
            "created_at": datetime.now(),
        }
    )
    db.commit()
    return {"id": result.lastrowid, "status": "pending"}


@router.post("/attendance/absence-requests/{request_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_absence_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending absence request. Only the owning parent may cancel."""
    row = db.execute(
        text("SELECT id, parent_user_id, status FROM absence_requests WHERE id = :id"),
        {"id": request_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Absence request not found")
    if row.parent_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorised")
    if row.status not in ("pending", "PENDING"):
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")
    db.execute(
        text("UPDATE absence_requests SET status = 'CANCELLED' WHERE id = :id"),
        {"id": request_id},
    )
    db.commit()
    return {"id": request_id, "status": "CANCELLED"}


# ============================================================================
# Attendance Report Endpoint
# ============================================================================

class AttendanceReportRequest(BaseModel):
    kindergarten_id: int
    class_ids: Optional[List[int]] = None
    child_ids: Optional[List[int]] = None
    period_type: str = Field(..., pattern="^(day|week|month|range)$")
    date: Optional[str] = None  # For day/week/month
    start_date: Optional[str] = None  # For range
    end_date: Optional[str] = None  # For range

    @field_validator("period_type", "date", "start_date", "end_date")
    def validate_dates(cls, v, info):
        if info.field_name == "period_type":
            period_type = v
        else:
            period_type = info.data.get("period_type")

        if period_type == "range":
            if not info.data.get("start_date") or not info.data.get("end_date"):
                raise ValueError("start_date and end_date required for range period")
        elif period_type in ["day", "week", "month"]:
            if not info.data.get("date"):
                raise ValueError("date required for day/week/month period")
        return v


class AttendanceReportResponse(BaseModel):
    meta: dict
    dates: List[str]
    children: List[dict]
    matrix: dict
    totals: dict
    chart_data: dict


# ============================================================================
# Daily Reports Endpoints
# ============================================================================

class DailyReportCreateRequest(BaseModel):
    child_id: int
    date: str
    arrival_time: str
    leave_time: str
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    activities: Optional[str] = None
    notes: Optional[str] = None


def _minutes_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    if not start or not end:
        return None
    try:
        start_dt = datetime.strptime(start, "%H:%M")
        end_dt = datetime.strptime(end, "%H:%M")
    except ValueError:
        return None
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    return minutes if minutes >= 0 else None


def _meal_rating(report: models.DailyReport) -> str:
    meals = [report.breakfast, report.snack, report.milk, report.lunch]
    eaten = sum(1 for meal in meals if meal is True)
    if eaten >= 3:
        return "great"
    if eaten >= 1:
        return "good"
    return "none"


# ============================================================================
# Incidents Endpoints
# ============================================================================

class IncidentCreateRequest(BaseModel):
    child_id: int
    kindergarten_id: Optional[int] = None
    class_id: Optional[int] = None
    supervisor_id: Optional[int] = None
    type: str                     # IncidentType enum value
    classification: Optional[str] = None  # IncidentClassification enum value
    severity_level: str           # SeverityLevel enum value
    description: str
    occurred_at: str              # ISO datetime string
    followup_required_flag: Optional[bool] = False
    parent_informed: Optional[bool] = None
    parent_response: Optional[str] = None
    parent_not_informed_reason: Optional[str] = None


@router.get("/daily-reports/submitted")
def list_submitted_daily_reports(
    report_date: Optional[str] = Query(default=None, alias="date"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submitted daily reports for the reports/list page (MANAGER view)."""
    if current_user.role != models.UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Manager access required")
    from models import Class, EnrollmentApplication, EnrollmentStatus, Child, User as UserModel
    kg_id = current_user.kindergarten_id
    classes = db.query(Class).filter(Class.kindergarten_id == kg_id, Class.deleted_at.is_(None)).all()
    class_ids = {c.id for c in classes}
    child_ids = {
        e.child_id
        for e in db.query(EnrollmentApplication)
        .filter(EnrollmentApplication.class_id.in_(class_ids), EnrollmentApplication.status == EnrollmentStatus.ACTIVE)
        .all()
    }
    q = db.query(models.DailyReport).filter(
        models.DailyReport.child_id.in_(child_ids),
        models.DailyReport.status == models.DailyReportStatus.SUBMITTED,
    )
    if report_date:
        try:
            q = q.filter(models.DailyReport.date == date.fromisoformat(report_date))
        except ValueError:
            pass
    reports = q.order_by(models.DailyReport.date.desc()).all()
    children_map = {c.id: c for c in db.query(Child).filter(Child.id.in_(child_ids)).all()}
    return {
        "reports": [
            {
                "id": r.id,
                "child_name": f"{children_map[r.child_id].first_name} {children_map[r.child_id].last_name}" if r.child_id in children_map else "—",
                "date": str(r.date),
                "submitted_by": r.submitted_by_name if hasattr(r, "submitted_by_name") else None,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "status": r.status.value if r.status else None,
            }
            for r in reports
        ]
    }


@router.get("/daily-reports/supervisor/my-children")
def supervisor_my_children_report_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Children with today's report status for supervisor reports/list view."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Supervisor access required")
    today = date.today()
    from models import Child, SupervisorAssignment, EnrollmentApplication, EnrollmentStatus
    assignments = db.query(SupervisorAssignment).filter(
        SupervisorAssignment.supervisor_id == current_user.id,
        SupervisorAssignment.deleted_at.is_(None),
    ).all()
    class_ids = {a.class_id for a in assignments}
    if not class_ids:
        return {"children": []}
    child_ids = {
        e.child_id
        for e in db.query(EnrollmentApplication)
        .filter(EnrollmentApplication.class_id.in_(class_ids), EnrollmentApplication.status == EnrollmentStatus.ACTIVE)
        .all()
    }
    children = db.query(Child).filter(Child.id.in_(child_ids)).all()
    reports_today = {
        r.child_id: r
        for r in db.query(models.DailyReport)
        .filter(models.DailyReport.child_id.in_(child_ids), models.DailyReport.date == today)
        .all()
    }
    return {
        "children": [
            {
                "child_id": c.id,
                "child_name": f"{c.first_name} {c.last_name}",
                "can_create_report": c.id not in reports_today,
                "report_id": reports_today[c.id].id if c.id in reports_today else None,
                "report_status": reports_today[c.id].status.value if c.id in reports_today else None,
            }
            for c in children
        ]
    }


# ============================================================================
# KPI Endpoints
# ============================================================================


# ============================================================================
# Supervisor Endpoints
# ============================================================================

class SupervisorAssignmentRequest(BaseModel):
    supervisor_id: int
    class_id: int
    start_date: str
    is_primary: bool = False


class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str
    mastery_level: Optional[str] = None


@router.get("/curriculum/observations")
def list_observations(
    child_id: Optional[int] = None,
    class_id: Optional[int] = None,
    domain: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List observations for the curriculum dashboard, scoped by role."""
    query = db.query(models.Observation, models.Child).join(
        models.Child, models.Observation.child_id == models.Child.id
    )

    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return {"observations": []}
        query = query.filter(models.Child.parent_id == parent_profile.id)
    elif current_user.role != models.UserRole.ADMIN:
        query = query.join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)

    if child_id:
        query = query.filter(models.Observation.child_id == child_id)
    if class_id:
        child_ids_for_class = db.query(models.EnrollmentApplication.child_id).filter(
            models.EnrollmentApplication.class_id == class_id
        )
        query = query.filter(models.Observation.child_id.in_(child_ids_for_class))
    if domain:
        domain_key = domain.upper().replace("-", "_")
        if domain_key == "SOCIAL":
            domain_key = "SOCIAL_EMOTIONAL"
        try:
            query = query.filter(models.Observation.domain == models.LearningDomain(domain_key))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid learning domain")

    rows = query.order_by(models.Observation.observed_at.desc()).limit(limit).all()
    domain_out = {
        models.LearningDomain.SOCIAL_EMOTIONAL: "social",
        models.LearningDomain.COGNITIVE: "cognitive",
        models.LearningDomain.PHYSICAL: "physical",
        models.LearningDomain.LANGUAGE: "language",
    }
    return {
        "observations": [
            {
                "id": observation.id,
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "domain": domain_out.get(observation.domain, observation.domain.value.lower()),
                "text": observation.observation_text,
                "date": observation.observed_at.date().isoformat() if observation.observed_at else None,
                "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
            }
            for observation, child in rows
        ]
    }


class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str = Field(..., max_length=10000)
    mastery_level: Optional[str] = None
    observed_at: Optional[str] = None  # ISO format datetime string


# ============================================================================
# Portfolio Endpoints
# ============================================================================

class PortfolioCreateRequest(BaseModel):
    child_id: int
    title: str
    description: Optional[str] = None
    status: Optional[str] = None  # Allow status to be provided


class PortfolioResponse(BaseModel):
    id: int
    child_id: int
    title: str
    description: Optional[str]
    status: str
    published_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Curriculum Outcomes Endpoints
# ============================================================================

class CurriculumOutcomeResponse(BaseModel):
    id: int
    domain: str
    age_band_min_months: int
    age_band_max_months: int
    indicator_code: str
    description: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/curriculum/outcomes")
def list_curriculum_outcomes(
    domain: Optional[str] = None,
    age_band_min: Optional[int] = None,
    age_band_max: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List curriculum outcomes (learning indicators) with optional filtering"""
    query = db.query(models.CurriculumOutcome)

    if domain:
        try:
            domain_enum = models.LearningDomain(domain.upper())
            query = query.filter(models.CurriculumOutcome.domain == domain_enum)
        except ValueError:
            pass

    # Filter by age band overlap
    if age_band_min is not None:
        query = query.filter(models.CurriculumOutcome.age_band_max_months >= age_band_min)
    
    if age_band_max is not None:
        query = query.filter(models.CurriculumOutcome.age_band_min_months <= age_band_max)

    outcomes = query.order_by(
        models.CurriculumOutcome.domain,
        models.CurriculumOutcome.age_band_min_months
    ).all()

    return {
        "outcomes": [
            {
                "id": o.id,
                "domain": o.domain.value,
                "age_band_min_months": o.age_band_min_months,
                "age_band_max_months": o.age_band_max_months,
                "indicator_code": o.indicator_code,
                "description": o.description
            }
            for o in outcomes
        ]
    }


@router.get("/curriculum/outcomes/{outcome_id}")
def get_curriculum_outcome(
    outcome_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific curriculum outcome details"""
    outcome = db.query(models.CurriculumOutcome).filter(
        models.CurriculumOutcome.id == outcome_id
    ).first()

    if not outcome:
        raise HTTPException(status_code=404, detail="Curriculum outcome not found")

    return {
        "id": outcome.id,
        "domain": outcome.domain.value,
        "age_band_min_months": outcome.age_band_min_months,
        "age_band_max_months": outcome.age_band_max_months,
        "indicator_code": outcome.indicator_code,
        "description": outcome.description
    }


# ============================================================================
# Health Alerts Endpoints (CRUD)
# ============================================================================

class HealthAlertCreateRequest(BaseModel):
    alert_type: str
    description: str
    severity: str

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity_upper(cls, v: Any) -> str:
        return v.upper() if isinstance(v, str) else v


# ============================================================================
# Audit Logs Endpoints
# ============================================================================

