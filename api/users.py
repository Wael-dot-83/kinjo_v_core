"""
Users domain endpoints
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta, timezone, UTC

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from ui_language import set_ui_language_cookie as _set_ui_language_cookie
from audit_actions import AuditAction
import validators
from captcha_service import captcha_error_message, captcha_required, verify_captcha
from config import settings
from database import get_db
from dependencies import get_current_user, require_admin
from rate_limiter import limiter

logger = logging.getLogger(__name__)

from api.auth.password_reset_service import (
    issue_password_reset_token,
    resolve_valid_token,
    deliver_password_reset_email,
)

router = APIRouter(tags=["Users"])

MAX_USER_EXPORT_ROWS = 10_000


def _log_access_denied(
    db: Session, user: models.User, action: str, details: Optional[str], request: Request, entity_type: str = "User"
) -> None:
    ip_address = request.client.host if request.client else None
    try:
        validators.log_audit_action(
            db=db,
            user_id=user.id,
            action=AuditAction.ACCESS_DENIED,
            entity_type=entity_type,
            entity_id=None,
            details=f"{action}: {details}" if details else action,
            ip_address=ip_address,
            sensitivity_level=2,
        )
    except (SQLAlchemyError, TypeError, ValueError) as exc:
        logger.warning("AUDIT_LOG_FAILED action=%s user_id=%s: %s", action, user.id, exc)


DUPLICATE_ERROR_MAP = {
    "name_ar": {"code": "error_duplicate_name_ar", "message": "This Arabic name is already registered."},
    "name_en": {"code": "error_duplicate_name_en", "message": "This English name is already registered."},
    "contact_phone": {"code": "error_duplicate_phone", "message": "This phone number is already registered."},
    "contact_email": {"code": "error_duplicate_email", "message": "This email is already registered."},
    "license_number": {"code": "error_duplicate_license", "message": "This license number is already registered."},
}


# ============================================================================
# User Profile Endpoints
# ============================================================================


class UserResponse(BaseModel):
    id: int
    public_id: Optional[str] = None
    username: str
    email: Optional[str] = None
    role: str
    status: str
    kindergarten_id: Optional[int] = None
    must_change_password: bool = False
    mfa_enabled: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/users/me", response_model=UserResponse)
def get_current_user_info(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current authenticated user's information"""
    from auth import requires_password_change

    return UserResponse(
        id=current_user.id,
        public_id=current_user.public_id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        status=current_user.status.value,
        kindergarten_id=current_user.kindergarten_id,
        must_change_password=requires_password_change(current_user),
        mfa_enabled=bool(getattr(current_user, "mfa_enabled", False)),
        created_at=current_user.created_at,
    )


@router.get("/users/me/language")
def get_user_language(
    current_user: models.User = Depends(get_current_user),
):
    """Get user language preference."""
    return {"user_lang": getattr(current_user, "preferred_language", "ar") or "ar"}


class UiLanguageRequest(BaseModel):
    language: str


@router.post("/ui-language")
def set_ui_language(payload: UiLanguageRequest, response: Response):
    """Set the UI language cookie for a visitor who has no session yet.

    Login and password-reset need to switch language before authentication
    exists, so those pages previously wrote the cookie from JavaScript. A
    document.cookie write is host-only while the server sets kinjo_lang with
    COOKIE_DOMAIN, and the two do not overwrite each other -- the browser kept
    both with different values and rendering lagged a step behind the request.
    Routing the anonymous path through the server keeps a single writer.

    Deliberately performs no database work: an unauthenticated caller must not
    be able to mutate any user record. Authenticated callers use
    PUT /users/me/language, which persists the preference as well.
    """
    if payload.language not in ("ar", "en"):
        raise HTTPException(status_code=400, detail="Supported languages: ar, en")
    _set_ui_language_cookie(response, payload.language)
    return {"language": payload.language}


class LanguageUpdateRequest(BaseModel):
    user_lang: str


@router.put("/users/me/language")
def update_user_language(
    payload: LanguageUpdateRequest,
    response: Response,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user language preference.

    This also rewrites the kinjo_lang cookie. Server-side rendering resolves the
    UI language from that cookie, and the cookie was only ever written at login,
    so persisting the preference here without updating it left the server
    rendering the *old* language while the client rewrote documentElement to the
    new one — every page came out with mixed Arabic/English text and a direction
    that disagreed with its content.

    The cookie must carry the same attributes the login path uses. It is set
    with COOKIE_DOMAIN so it is shared across the apex and www hosts; a
    host-only cookie of the same name does not overwrite the domain-wide one,
    it merely shadows it inconsistently.
    """
    if payload.user_lang not in ("ar", "en"):
        raise HTTPException(status_code=400, detail="Supported languages: ar, en")
    current_user.preferred_language = payload.user_lang
    # Sync notification_language on parent_profiles so notifications use the
    # same language as the UI preference.
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if parent_profile:
            parent_profile.notification_language = payload.user_lang
    db.commit()
    db.refresh(current_user)
    _set_ui_language_cookie(response, current_user.preferred_language)
    return {"user_lang": current_user.preferred_language}


# ============================================================================
# Change Password Endpoint
# ============================================================================


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.post("/users/change-password")
@limiter.limit("10/minute")
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password"""
    from auth import verify_password, change_user_password

    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    change_user_password(db, current_user, payload.new_password)
    return {"message": "Password changed successfully"}


# ============================================================================
# Admin User Management Endpoints
# ============================================================================


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: models.UserRole
    kindergarten_id: Optional[int] = None


class ParentProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    parent_type: Optional[str] = Field(default=None, pattern="^(FATHER|MOTHER|OTHER)$")
    national_id: Optional[str] = Field(default=None, max_length=50)
    nationality: Optional[str] = Field(default=None, max_length=100)


@router.put("/users/me")
def update_current_user_profile(
    update_data: ParentProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's profile (parent fields: name, phone, parent_type, etc.)."""
    from auth import normalize_email, normalize_jordan_phone, jordan_phone_login_variants

    if update_data.email and update_data.email != current_user.email:
        normalized_email = normalize_email(str(update_data.email))
        existing = (
            db.query(models.User)
            .filter(
                func.lower(models.User.email) == normalized_email,
                models.User.id != current_user.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already used")
        current_user.email = normalized_email

    parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()

    if parent_profile:
        if update_data.first_name is not None:
            parent_profile.first_name = update_data.first_name.strip()
        if update_data.last_name is not None:
            parent_profile.last_name = update_data.last_name.strip()
        if update_data.phone is not None:
            phone = update_data.phone.strip()
            if phone:
                if not validators.validate_jordan_phone(phone):
                    raise HTTPException(status_code=400, detail="Invalid Jordanian phone number")
                normalized_phone = normalize_jordan_phone(phone)
                dup = (
                    db.query(models.ParentProfile)
                    .filter(
                        models.ParentProfile.phone_number.in_(jordan_phone_login_variants(phone)),
                        models.ParentProfile.user_id != current_user.id,
                        models.ParentProfile.deleted_at.is_(None),
                    )
                    .first()
                )
                if dup:
                    raise HTTPException(status_code=400, detail="Phone number already used")
                parent_profile.phone_number = normalized_phone
        if update_data.parent_type is not None:
            parent_profile.parent_type = update_data.parent_type
        if update_data.national_id is not None:
            stripped_nid = update_data.national_id.strip()
            if stripped_nid:
                dup_nid = (
                    db.query(models.ParentProfile)
                    .filter(
                        models.ParentProfile.national_id == stripped_nid,
                        models.ParentProfile.user_id != current_user.id,
                        models.ParentProfile.deleted_at.is_(None),
                    )
                    .first()
                )
                if dup_nid:
                    raise HTTPException(status_code=400, detail="National ID already used by another user")
            parent_profile.national_id = stripped_nid or None
        if update_data.nationality is not None:
            parent_profile.nationality = update_data.nationality.strip()

    db.commit()
    db.refresh(current_user)
    if parent_profile:
        db.refresh(parent_profile)

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value,
        "status": current_user.status.value,
        "first_name": parent_profile.first_name if parent_profile else None,
        "last_name": parent_profile.last_name if parent_profile else None,
        "parent_type": parent_profile.parent_type if parent_profile else None,
        "national_id": parent_profile.national_id if parent_profile else None,
        "nationality": parent_profile.nationality if parent_profile else None,
    }


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[models.UserRole] = None
    status: Optional[models.UserStatus] = None
    kindergarten_id: Optional[int] = None


@router.get("/users")
def list_users(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    role: Optional[models.UserRole] = None,
    status: Optional[models.UserStatus] = None,
    kindergarten_id: Optional[int] = None,
    phone: Optional[str] = None,
    governorate: Optional[str] = None,
    search: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List users. Admins see all. Managers see only their kindergarten's staff."""
    query = db.query(models.User).filter(models.User.deleted_at.is_(None))
    active_parent_statuses = (models.EnrollmentStatus.ACCEPTED, models.EnrollmentStatus.ACTIVE)

    if phone or governorate:
        query = query.outerjoin(models.ParentProfile, models.ParentProfile.user_id == models.User.id).outerjoin(
            models.Kindergarten, models.Kindergarten.id == models.User.kindergarten_id
        )

    if current_user.role == models.UserRole.ADMIN:
        if kindergarten_id:
            parent_ids_query = (
                db.query(models.ParentProfile.user_id)
                .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
                .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
                .filter(
                    models.EnrollmentApplication.kindergarten_id == kindergarten_id,
                    models.EnrollmentApplication.status.in_(active_parent_statuses),
                )
                .distinct()
            )
            query = query.filter(
                or_(
                    and_(models.User.role == models.UserRole.PARENT, models.User.id.in_(parent_ids_query)),
                    and_(models.User.role != models.UserRole.PARENT, models.User.kindergarten_id == kindergarten_id),
                )
            )
        # Admin cannot see or manage other admin users
        query = query.filter(models.User.role != models.UserRole.ADMIN)
    elif current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            _log_access_denied(db, current_user, "list_users", "Missing kindergarten", request)
            raise HTTPException(status_code=400, detail="Manager must be assigned to a kindergarten")
        if role == models.UserRole.PARENT:
            if kindergarten_id and kindergarten_id != current_user.kindergarten_id:
                query = query.filter(models.User.id == -1)
            else:
                parent_ids_query = (
                    db.query(models.ParentProfile.user_id)
                    .join(models.Child, models.Child.parent_id == models.ParentProfile.id)
                    .join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id)
                    .filter(
                        models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                        models.EnrollmentApplication.status.in_(active_parent_statuses),
                    )
                    .distinct()
                )
                query = query.filter(models.User.role == models.UserRole.PARENT, models.User.id.in_(parent_ids_query))
        else:
            query = query.filter(models.User.kindergarten_id == current_user.kindergarten_id)
            if kindergarten_id and kindergarten_id != current_user.kindergarten_id:
                query = query.filter(models.User.kindergarten_id == kindergarten_id)
    else:
        _log_access_denied(db, current_user, "list_users", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    if role:
        # Prevent admins from filtering by ADMIN role
        if role == models.UserRole.ADMIN and current_user.role == models.UserRole.ADMIN:
            _log_access_denied(db, current_user, "list_users", "Cannot filter by ADMIN role", request)
            raise HTTPException(status_code=403, detail="Cannot filter by ADMIN role")
        query = query.filter(models.User.role == role)

    if status:
        query = query.filter(models.User.status == status)

    if search:
        query = query.filter(or_(models.User.username.ilike(f"%{search}%"), models.User.email.ilike(f"%{search}%")))

    if phone:
        query = query.filter(
            or_(
                models.ParentProfile.phone_number.ilike(f"%{phone}%"),
                models.Kindergarten.contact_phone.ilike(f"%{phone}%"),
            )
        )

    if governorate:
        query = query.filter(
            or_(
                models.ParentProfile.home_governorate.ilike(f"%{governorate}%"),
                models.Kindergarten.governorate.ilike(f"%{governorate}%"),
            )
        )

    users = query.offset(skip).limit(limit).all()

    # Manually serialize to avoid enum issues if using Pydantic directly for list
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role.value,
            "status": u.status.value,
            "kindergarten_id": u.kindergarten_id,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.get("/users/export")
def export_users(
    format: str = Query("csv", pattern="^(csv)$"),
    role: Optional[models.UserRole] = None,
    status_filter: Optional[models.UserStatus] = Query(None, alias="status"),
    kindergarten_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export users list (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    query = db.query(models.User).filter(models.User.deleted_at.is_(None))

    if kindergarten_id:
        query = query.filter(models.User.kindergarten_id == kindergarten_id)

    # Exclude admin users from export
    query = query.filter(models.User.role != models.UserRole.ADMIN)

    if role:
        query = query.filter(models.User.role == role)
    if status_filter:
        query = query.filter(models.User.status == status_filter)

    users = query.limit(MAX_USER_EXPORT_ROWS).all()

    import csv
    import io
    from fastapi.responses import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Email", "Role", "Status", "Kindergarten ID", "Created At"])

    for u in users:
        writer.writerow(
            [u.id, u.username, u.email, u.role.value, u.status.value, u.kindergarten_id or "N/A", u.created_at]
        )

    return Response(
        content="\ufeff" + output.getvalue(),  # UTF-8 BOM for Arabic Excel compatibility (CHART-003)
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users_export_{datetime.now(_JORDAN_TZ).date()}.csv"},
    )


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create new user. Admins can create all. Managers can create staff for their KG."""

    # Permission Check
    if current_user.role == models.UserRole.ADMIN:
        # Admin cannot create other admin users
        if user_data.role == models.UserRole.ADMIN:
            _log_access_denied(db, current_user, "create_user", "Cannot create admin users", request)
            raise HTTPException(status_code=403, detail="Cannot create admin users")
        if user_data.role == models.UserRole.MANAGER:
            raise HTTPException(
                status_code=409,
                detail=("Manager accounts must be created through the canonical admin manager-assignment workflow."),
            )
    elif current_user.role == models.UserRole.MANAGER:
        # Manager can only create non-admin, non-manager roles for their own KG
        if user_data.role in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
            _log_access_denied(db, current_user, "create_user", "Manager attempted privileged role", request)
            raise HTTPException(status_code=403, detail="Managers cannot create Admin or Manager accounts")

        # Enforce Kindergarten ID
        if user_data.kindergarten_id and user_data.kindergarten_id != current_user.kindergarten_id:
            _log_access_denied(db, current_user, "create_user", "Cross-kindergarten creation attempt", request)
            raise HTTPException(status_code=403, detail="Cannot create users for other kindergartens")

        user_data.kindergarten_id = current_user.kindergarten_id
    else:
        _log_access_denied(db, current_user, "create_user", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if exists (case-insensitive email check)
    existing = (
        db.query(models.User)
        .filter(
            or_(models.User.username == user_data.username, func.lower(models.User.email) == user_data.email.lower())
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    from auth import get_password_hash

    hashed_password = get_password_hash(user_data.password)

    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role,
        kindergarten_id=user_data.kindergarten_id,
        status=models.UserStatus.ACTIVE,
        must_change_password=True,
    )

    db.add(new_user)
    db.flush()
    db.refresh(new_user)

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.USER_CREATED,
            entity_type="User",
            entity_id=new_user.id,
            sensitivity_level=3,
        )
    except Exception:
        db.rollback()
        raise

    return {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "role": new_user.role.value,
        "status": new_user.status.value,
    }


class StaffCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    kindergarten_id: Optional[int] = None
    role: Optional[models.UserRole] = models.UserRole.SUPERVISOR
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    passport_number: Optional[str] = None


@router.post("/staff/create", status_code=status.HTTP_201_CREATED)
def create_staff(
    request: Request,
    staff_data: StaffCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new staff member (Supervisor or Teacher).
    Managers can create staff for their own kindergarten.
    Admins can create staff for any kindergarten.
    """
    # Permission check
    if current_user.role == models.UserRole.ADMIN:
        kindergarten_id = staff_data.kindergarten_id
        if not kindergarten_id:
            raise HTTPException(status_code=400, detail="Admin must specify kindergarten_id")
    elif current_user.role == models.UserRole.MANAGER:
        kindergarten_id = current_user.kindergarten_id
        if staff_data.kindergarten_id and staff_data.kindergarten_id != kindergarten_id:
            raise HTTPException(status_code=403, detail="Managers can only create staff for their own kindergarten")
    else:
        raise HTTPException(status_code=403, detail="Only Admins and Managers can create staff")

    # Only allow non-privileged roles
    allowed_roles = [models.UserRole.SUPERVISOR, models.UserRole.PARENT]
    if staff_data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Staff role must be one of: {[r.value for r in allowed_roles]}")

    # Verify kindergarten exists
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check for duplicate username or email
    existing = (
        db.query(models.User)
        .filter(
            or_(
                models.User.username == staff_data.username,
                (models.User.email == staff_data.email) if staff_data.email else False,
            )
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    # Validate identity by nationality if provided
    if staff_data.nationality:
        try:
            validators.validate_identity_by_nationality(
                staff_data.nationality, staff_data.national_id, staff_data.passport_number
            )
        except validators.ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

    from auth import get_password_hash

    hashed_password = get_password_hash(staff_data.password)

    new_staff = models.User(
        username=staff_data.username,
        email=staff_data.email,
        hashed_password=hashed_password,
        role=staff_data.role,
        kindergarten_id=kindergarten_id,
        status=models.UserStatus.ACTIVE,
        must_change_password=True,
        full_name=staff_data.full_name,
        phone_number=staff_data.phone_number,
        address=staff_data.address,
        nationality=staff_data.nationality,
        national_id=staff_data.national_id,
        passport_number=staff_data.passport_number,
    )

    db.add(new_staff)
    db.flush()
    db.refresh(new_staff)

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.STAFF_CREATED,
            entity_type="User",
            entity_id=new_staff.id,
            sensitivity_level=2,
        )
    except Exception:
        db.rollback()
        raise

    return {
        "id": new_staff.id,
        "username": new_staff.username,
        "email": new_staff.email,
        "role": new_staff.role.value,
        "kindergarten_id": new_staff.kindergarten_id,
        "status": new_staff.status.value,
        "full_name": new_staff.full_name,
        "phone_number": new_staff.phone_number,
        "address": new_staff.address,
        "nationality": new_staff.nationality,
        "national_id": new_staff.national_id,
        "passport_number": new_staff.passport_number,
    }


@router.get("/users/{user_id}")
def get_user(
    request: Request, user_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get user details"""
    user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Admin cannot view other admin users
    if current_user.role == models.UserRole.ADMIN:
        if user.role == models.UserRole.ADMIN and user.id != current_user.id:
            _log_access_denied(db, current_user, "get_user", "Cannot access other admin user", request)
            raise HTTPException(status_code=403, detail="Cannot access admin users")
    elif current_user.id != user_id:
        # Non-admin can only view self
        _log_access_denied(db, current_user, "get_user", "Non-admin access to other user", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "kindergarten_id": user.kindergarten_id,
        "created_at": user.created_at,
    }


@router.put("/users/{user_id}")
def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user"""
    user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before_state = {
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "kindergarten_id": user.kindergarten_id,
    }

    if current_user.role == models.UserRole.ADMIN:
        # Admin cannot update other admin users
        if user.role == models.UserRole.ADMIN and user.id != current_user.id:
            _log_access_denied(db, current_user, "update_user", "Cannot update other admin users", request)
            raise HTTPException(status_code=403, detail="Cannot update admin users")
        # Admin cannot promote users to admin role
        if user_data.role == models.UserRole.ADMIN:
            _log_access_denied(db, current_user, "update_user", "Cannot promote to admin role", request)
            raise HTTPException(status_code=403, detail="Cannot promote users to admin role")
    elif current_user.id != user_id:
        # Non-admin can only update self
        _log_access_denied(db, current_user, "update_user", "Non-admin update of other user", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    if user_data.email:
        # Case-insensitive uniqueness check
        existing = (
            db.query(models.User)
            .filter(func.lower(models.User.email) == user_data.email.lower(), models.User.id != user_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already used")
        user.email = user_data.email

    if user_data.password:
        # Password change via PUT requires admin; non-admins must use /users/change-password
        if current_user.role != models.UserRole.ADMIN:
            raise HTTPException(
                status_code=400,
                detail="Use POST /users/change-password to update your password (current password required)",
            )
        from auth import get_password_hash

        user.hashed_password = get_password_hash(user_data.password)

    if current_user.role == models.UserRole.ADMIN:
        lifecycle_fields = {"role", "status", "kindergarten_id"}
        touches_manager_lifecycle = bool(user_data.model_fields_set & lifecycle_fields) and (
            user.role == models.UserRole.MANAGER or user_data.role == models.UserRole.MANAGER
        )
        if touches_manager_lifecycle:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Manager lifecycle changes must use /api/admin/users or the "
                    "kindergarten manager-assignment workflow."
                ),
            )
        if user_data.role:
            user.role = user_data.role
        if user_data.status:
            user.status = user_data.status
        if user_data.kindergarten_id is not None:
            # Validate the kindergarten exists before assigning
            if user_data.kindergarten_id > 0:
                kg_exists = (
                    db.query(models.Kindergarten.id).filter(models.Kindergarten.id == user_data.kindergarten_id).first()
                )
                if not kg_exists:
                    raise HTTPException(status_code=400, detail="Kindergarten not found")
            user.kindergarten_id = user_data.kindergarten_id

    db.flush()
    db.refresh(user)

    after_state = {
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "kindergarten_id": user.kindergarten_id,
    }

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.USER_UPDATED,
            entity_type="User",
            entity_id=user.id,
            sensitivity_level=3,
            old_data=before_state,
            new_data=after_state,
        )
    except Exception:
        db.rollback()
        raise

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    request: Request, user_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete user (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "delete_user", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Admin cannot delete other admin users
    if user.role == models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "delete_user", "Cannot delete admin users", request)
        raise HTTPException(status_code=403, detail="Cannot delete admin users")
    if user.role == models.UserRole.MANAGER:
        raise HTTPException(
            status_code=409,
            detail="Manager deletion must use the canonical /api/admin/users workflow.",
        )

    user.deleted_at = datetime.now(UTC)
    user.deleted_by = current_user.id
    user.status = models.UserStatus.INACTIVE

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.USER_DELETED,
            entity_type="User",
            entity_id=user_id,
            sensitivity_level=3,
        )
    except Exception:
        db.rollback()
        raise
    return None


# Password Reset Endpoints
class PasswordResetRequest(BaseModel):
    email: str
    captcha_token: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
    admin_password: str = Field(..., min_length=8)


PASSWORD_RESET_GENERIC_MESSAGE = "If the email exists, a reset link has been sent"


def initiate_password_reset(
    request: Request,
    email: str,
    captcha_token: Optional[str],
    db: Session,
) -> tuple[Optional[models.User], Optional[str]]:
    """Apply the canonical anti-abuse and account-eligibility reset policy."""
    if captcha_required() and not verify_captcha(captcha_token):
        lang = "en" if request.headers.get("Accept-Language", "ar").startswith("en") else "ar"
        raise HTTPException(status_code=400, detail=captcha_error_message(lang))

    user = (
        db.query(models.User)
        .filter(
            models.User.email == email,
            models.User.deleted_at.is_(None),
        )
        .first()
    )
    if not user:
        return None, None

    try:
        token = issue_password_reset_token(db, user, commit=False)
        validators.log_audit_action(
            db=db,
            user_id=user.id,
            action=AuditAction.PASSWORD_RESET_REQUESTED,
            entity_type="User",
            entity_id=user.id,
            sensitivity_level=2,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "PASSWORD_RESET_AUDIT_FAILED user_id=%s: token issuance rolled back: %s",
            user.id,
            exc,
        )
        # Preserve anti-enumeration: an audit outage must look exactly like an
        # unknown email while failing closed without issuing a usable token.
        return None, None

    base_url = str(request.base_url).rstrip("/")
    delivered = deliver_password_reset_email(base_url, user, token)
    if not delivered:
        logger.warning(
            "PASSWORD_RESET_UNDELIVERED user_id=%s: token issued but email not sent "
            "(check SMTP config or prior CRITICAL log for delivery error)",
            user.id,
        )

    return user, token


def apply_password_reset(
    db: Session,
    token: str,
    new_password: str,
) -> Optional[models.PasswordResetToken]:
    """Apply the canonical password lifecycle without committing the caller's transaction."""
    token_record = resolve_valid_token(db, token)
    if not token_record:
        return None

    claimed = (
        db.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.id == token_record.id,
            models.PasswordResetToken.used.is_(False),
            models.PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .update({"used": True}, synchronize_session=False)
    )
    if claimed != 1:
        db.expire(token_record)
        return None

    from auth import change_user_password

    change_user_password(db, token_record.user, new_password, commit=False)
    token_record.used = True
    return token_record


@router.post("/users/{user_id}/admin-reset-password", include_in_schema=False)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def admin_reset_password(
    request: Request,
    user_id: int,
    reset_data: AdminPasswordReset,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Compatibility alias for the canonical admin password reset endpoint."""
    from admin_endpoints import admin_reset_password as canonical_admin_reset_password

    return canonical_admin_reset_password(
        request=request,
        user_id=user_id,
        reset_data=reset_data,
        current_user=current_user,
        db=db,
    )


@router.post("/users/request-password-reset")
@limiter.limit("5/hour")
def request_password_reset(request: Request, reset_request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Request password reset token (for self-service)"""
    initiate_password_reset(
        request=request,
        email=reset_request.email,
        captcha_token=reset_request.captcha_token,
        db=db,
    )
    # Always return the same message — never reveal whether email exists.
    return {"message": PASSWORD_RESET_GENERIC_MESSAGE}


@router.post("/users/reset-password")
@limiter.limit("10/hour")
def reset_password(request: Request, reset_data: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Reset password using token"""

    try:
        token_record = apply_password_reset(db, reset_data.token, reset_data.new_password)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    try:
        validators.log_audit_action(
            db=db,
            user_id=token_record.user.id,
            action=AuditAction.PASSWORD_RESET,
            entity_type="User",
            entity_id=token_record.user.id,
            sensitivity_level=2,
        )
    except Exception:
        db.rollback()
        raise

    return {"message": "Password reset successfully"}


# Bulk Operations Endpoints
class BulkStatusUpdate(BaseModel):
    user_ids: List[int] = Field(..., min_length=1, max_length=settings.MAX_BULK_UPDATE)
    new_status: models.UserStatus


class BulkDeleteRequest(BaseModel):
    user_ids: List[int] = Field(..., min_length=1, max_length=settings.MAX_BULK_DELETE)
    confirmation_text: Optional[str] = None


class BulkCreateRequest(BaseModel):
    users: List[UserCreate] = Field(..., min_length=1, max_length=settings.MAX_BULK_CREATE)


@router.post("/users/bulk-status-update")
@limiter.limit(settings.RATE_LIMIT_BULK_UPDATE)
def bulk_update_status(
    request: Request,
    bulk_data: BulkStatusUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk update user status (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "bulk_status_update", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Admin access required")

    if not bulk_data.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    if len(bulk_data.user_ids) > settings.MAX_BULK_UPDATE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update more than {settings.MAX_BULK_UPDATE} users at once",
        )

    # Check for admin users in the list - cannot update admin status
    admin_users = (
        db.query(models.User)
        .filter(models.User.id.in_(bulk_data.user_ids), models.User.role == models.UserRole.ADMIN)
        .all()
    )

    if admin_users:
        raise HTTPException(
            status_code=403, detail=f"Cannot update admin accounts: {', '.join([u.username for u in admin_users])}"
        )

    manager_users = (
        db.query(models.User)
        .filter(
            models.User.id.in_(bulk_data.user_ids),
            models.User.role == models.UserRole.MANAGER,
            models.User.deleted_at.is_(None),
        )
        .all()
    )
    if manager_users:
        raise HTTPException(
            status_code=409,
            detail="Manager status changes must use the canonical /api/admin/users workflow.",
        )

    # Update only non-admin users
    updated_count = (
        db.query(models.User)
        .filter(
            models.User.id.in_(bulk_data.user_ids),
            models.User.role != models.UserRole.ADMIN,
            models.User.deleted_at.is_(None),
        )
        .update({"status": bulk_data.new_status}, synchronize_session=False)
    )

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.BULK_STATUS_UPDATE,
            entity_type="User",
            entity_id=None,
            details=f"Updated {updated_count} users to status {bulk_data.new_status.value}",
            sensitivity_level=3,
        )
    except Exception:
        db.rollback()
        raise

    return {"message": f"Updated {updated_count} users successfully"}


@router.post("/users/bulk-delete")
@limiter.limit(settings.RATE_LIMIT_BULK_DELETE)
def bulk_delete_users(
    request: Request,
    bulk_data: BulkDeleteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk delete users (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "bulk_delete_users", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Admin access required")

    if not bulk_data.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    if len(bulk_data.user_ids) > settings.MAX_BULK_DELETE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete more than {settings.MAX_BULK_DELETE} users at once",
        )

    if current_user.id in bulk_data.user_ids:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    if bulk_data.confirmation_text != "DELETE":
        raise HTTPException(
            status_code=400,
            detail="Bulk delete requires confirmation_text='DELETE'",
        )

    # Prevent deleting admin accounts
    admin_users = (
        db.query(models.User)
        .filter(models.User.id.in_(bulk_data.user_ids), models.User.role == models.UserRole.ADMIN)
        .all()
    )

    if admin_users:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete admin accounts: {', '.join([u.username for u in admin_users])}"
        )

    manager_users = (
        db.query(models.User)
        .filter(
            models.User.id.in_(bulk_data.user_ids),
            models.User.role == models.UserRole.MANAGER,
            models.User.deleted_at.is_(None),
        )
        .all()
    )
    if manager_users:
        raise HTTPException(
            status_code=409,
            detail="Manager deletion must use the canonical /api/admin/users workflow.",
        )

    # Preserve referential integrity and auditability through soft deletion.
    now = datetime.now(UTC)
    deleted_count = (
        db.query(models.User)
        .filter(
            models.User.id.in_(bulk_data.user_ids),
            models.User.deleted_at.is_(None),
        )
        .update(
            {
                "deleted_at": now,
                "deleted_by": current_user.id,
                "status": models.UserStatus.INACTIVE,
            },
            synchronize_session=False,
        )
    )

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.BULK_USER_DELETE,
            entity_type="User",
            entity_id=None,
            details=f"Deleted {deleted_count} users",
            sensitivity_level=3,
        )
    except Exception:
        db.rollback()
        raise

    return {"message": f"Deleted {deleted_count} users successfully"}


@router.post("/users/bulk-create")
@limiter.limit(settings.RATE_LIMIT_BULK_CREATE)
def bulk_create_users(
    request: Request,
    bulk_data: BulkCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk create users (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "bulk_create_users", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Admin access required")

    if not bulk_data.users:
        raise HTTPException(status_code=400, detail="No users provided")

    if len(bulk_data.users) > settings.MAX_BULK_CREATE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create more than {settings.MAX_BULK_CREATE} users at once",
        )

    created_users = []
    errors = []

    # Pre-fetch all conflicting usernames/emails in one query to avoid N lookups
    all_usernames = {u.username for u in bulk_data.users if u.username}
    all_emails = {u.email for u in bulk_data.users if u.email}
    existing_users = (
        db.query(models.User)
        .filter(
            or_(
                models.User.username.in_(all_usernames),
                models.User.email.in_(all_emails),
            )
        )
        .all()
    )
    taken_usernames = {u.username for u in existing_users}
    taken_emails = {u.email for u in existing_users}

    for i, user_data in enumerate(bulk_data.users):
        try:
            # Cannot create admin users via bulk create
            if user_data.role == models.UserRole.ADMIN:
                errors.append(
                    {
                        "row": i + 1,
                        "field": "role",
                        "message": "Cannot create admin users",
                    }
                )
                continue
            if user_data.role == models.UserRole.MANAGER:
                errors.append(
                    {
                        "row": i + 1,
                        "field": "role",
                        "message": ("Manager accounts must use the canonical admin manager-assignment workflow"),
                    }
                )
                continue

            # Check against pre-fetched conflict set
            if user_data.username in taken_usernames or user_data.email in taken_emails:
                errors.append(
                    {
                        "row": i + 1,
                        "field": "username/email",
                        "message": "Username or email already exists",
                    }
                )
                continue

            from auth import get_password_hash

            hashed_password = get_password_hash(user_data.password)

            new_user = models.User(
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed_password,
                role=user_data.role,
                kindergarten_id=user_data.kindergarten_id,
                status=models.UserStatus.ACTIVE,
                must_change_password=True,
            )

            db.add(new_user)
            db.flush()  # Get the ID without committing

            created_users.append(
                {"id": new_user.id, "username": new_user.username, "email": new_user.email, "role": new_user.role.value}
            )

        except (SQLAlchemyError, TypeError, ValueError) as e:
            errors.append({"row": i + 1, "field": "unknown", "message": str(e)})

    try:
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.BULK_USER_CREATE,
            entity_type="User",
            entity_id=None,
            details=f"Created {len(created_users)} users, {len(errors)} errors",
            sensitivity_level=3,
        )
    except Exception:
        db.rollback()
        raise

    return {
        "message": f"Created {len(created_users)} users successfully",
        "created_users": created_users,
        "errors": errors,
    }
