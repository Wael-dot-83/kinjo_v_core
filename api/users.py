"""
Users domain endpoints
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta, UTC
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user
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
def get_current_user_info(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current authenticated user's information"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        status=current_user.status.value,
        kindergarten_id=current_user.kindergarten_id,
        must_change_password=current_user.must_change_password,
        mfa_enabled=bool(getattr(current_user, "mfa_enabled", False)),
        created_at=current_user.created_at
    )


@router.get("/users/me/language")
def get_user_language(
    current_user: models.User = Depends(get_current_user),
):
    """Get user language preference."""
    return {"user_lang": getattr(current_user, "preferred_language", "ar") or "ar"}


class LanguageUpdateRequest(BaseModel):
    user_lang: str


@router.put("/users/me/language")
def update_user_language(
    payload: LanguageUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user language preference."""
    if payload.user_lang not in ("ar", "en"):
        raise HTTPException(status_code=400, detail="Supported languages: ar, en")
    current_user.preferred_language = payload.user_lang
    # Sync notification_language on parent_profiles so notifications use the
    # same language as the UI preference.
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if parent_profile:
            parent_profile.notification_language = payload.user_lang
    db.commit()
    db.refresh(current_user)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
):
    """List users. Admins see all. Managers see only their kindergarten's staff."""
    query = db.query(models.User)
    active_parent_statuses = (
        models.EnrollmentStatus.ACCEPTED,
        models.EnrollmentStatus.ACTIVE
    )

    if phone or governorate:
        query = query.outerjoin(
            models.ParentProfile,
            models.ParentProfile.user_id == models.User.id
        ).outerjoin(
            models.Kindergarten,
            models.Kindergarten.id == models.User.kindergarten_id
        )

    if current_user.role == models.UserRole.ADMIN:
        if kindergarten_id:
            parent_ids_query = db.query(models.ParentProfile.user_id).join(
                models.Child,
                models.Child.parent_id == models.ParentProfile.id
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kindergarten_id,
                models.EnrollmentApplication.status.in_(active_parent_statuses)
            ).distinct()
            query = query.filter(
                or_(
                    and_(
                        models.User.role == models.UserRole.PARENT,
                        models.User.id.in_(parent_ids_query)
                    ),
                    and_(
                        models.User.role != models.UserRole.PARENT,
                        models.User.kindergarten_id == kindergarten_id
                    )
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
                parent_ids_query = db.query(models.ParentProfile.user_id).join(
                    models.Child,
                    models.Child.parent_id == models.ParentProfile.id
                ).join(
                    models.EnrollmentApplication,
                    models.EnrollmentApplication.child_id == models.Child.id
                ).filter(
                    models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                    models.EnrollmentApplication.status.in_(active_parent_statuses)
                ).distinct()
                query = query.filter(
                    models.User.role == models.UserRole.PARENT,
                    models.User.id.in_(parent_ids_query)
                )
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
        query = query.filter(or_(
            models.User.username.ilike(f"%{search}%"),
            models.User.email.ilike(f"%{search}%")
        ))

    if phone:
        query = query.filter(or_(
            models.ParentProfile.phone_number.ilike(f"%{phone}%"),
            models.Kindergarten.contact_phone.ilike(f"%{phone}%")
        ))

    if governorate:
        query = query.filter(or_(
            models.ParentProfile.home_governorate.ilike(f"%{governorate}%"),
            models.Kindergarten.governorate.ilike(f"%{governorate}%")
        ))
    
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
            "created_at": u.created_at
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
    db: Session = Depends(get_db)
):
    """Export users list (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    query = db.query(models.User)

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
        writer.writerow([
            u.id,
            u.username,
            u.email,
            u.role.value,
            u.status.value,
            u.kindergarten_id or "N/A",
            u.created_at
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users_export_{date.today()}.csv"}
    )

@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new user. Admins can create all. Managers can create staff for their KG."""
    
    # Permission Check
    if current_user.role == models.UserRole.ADMIN:
        # Admin cannot create other admin users
        if user_data.role == models.UserRole.ADMIN:
            _log_access_denied(db, current_user, "create_user", "Cannot create admin users", request)
            raise HTTPException(status_code=403, detail="Cannot create admin users")
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

    # Check if exists
    existing = db.query(models.User).filter(
        or_(models.User.username == user_data.username, models.User.email == user_data.email)
    ).first()
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
        status=models.UserStatus.ACTIVE
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="USER_CREATED",
        entity_type="User",
        entity_id=new_user.id,
        sensitivity_level=3
    )
    
    return {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "role": new_user.role.value,
        "status": new_user.status.value
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
    db: Session = Depends(get_db)
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
            raise HTTPException(
                status_code=403,
                detail="Managers can only create staff for their own kindergarten"
            )
    else:
        raise HTTPException(status_code=403, detail="Only Admins and Managers can create staff")

    # Only allow non-privileged roles
    allowed_roles = [models.UserRole.SUPERVISOR, models.UserRole.PARENT]
    if staff_data.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Staff role must be one of: {[r.value for r in allowed_roles]}"
        )

    # Verify kindergarten exists
    kg = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check for duplicate username or email
    existing = db.query(models.User).filter(
        or_(
            models.User.username == staff_data.username,
            (models.User.email == staff_data.email) if staff_data.email else False
        )
    ).first()
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
    db.commit()
    db.refresh(new_staff)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="STAFF_CREATED",
        entity_type="User",
        entity_id=new_staff.id,
        sensitivity_level=2
    )

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
    request: Request,
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user details"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
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
        "created_at": user.created_at
    }

@router.put("/users/{user_id}")
def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        # Check uniqueness
        existing = db.query(models.User).filter(
            models.User.email == user_data.email, 
            models.User.id != user_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already used")
        user.email = user_data.email
        
    if user_data.password:
        from auth import get_password_hash
        user.hashed_password = get_password_hash(user_data.password)
        
    if current_user.role == models.UserRole.ADMIN:
        if user_data.role:
            user.role = user_data.role
        if user_data.status:
            user.status = user_data.status
        if user_data.kindergarten_id is not None:
             # Allow 0 or -1 to clear? Pydantic handles null
             user.kindergarten_id = user_data.kindergarten_id

    db.commit()
    db.refresh(user)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="USER_UPDATED",
        entity_type="User",
        entity_id=user.id,
        sensitivity_level=3
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value
    }

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    request: Request,
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete user (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "delete_user", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Admin cannot delete other admin users
    if user.role == models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "delete_user", "Cannot delete admin users", request)
        raise HTTPException(status_code=403, detail="Cannot delete admin users")

    db.delete(user)
    db.commit()
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="USER_DELETED",
        entity_type="User",
        entity_id=user_id,
        sensitivity_level=3
    )
    return None


# Password Reset Endpoints
class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
    admin_password: str = Field(..., min_length=8)

@router.post("/users/{user_id}/admin-reset-password")
@limiter.limit("5/minute")
def admin_reset_password(
    request: Request,
    user_id: int,
    reset_data: AdminPasswordReset,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin forces password reset for a user"""
    if current_user.role != models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "admin_reset_password", "Not authorized", request)
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Admin cannot reset other admin users' passwords
    if user.role == models.UserRole.ADMIN:
        _log_access_denied(db, current_user, "admin_reset_password", "Cannot reset admin passwords", request)
        raise HTTPException(status_code=403, detail="Cannot reset admin passwords")

    from auth import verify_password, change_user_password
    ip_address = request.client.host if request.client else None
    if not verify_password(reset_data.admin_password, current_user.hashed_password):
        validators.log_audit_action(
            db=db,
            user_id=current_user.id,
            action="ADMIN_PASSWORD_RESET_FAILED",
            entity_type="User",
            entity_id=user.id,
            details="Admin password verification failed",
            ip_address=ip_address,
            sensitivity_level=3
        )
        raise HTTPException(status_code=401, detail="Admin password verification failed")

    from auth import change_user_password
    change_user_password(db, user, reset_data.new_password)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="ADMIN_PASSWORD_RESET",
        entity_type="User",
        entity_id=user.id,
        details="Admin password reset",
        ip_address=ip_address,
        sensitivity_level=3
    )

    return {"message": "Password reset successfully"}

@router.post("/users/request-password-reset")
@limiter.limit("5/hour")
def request_password_reset(
    request: Request,
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset token (for self-service)"""
    user = db.query(models.User).filter(models.User.email == reset_request.email).first()
    # Always return the same message — never reveal whether email exists
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}

    token = issue_password_reset_token(db, user)
    base_url = str(request.base_url).rstrip("/")
    delivered = deliver_password_reset_email(base_url, user, token)
    if not delivered:
        logger.warning(
            "PASSWORD_RESET_UNDELIVERED user_id=%s: token issued but email not sent "
            "(check SMTP config or prior CRITICAL log for delivery error)",
            user.id,
        )

    return {"message": "If the email exists, a reset link has been sent"}

@router.post("/users/reset-password")
@limiter.limit("10/hour")
def reset_password(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """Reset password using token"""

    token_record = resolve_valid_token(db, reset_data.token)

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    from auth import change_user_password
    try:
        change_user_password(db, token_record.user, reset_data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token_record.used = True
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=token_record.user.id,
        action="PASSWORD_RESET",
        entity_type="User",
        entity_id=token_record.user.id,
        sensitivity_level=2
    )

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
    db: Session = Depends(get_db)
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
    admin_users = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids),
        models.User.role == models.UserRole.ADMIN
    ).all()

    if admin_users:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot update admin accounts: {', '.join([u.username for u in admin_users])}"
        )

    # Update only non-admin users
    updated_count = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids),
        models.User.role != models.UserRole.ADMIN
    ).update({"status": bulk_data.new_status}, synchronize_session=False)

    db.commit()

    # Log audit action
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="BULK_STATUS_UPDATE",
        entity_type="User",
        entity_id=None,
        details=f"Updated {updated_count} users to status {bulk_data.new_status.value}",
        sensitivity_level=3
    )

    return {"message": f"Updated {updated_count} users successfully"}

@router.post("/users/bulk-delete")
@limiter.limit(settings.RATE_LIMIT_BULK_DELETE)
def bulk_delete_users(
    request: Request,
    bulk_data: BulkDeleteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    admin_users = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids),
        models.User.role == models.UserRole.ADMIN
    ).all()

    if admin_users:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete admin accounts: {', '.join([u.username for u in admin_users])}"
        )

    # Delete users
    deleted_count = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids)
    ).delete()

    db.commit()

    # Log audit action
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="BULK_USER_DELETE",
        entity_type="User",
        entity_id=None,
        details=f"Deleted {deleted_count} users",
        sensitivity_level=3
    )

    return {"message": f"Deleted {deleted_count} users successfully"}

@router.post("/users/bulk-create")
@limiter.limit(settings.RATE_LIMIT_BULK_CREATE)
def bulk_create_users(
    request: Request,
    bulk_data: BulkCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
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

    for i, user_data in enumerate(bulk_data.users):
        try:
            # Cannot create admin users via bulk create
            if user_data.role == models.UserRole.ADMIN:
                errors.append({
                    "row": i + 1,
                    "field": "role",
                    "message": "Cannot create admin users"
                })
                continue

            # Check if username or email already exists
            existing = db.query(models.User).filter(
                or_(models.User.username == user_data.username,
                    models.User.email == user_data.email)
            ).first()

            if existing:
                errors.append({
                    "row": i + 1,
                    "field": "username/email",
                    "message": "Username or email already exists"
                })
                continue

            from auth import get_password_hash
            hashed_password = get_password_hash(user_data.password)

            new_user = models.User(
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed_password,
                role=user_data.role,
                kindergarten_id=user_data.kindergarten_id,
                status=models.UserStatus.ACTIVE
            )

            db.add(new_user)
            db.flush()  # Get the ID without committing

            created_users.append({
                "id": new_user.id,
                "username": new_user.username,
                "email": new_user.email,
                "role": new_user.role.value
            })

        except (SQLAlchemyError, TypeError, ValueError) as e:
            errors.append({
                "row": i + 1,
                "field": "unknown",
                "message": str(e)
            })

    db.commit()

    # Log audit action
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="BULK_USER_CREATE",
        entity_type="User",
        entity_id=None,
        details=f"Created {len(created_users)} users, {len(errors)} errors",
        sensitivity_level=3
    )

    return {
        "message": f"Created {len(created_users)} users successfully",
        "created_users": created_users,
        "errors": errors
    }
