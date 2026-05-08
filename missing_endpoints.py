"""
Missing Critical Endpoints - Implementation
Adds CRUD operations and complete workflows
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from datetime import date, datetime, timedelta
from typing import Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

import models
import validators
from config import settings
from database import get_db, engine as _db_engine
from dependencies import get_current_user


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


# ============================================================================
# User Profile Endpoints
# ============================================================================

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    status: str
    kindergarten_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class CurrentUserUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)


class CurrentPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.get("/users/me", response_model=UserResponse)
def get_current_user_info(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current authenticated user's information"""
    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        status=current_user.status.value,
        kindergarten_id=current_user.kindergarten_id,
        first_name=parent_profile.first_name if parent_profile else current_user.username,
        last_name=parent_profile.last_name if parent_profile else "",
        phone=parent_profile.phone_number if parent_profile else None,
        created_at=current_user.created_at
    )


@router.put("/users/me", response_model=UserResponse)
def update_current_user_info(
    update_data: CurrentUserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the current user's basic profile fields."""
    if update_data.email and update_data.email != current_user.email:
        existing = db.query(models.User).filter(
            models.User.email == update_data.email,
            models.User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already used")
        current_user.email = str(update_data.email)

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if parent_profile:
        if update_data.first_name is not None:
            parent_profile.first_name = update_data.first_name.strip()
        if update_data.last_name is not None:
            parent_profile.last_name = update_data.last_name.strip()
        if update_data.phone is not None:
            parent_profile.phone_number = update_data.phone.strip()
        parent_profile.updated_at = datetime.now()

    db.commit()
    db.refresh(current_user)

    return get_current_user_info(current_user=current_user, db=db)


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

    unread_messages = message_query.filter(
        or_(
            models.Message.recipient_id == current_user.id,
            models.Message.thread_type == models.MessageThreadType.BROADCAST
        ),
        models.Message.is_read == False
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

@router.get("/users")
def list_users(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    role: Optional[models.UserRole] = None,
    status: Optional[models.UserStatus] = None,
    kindergarten_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List users. Admins see all. Managers see only their kindergarten's staff."""
    query = db.query(models.User)

    if current_user.role == models.UserRole.ADMIN:
        # Admin can filter by any kindergarten_id
        if kindergarten_id:
            query = query.filter(models.User.kindergarten_id == kindergarten_id)
        # Prevent admins from seeing or filtering for other admin users
        query = query.filter(models.User.role != models.UserRole.ADMIN)
    elif current_user.role == models.UserRole.MANAGER:
        # Manager is restricted to their own kindergarten
        query = query.filter(models.User.kindergarten_id == current_user.kindergarten_id)
        # If they requested a specific kindergarten_id, it must match theirs (already filtered, but for clarity)
        if kindergarten_id and kindergarten_id != current_user.kindergarten_id:
             # Return empty? or just ignore?
             # Let's stricter:
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
        pass # Allowed all
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

@router.get("/users/{user_id}")
def get_user(
    request: Request,
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user details"""
    if current_user.role != models.UserRole.ADMIN:
        # Can view self
        if current_user.id != user_id:
             _log_access_denied(db, current_user, "get_user", "Non-admin access to other user", request)
             raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
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
    if current_user.role != models.UserRole.ADMIN:
        # User update self? Maybe restrict for now or allow only password
        if current_user.id != user_id:
            _log_access_denied(db, current_user, "update_user", "Non-admin update of other user", request)
            raise HTTPException(status_code=403, detail="Not authorized")
            
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
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
        
    # Check dependencies before deleting? typically cascade or strict.
    # We will hard delete for now as per instructions.
    
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

    from auth import get_password_hash, verify_password
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
    user.hashed_password = get_password_hash(reset_data.new_password)

    db.commit()

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
def request_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset token (for self-service)"""
    user = db.query(models.User).filter(models.User.email == reset_request.email).first()
    if not user:
        # Don't reveal if email exists or not for security
        return {"message": "If the email exists, a reset link has been sent"}

    # Generate secure token
    import secrets
    from datetime import datetime, timedelta

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)

    # Save token
    reset_token = models.PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at
    )

    db.add(reset_token)
    db.commit()

    # TODO: Send email with reset link
    # For now, just return the token (in production, this would be emailed)
    return {"message": "If the email exists, a reset link has been sent", "token": token}

@router.post("/users/reset-password")
def reset_password(
    reset_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """Reset password using token"""
    from datetime import datetime

    token_record = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == reset_data.token,
        models.PasswordResetToken.used == False,
        models.PasswordResetToken.expires_at > datetime.utcnow()
    ).first()

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    from auth import get_password_hash
    token_record.user.hashed_password = get_password_hash(reset_data.new_password)
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
    user_ids: List[int]
    new_status: models.UserStatus

class BulkDeleteRequest(BaseModel):
    user_ids: List[int]

class BulkCreateRequest(BaseModel):
    users: List[UserCreate]

@router.post("/users/bulk-status-update")
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

    # Update users
    updated_count = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids)
    ).update({"status": bulk_data.new_status})

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

    created_users = []
    errors = []

    for i, user_data in enumerate(bulk_data.users):
        try:
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

        except Exception as e:
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
        return validators.normalise_jordan_governorate(value)


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

@router.post("/kindergartens", status_code=status.HTTP_201_CREATED, response_model=KindergartenResponse)
def create_kindergarten(
    kindergarten_data: KindergartenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new kindergarten (Admin only)"""

    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can create kindergartens")

    duplicate_field = detect_kindergarten_duplicate(db, kindergarten_data)
    if duplicate_field:
        raise HTTPException(
            status_code=400,
            detail=DUPLICATE_ERROR_MAP.get(duplicate_field, {"code": "error_duplicate_entry", "message": "Duplicate record found."})
        )
        raise HTTPException(status_code=400, detail="روضة بنفس الاسم أو رقم الهاتف أو البريد الإلكتروني موجودة بالفعل")

    kindergarten = models.Kindergarten(
        **kindergarten_data.model_dump(),
        status=models.KindergartenStatus.DRAFT
    )

    db.add(kindergarten)
    db.commit()
    db.refresh(kindergarten)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_CREATED",
        entity_type="Kindergarten",
        entity_id=kindergarten.id,
        sensitivity_level=2
    )

    return kindergarten


@router.get("/kindergartens")
def list_kindergartens(
    status: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List kindergartens with filtering"""
    query = db.query(models.Kindergarten)

    if status:
        query = query.filter(models.Kindergarten.status == models.KindergartenStatus(status))
    if governorate:
        query = query.filter(models.Kindergarten.governorate == governorate)
    if city:
        query = query.filter(models.Kindergarten.city == city)
    if phone:
        query = query.filter(models.Kindergarten.contact_phone.ilike(f"%{phone}%"))
    if name:
        query = query.filter(
            or_(
                models.Kindergarten.name_ar.ilike(f"%{name}%"),
                models.Kindergarten.name_en.ilike(f"%{name}%")
            )
        )

    # For non-admins, only show active kindergartens unless explicitly requested
    if current_user.role != models.UserRole.ADMIN and not include_inactive:
        query = query.filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE)

    kindergartens = query.offset(skip).limit(limit).all()
    total = query.count()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "kindergartens": kindergartens
    }


@router.get("/kindergartens/{kindergarten_id}")
def get_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get kindergarten details"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    return kindergarten


@router.put("/kindergartens/{kindergarten_id}")
def update_kindergarten(
    kindergarten_id: int,
    kindergarten_data: KindergartenCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update kindergarten (Admin or Manager)"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    # Check permissions
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kindergarten_id:
            raise HTTPException(status_code=403, detail="Can only update own kindergarten")
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    duplicate_field = detect_kindergarten_duplicate(db, kindergarten_data, exclude_id=kindergarten_id)
    if duplicate_field:
        raise HTTPException(
            status_code=400,
            detail=DUPLICATE_ERROR_MAP.get(duplicate_field, {"code": "error_duplicate_entry", "message": "Duplicate record found."})
        )

    for field, value in kindergarten_data.model_dump().items():
        setattr(kindergarten, field, value)

    db.commit()
    db.refresh(kindergarten)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_UPDATED",
        entity_type="Kindergarten",
        entity_id=kindergarten.id,
        sensitivity_level=2
    )

    return kindergarten


@router.delete("/kindergartens/{kindergarten_id}")
def delete_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete or archive kindergarten based on dependencies"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="الروضة غير موجودة")

    # Check permissions
    if current_user.role != models.UserRole.ADMIN:
        if current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id == kindergarten_id:
            # Managers can archive their own kindergarten
            pass
        else:
            raise HTTPException(status_code=403, detail="غير مصرح لك بحذف هذه الروضة")

    # Check for dependent records
    active_children = db.query(models.Child).filter(models.Child.kindergarten_id == kindergarten_id).count()
    active_classes = db.query(models.Class).filter(
        models.Class.kindergarten_id == kindergarten_id,
        models.Class.is_active == True
    ).count()
    active_staff = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE
    ).count()

    has_dependencies = active_children > 0 or active_classes > 0 or active_staff > 0

    if has_dependencies:
        if current_user.role != models.UserRole.ADMIN:
            raise HTTPException(
                status_code=409,
                detail="لا يمكن حذف الروضة لأنها تحتوي على بيانات نشطة. يرجى أرشفتها بدلاً من ذلك."
            )
        # Admin can force archive even with dependencies
        kindergarten.status = models.KindergartenStatus.INACTIVE
        action = "archived"
        message = "تم أرشفة الروضة بنجاح"
        audit_action = "KINDERGARTEN_ARCHIVED"
    else:
        # No dependencies - allow hard delete
        db.delete(kindergarten)
        action = "deleted"
        message = "تم حذف الروضة نهائياً"
        audit_action = "KINDERGARTEN_DELETED"

    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=audit_action,
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        details=f"Action: {action}, Dependencies: children={active_children}, classes={active_classes}, staff={active_staff}",
        sensitivity_level=3
    )

    return {
        "action": action,
        "message": message,
        "kindergarten_id": kindergarten_id
    }


@router.post("/kindergartens/{kindergarten_id}/archive")
def archive_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive kindergarten (soft delete)"""
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="الروضة غير موجودة")

    # Check permissions
    if current_user.role != models.UserRole.ADMIN:
        if current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id == kindergarten_id:
            # Managers can archive their own kindergarten
            pass
        else:
            raise HTTPException(status_code=403, detail="غير مصرح لك بأرشفة هذه الروضة")

    if kindergarten.status == models.KindergartenStatus.INACTIVE:
        raise HTTPException(status_code=400, detail="الروضة مأرشفة بالفعل")

    kindergarten.status = models.KindergartenStatus.INACTIVE
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_ARCHIVED",
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        sensitivity_level=2
    )

    return {
        "action": "archived",
        "message": "تم أرشفة الروضة بنجاح",
        "kindergarten_id": kindergarten_id
    }


@router.post("/kindergartens/{kindergarten_id}/restore")
def restore_kindergarten(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore archived kindergarten"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="فقط المدير يمكنه استعادة الروضات المأرشفة")

    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kindergarten_id
    ).first()

    if not kindergarten:
        raise HTTPException(status_code=404, detail="الروضة غير موجودة")

    if kindergarten.status != models.KindergartenStatus.INACTIVE:
        raise HTTPException(status_code=400, detail="الروضة غير مأرشفة")

    kindergarten.status = models.KindergartenStatus.ACTIVE
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_RESTORED",
        entity_type="Kindergarten",
        entity_id=kindergarten_id,
        sensitivity_level=2
    )

    return {
        "action": "restored",
        "message": "تم استعادة الروضة بنجاح",
        "kindergarten_id": kindergarten_id
    }


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

@router.get("/kindergartens/{kindergarten_id}/services", response_model=List[KindergartenServiceResponse])
def list_kindergarten_services(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all services/facilities for a kindergarten"""
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    services = db.query(models.KindergartenService).filter(models.KindergartenService.kindergarten_id == kindergarten_id).all()
    return services

@router.post("/kindergartens/{kindergarten_id}/services", status_code=status.HTTP_201_CREATED, response_model=KindergartenServiceResponse)
def create_kindergarten_service(
    kindergarten_id: int,
    service_data: KindergartenServiceCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new service/facility for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = models.KindergartenService(
        kindergarten_id=kindergarten_id,
        service_name=service_data.service_name,
        description=service_data.description,
        enabled_flag=service_data.enabled_flag if service_data.enabled_flag is not None else True
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_SERVICE_CREATED",
        entity_type="KindergartenService",
        entity_id=service.id,
        sensitivity_level=2
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=201, content=KindergartenServiceResponse.model_validate(service).model_dump())

@router.put("/kindergartens/{kindergarten_id}/services/{service_id}", response_model=KindergartenServiceResponse)
def update_kindergarten_service(
    kindergarten_id: int,
    service_id: int,
    service_data: KindergartenServiceUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a service/facility for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = db.query(models.KindergartenService).filter(
        models.KindergartenService.id == service_id,
        models.KindergartenService.kindergarten_id == kindergarten_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in service_data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_SERVICE_UPDATED",
        entity_type="KindergartenService",
        entity_id=service.id,
        sensitivity_level=2
    )
    return service

@router.delete("/kindergartens/{kindergarten_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kindergarten_service(
    kindergarten_id: int,
    service_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a service/facility from a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    service = db.query(models.KindergartenService).filter(
        models.KindergartenService.id == service_id,
        models.KindergartenService.kindergarten_id == kindergarten_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="KINDERGARTEN_SERVICE_DELETED",
        entity_type="KindergartenService",
        entity_id=service_id,
        sensitivity_level=2
    )
    return Response(status_code=204)

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

@router.post("/classes", status_code=status.HTTP_201_CREATED, response_model=ClassResponse)
def create_class(
    class_data: ClassCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new class (Manager or Admin)"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, class_data.kindergarten_id)

    if class_data.max_age_months < class_data.min_age_months:
        raise HTTPException(status_code=400, detail="Max age must be >= min age")

    class_obj = models.Class(
        **class_data.model_dump(),
        is_active=True
    )

    db.add(class_obj)
    db.commit()
    db.refresh(class_obj)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_CREATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return class_obj


@router.get("/classes")
def list_classes(
    kindergarten_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List classes with filtering and current supervisor info"""
    query = db.query(models.Class)

    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Class.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.Class.kindergarten_id == kindergarten_id)

    if is_active is not None:
        query = query.filter(models.Class.is_active == is_active)

    classes_orm = query.all()
    
    result = []
    today = date.today()
    
    for c in classes_orm:
        # Get active primary supervisor
        current_supervisor = None
        current_primary_assignment = db.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.class_id == c.id,
            models.SupervisorAssignment.is_primary == True,
            models.SupervisorAssignment.start_date <= today,
            (models.SupervisorAssignment.end_date == None) | (models.SupervisorAssignment.end_date >= today)
        ).first()
        
        if current_primary_assignment and current_primary_assignment.supervisor:
            s_user = current_primary_assignment.supervisor
            current_supervisor = {
                "id": s_user.id,
                "name": s_user.username  # User model uses username, not first/last name
            }
            
        c_dict = {
            "id": c.id,
            "name_ar": c.name_ar,
            "name_en": c.name_en,
            "min_age_months": c.min_age_months,
            "max_age_months": c.max_age_months,
            "capacity_total": c.capacity_total,
            "is_active": c.is_active,
            "current_supervisor": current_supervisor
        }
        result.append(c_dict)

    return {"classes": result}


@router.get("/classes/{class_id}/capacity-status")
def get_class_capacity_status(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current enrollment vs capacity for a class"""
    class_obj = db.query(models.Class).filter(
        models.Class.id == class_id
    ).first()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Count active enrollments assigned to this class
    enrolled_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    return {
        "class_id": class_id,
        "class_name": class_obj.name_en or class_obj.name_ar,
        "capacity_total": class_obj.capacity_total,
        "enrolled_count": enrolled_count,
        "available_spots": class_obj.capacity_total - enrolled_count,
        "utilization_percent": round((enrolled_count / class_obj.capacity_total) * 100, 2) if class_obj.capacity_total > 0 else 0
    }


@router.get("/classes/{class_id}", response_model=ClassResponse)
def get_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific class by ID"""
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Check permissions - admin can see all, others only their kindergarten's classes
    if current_user.role != models.UserRole.ADMIN:
        if class_obj.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return class_obj


@router.put("/classes/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: int,
    class_data: ClassUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update class details (Manager or Admin)"""
    validators.validate_manager_role(current_user)

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    # Validate age range if provided
    if hasattr(class_data, 'max_age_months') and hasattr(class_data, 'min_age_months'):
        if class_data.max_age_months is not None and class_data.min_age_months is not None:
            if class_data.max_age_months < class_data.min_age_months:
                raise HTTPException(status_code=400, detail="Max age must be >= min age")

    # Update fields
    update_data = class_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(class_obj, field, value)

    db.commit()
    db.refresh(class_obj)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_UPDATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return class_obj


@router.put("/classes/{class_id}/deactivate")
def deactivate_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate class (soft delete - Manager or Admin)"""
    validators.validate_manager_role(current_user)

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    if not class_obj.is_active:
        raise HTTPException(status_code=400, detail="Class is already inactive")

    # Check if class has active enrollments
    active_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).count()

    if active_enrollments > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot deactivate class with {active_enrollments} active enrollment(s). Move children to other classes first."
        )

    class_obj.is_active = False
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_DEACTIVATED",
        entity_type="Class",
        entity_id=class_obj.id,
        sensitivity_level=2
    )

    return {"message": "Class deactivated successfully", "class_id": class_id}


@router.delete("/classes/{class_id}")
def delete_class(
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Hard delete class (Admin only, when no dependencies exist)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required for permanent deletion")

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Check for any dependencies
    enrollment_count = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id
    ).count()

    supervisor_assignment_count = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.class_id == class_id
    ).count()

    if enrollment_count > 0 or supervisor_assignment_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete class with existing dependencies: {enrollment_count} enrollment(s), {supervisor_assignment_count} supervisor assignment(s)"
        )

    db.delete(class_obj)
    db.commit()

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CLASS_DELETED",
        entity_type="Class",
        entity_id=class_id,
        sensitivity_level=3
    )

    return {"message": "Class permanently deleted", "class_id": class_id}


# ============================================================================
# Class Assignment Endpoint
# ============================================================================

@router.post("/enrollments/{enrollment_id}/assign-class")
def assign_child_to_class(
    enrollment_id: int,
    class_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign an active enrollment to a specific class (Manager only)"""
    validators.validate_manager_role(current_user)

    # Get enrollment
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()

    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Validate enrollment is active
    if enrollment.status != models.EnrollmentStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Can only assign active enrollments")

    # Validate kindergarten scope
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)

    # Get class
    class_obj = db.query(models.Class).filter(
        models.Class.id == class_id
    ).first()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Validate class belongs to same kindergarten
    if class_obj.kindergarten_id != enrollment.kindergarten_id:
        raise HTTPException(status_code=400, detail="Class must belong to same kindergarten")

    # Validate age band eligibility
    child = enrollment.child
    try:
        validators.validate_age_band_eligibility(
            child.date_of_birth,
            class_obj.min_age_months,
            class_obj.max_age_months
        )
    except validators.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Acquire a row-level lock on the class record before counting seats.
    # This eliminates the TOCTOU race on PostgreSQL where two concurrent
    # requests both read the count before either writes, causing over-enrollment.
    # SQLite serialises at the connection level so no explicit lock is needed.
    if _db_engine.dialect.name == "postgresql":
        db.execute(
            text("SELECT id FROM classes WHERE id = :id FOR UPDATE"),
            {"id": class_id},
        )

    # Check capacity
    enrolled_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    if enrolled_count >= class_obj.capacity_total:
        raise HTTPException(status_code=400, detail="Class is at full capacity")

    # Assign to class
    enrollment.class_id = class_id
    enrollment.class_assignment_date = date.today()

    db.commit()
    db.refresh(enrollment)

    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="CHILD_ASSIGNED_TO_CLASS",
        entity_type="EnrollmentApplication",
        entity_id=enrollment.id,
        details=f"Child {child.first_name} {child.last_name} assigned to class {class_obj.name_en}",
        sensitivity_level=2
    )

    return {
        "enrollment_id": enrollment.id,
        "child_id": enrollment.child_id,
        "class_id": class_id,
        "class_name": class_obj.name_en or class_obj.name_ar,
        "assignment_date": enrollment.class_assignment_date
    }


@router.get("/enrollments")
def list_enrollments(
    status: Optional[str] = None,
    kindergarten_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List enrollment applications with filtering"""
    query = db.query(
        models.EnrollmentApplication,
        models.Child,
        models.ParentProfile,
        models.Kindergarten
    ).join(
        models.Child, models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.ParentProfile, models.Child.parent_id == models.ParentProfile.id
    ).join(
        models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    )

    # Filter by user role and scope
    if current_user.role == models.UserRole.ADMIN:
        # Admin can see all, but can filter by kindergarten
        if kindergarten_id:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
    elif current_user.role == models.UserRole.MANAGER:
        # Manager can only see enrollments for their kindergarten
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    elif current_user.role == models.UserRole.SUPERVISOR:
        # Supervisor can only see enrollments for their kindergarten
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view enrollments")

    # Filter by status if provided
    if status:
        query = query.filter(models.EnrollmentApplication.status == status)

    # Get total count
    total = query.count()

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Format results
    enrollments = []
    for enrollment, child, parent, kg in results:
        enrollments.append({
            "id": enrollment.id,
            "child_name": f"{child.first_name} {child.last_name}",
            "parent_name": f"{parent.first_name} {parent.last_name}",
            "kindergarten_name": kg.name_ar or kg.name_en,
            "status": enrollment.status.value if hasattr(enrollment.status, 'value') else str(enrollment.status),
            "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
            "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None,
            "kindergarten_id": enrollment.kindergarten_id,
            "child_id": enrollment.child_id
        })

    return {
        "enrollments": enrollments,
        "total": total,
        "skip": skip,
        "limit": limit
    }


# ============================================================================
# Manager Dashboard
# ============================================================================

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
        if days < 0:
            msg  = f"ترخيص روضة «{kg.name_ar}» منتهٍ منذ {abs(days)} يوم"
            prio = "critical"
        else:
            msg  = f"ترخيص روضة «{kg.name_ar}» ينتهي خلال {days} يوم"
            prio = "high"
        alerts.append({
            "type": "license_expiry",
            "message": msg,
            "priority": prio,
            "kindergarten_id": kg.id
        })

    # High pending applications
    if pending_applications > 10:
        alerts.append({
            "type": "high_pending_applications",
            "message": f"يوجد {pending_applications} طلب تسجيل معلق يتطلب المراجعة",
            "priority": "high"
        })

    # Low attendance rate alert (if attendance < 70% of enrollments)
    if total_enrollments > 0:
        attendance_rate = (attendance_today / total_enrollments) * 100
        if attendance_rate < 70:
            alerts.append({
                "type": "low_attendance",
                "message": f"نسبة الحضور اليوم {attendance_rate:.1f}% فقط (أقل من الحد المطلوب 70%)",
                "priority": "medium"
            })

    # Recent high incident count
    if recent_incidents > 5:
        alerts.append({
            "type": "high_incidents",
            "message": f"تم تسجيل {recent_incidents} حادثة في الأسبوع الأخير",
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


# ============================================================================
# Parent Dashboard
# ============================================================================

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
            "age_months": (date.today() - child.date_of_birth).days // 30 if child.date_of_birth else None,
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


@router.get("/parent/children")
def get_parent_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of parent's children"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()

    if not parent_profile:
        return {"children": []}

    children = db.query(models.Child).filter(
        models.Child.parent_id == parent_profile.id
    ).all()

    return {
        "children": [
            {
                "id": c.id,
                "full_name_ar": f"{c.first_name} {c.last_name}",
                "name": f"{c.first_name} {c.last_name}",
                "first_name": c.first_name,
                "last_name": c.last_name,
            }
            for c in children
        ]
    }


@router.get("/parent/enrollments")
def get_parent_enrollments(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get enrollment applications for the current parent."""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        return {"enrollments": []}

    rows = db.query(
        models.EnrollmentApplication,
        models.Child,
        models.Kindergarten
    ).join(
        models.Child, models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    ).filter(
        models.Child.parent_id == parent_profile.id
    ).order_by(models.EnrollmentApplication.created_at.desc()).all()

    return {
        "enrollments": [
            {
                "id": enrollment.id,
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_id": kg.id,
                "kindergarten_name": kg.name_ar or kg.name_en,
                "status": enrollment.status.value.lower(),
                "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
                "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None,
            }
            for enrollment, child, kg in rows
        ]
    }


@router.get("/parent/attendance")
def get_parent_attendance(
    year: int,
    month: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get monthly attendance/approved absence records for current parent's children."""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parent access only")
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        return {"records": []}

    child_ids = [
        c.id for c in db.query(models.Child.id).filter(
            models.Child.parent_id == parent_profile.id
        ).all()
    ]
    if not child_ids:
        return {"records": []}

    start_date = date(year, month, 1)
    end_date = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)

    attendance = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id.in_(child_ids),
        models.AttendanceLog.date >= start_date,
        models.AttendanceLog.date <= end_date
    ).order_by(models.AttendanceLog.date.desc()).all()

    records = [
        {
            "date": row.date.isoformat(),
            "child_id": row.child_id,
            "status": "present",
            "notes": row.check_in_at.strftime("%H:%M") if row.check_in_at else None,
        }
        for row in attendance
    ]

    absence_rows = db.execute(
        text(
            "SELECT child_id, start_date, end_date, reason, status FROM absence_requests "
            "WHERE parent_id = :parent_id AND status = 'APPROVED' "
            "AND start_date <= :end_date AND end_date >= :start_date"
        ),
        {"parent_id": parent_profile.id, "start_date": start_date, "end_date": end_date}
    ).mappings().all()
    for row in absence_rows:
        absence_start = _coerce_date(row["start_date"])
        absence_end = _coerce_date(row["end_date"])
        current = max(absence_start, start_date)
        last = min(absence_end, end_date)
        while current <= last:
            records.append({
                "date": current.isoformat(),
                "child_id": row["child_id"],
                "status": "excused",
                "notes": row["reason"],
            })
            current += timedelta(days=1)

    records.sort(key=lambda item: item["date"], reverse=True)
    return {"records": records}


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
        # Parents only see approved reports for their children
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


@router.post("/tasks", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
def create_task(
    task_data: TaskCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new task"""
    # Validate role - only admin, manager, supervisor can create tasks
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized to create tasks")
    
    # Admin must specify kindergarten, others use their assigned one
    if current_user.role == models.UserRole.ADMIN:
        # For admin, default to first kindergarten if none specified
        kindergarten = db.query(models.Kindergarten).first()
        if not kindergarten:
            raise HTTPException(status_code=400, detail="No kindergarten available")
        kindergarten_id = kindergarten.id
    else:
        if not current_user.kindergarten_id:
            raise HTTPException(status_code=400, detail="User not assigned to a kindergarten")
        kindergarten_id = current_user.kindergarten_id
    
    # Validate priority
    priority_str = task_data.priority.upper() if task_data.priority else "MEDIUM"
    try:
        priority = models.TaskPriority(priority_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}. Valid values: LOW, MEDIUM, HIGH, URGENT")
    
    # Create task
    task = models.Task(
        kindergarten_id=kindergarten_id,
        title=task_data.title,
        description=task_data.description,
        priority=priority,
        status=models.TaskStatus.PENDING,
        assigned_to=task_data.assigned_to,
        created_by=current_user.id,
        due_date=task_data.due_date
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.get("/tasks", response_model=List[TaskResponse])
def get_tasks(
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    assigned_to_me: bool = False,
    created_by_me: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tasks with optional filters"""
    query = db.query(models.Task)
    
    # Filter by kindergarten for non-admin users
    if current_user.role != models.UserRole.ADMIN and current_user.kindergarten_id:
        query = query.filter(models.Task.kindergarten_id == current_user.kindergarten_id)
    
    if status_filter:
        try:
            status_enum = models.TaskStatus(status_filter.upper())
            query = query.filter(models.Task.status == status_enum)
        except ValueError:
            pass
    
    if priority_filter:
        try:
            priority_enum = models.TaskPriority(priority_filter.upper())
            query = query.filter(models.Task.priority == priority_enum)
        except ValueError:
            pass
    
    if assigned_to_me:
        query = query.filter(models.Task.assigned_to == current_user.id)
    
    if created_by_me:
        query = query.filter(models.Task.created_by == current_user.id)
    
    tasks = query.order_by(models.Task.created_at.desc()).all()
    
    return [
        TaskResponse(
            id=t.id,
            kindergarten_id=t.kindergarten_id,
            title=t.title,
            description=t.description,
            status=t.status.value,
            priority=t.priority.value,
            assigned_to=t.assigned_to,
            created_by=t.created_by,
            due_date=t.due_date,
            completed_at=t.completed_at,
            created_at=t.created_at
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific task by ID"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing task"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Update fields
    if task_data.title is not None:
        task.title = task_data.title
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.status is not None:
        try:
            new_status = models.TaskStatus(task_data.status.upper())
            task.status = new_status
            if new_status == models.TaskStatus.COMPLETED:
                task.completed_at = datetime.now()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {task_data.status}")
    if task_data.priority is not None:
        try:
            task.priority = models.TaskPriority(task_data.priority.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}")
    if task_data.assigned_to is not None:
        task.assigned_to = task_data.assigned_to
    if task_data.due_date is not None:
        task.due_date = task_data.due_date
    
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.post("/tasks/{task_id}/toggle", response_model=TaskResponse)
def toggle_task_status(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle task between PENDING and COMPLETED"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Toggle status
    if task.status == models.TaskStatus.COMPLETED:
        task.status = models.TaskStatus.PENDING
        task.completed_at = None
    else:
        task.status = models.TaskStatus.COMPLETED
        task.completed_at = datetime.now()
    
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a task"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access - only creator or admin can delete
    if current_user.role != models.UserRole.ADMIN:
        if task.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Only task creator or admin can delete")
    
    db.delete(task)
    db.commit()
    
    return None


# ============================================================================
# Parent Registration Endpoint
# ============================================================================

class ParentRegistrationRequest(BaseModel):
    first_name: str
    second_name: Optional[str] = None
    last_name: str
    first_name_en: Optional[str] = None
    last_name_en: Optional[str] = None
    phone_number: str
    gender: str
    nationality: str
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    home_governorate: str
    home_city: str
    home_area: str
    home_address_line: str
    correspondence_preference: Optional[bool] = True
    email: str
    password: str

    @field_validator("home_governorate")
    def validate_home_governorate(cls, value):
        if not validators.validate_jordan_governorate(value):
            raise ValueError(f"Invalid governorate: {value}. Must be one of: {', '.join(settings.JORDAN_GOVERNORATES)}")
        return validators.normalise_jordan_governorate(value)


@router.post("/register/parent", status_code=status.HTTP_201_CREATED)
def register_parent(
    registration_data: ParentRegistrationRequest,
    db: Session = Depends(get_db)
):
    """Register a new parent user with profile"""
    from auth import get_password_hash

    # Check if email already exists
    existing_user = db.query(models.User).filter(
        models.User.email == registration_data.email
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل مسبقاً")

    # Validate identification: either national_id or passport_number required
    if not registration_data.national_id and not registration_data.passport_number:
        raise HTTPException(
            status_code=400,
            detail="يجب إدخال الرقم الوطني أو رقم جواز السفر"
        )

    # Validate password strength (minimum 8 characters)
    password = registration_data.password
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")

    # Create user
    user = models.User(
        username=registration_data.email,
        email=registration_data.email,
        hashed_password=get_password_hash(password),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create parent profile
    parent_profile = models.ParentProfile(
        user_id=user.id,
        first_name=registration_data.first_name,
        second_name=registration_data.second_name,
        last_name=registration_data.last_name,
        first_name_en=registration_data.first_name_en,
        last_name_en=registration_data.last_name_en,
        phone_number=registration_data.phone_number,
        gender=models.Gender(registration_data.gender.upper()),
        nationality=registration_data.nationality,
        national_id=registration_data.national_id,
        passport_number=registration_data.passport_number,
        home_governorate=registration_data.home_governorate,
        home_city=registration_data.home_city,
        home_area=registration_data.home_area,
        home_address_line=registration_data.home_address_line,
        correspondence_preference=registration_data.correspondence_preference or True
    )
    db.add(parent_profile)
    db.commit()

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value.lower(),
        "first_name": registration_data.first_name,
        "last_name": registration_data.last_name
    }


# ============================================================================
# Enrollment Endpoints
# ============================================================================

class EnrollmentApplicationRequest(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: str  # ISO format date
    father_name: str
    mother_first_name: str
    mother_last_name: str
    mother_nationality: str
    mother_national_id: str
    kindergarten_id: int


@router.post("/enrollment/apply", status_code=status.HTTP_201_CREATED)
def create_enrollment_application(
    enrollment_data: EnrollmentApplicationRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new enrollment application (Parent only)"""
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only parents can apply for enrollment")
    
    # Get parent profile
    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        raise HTTPException(status_code=400, detail="Parent profile not found")
    
    # Validate kindergarten exists
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == enrollment_data.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")
    
    # Validate child age (70 days to 56 months)
    dob = date.fromisoformat(enrollment_data.date_of_birth)
    today = date.today()
    age_days = (today - dob).days
    age_months = age_days / 30.44  # Average days per month
    
    if age_days < 70:
        raise HTTPException(status_code=400, detail="Child must be at least 70 days old")
    if age_months > 56:
        raise HTTPException(status_code=400, detail="Child must be under 56 months old")
    
    # Create child record
    child = models.Child(
        parent_id=parent_profile.id,
        first_name=enrollment_data.first_name,
        last_name=enrollment_data.last_name,
        gender=models.Gender(enrollment_data.gender.upper()),
        date_of_birth=dob,
        father_name=enrollment_data.father_name,
        mother_first_name=enrollment_data.mother_first_name,
        mother_last_name=enrollment_data.mother_last_name,
        mother_nationality=enrollment_data.mother_nationality,
        mother_national_id=enrollment_data.mother_national_id
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    
    # Create enrollment application
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=enrollment_data.kindergarten_id,
        status=models.EnrollmentStatus.DRAFT,
        source="online"
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    
    return {
        "id": enrollment.id,
        "child_id": child.id,
        "kindergarten_id": enrollment.kindergarten_id,
        "status": enrollment.status.value.lower()
    }


@router.post("/enrollment/{enrollment_id}/submit")
def submit_enrollment(
    enrollment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit enrollment application for review"""
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    
    if enrollment.status != models.EnrollmentStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft applications can be submitted")
    
    # Verify parent owns this enrollment
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        child = enrollment.child
        if child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Not authorized to submit this enrollment")
    
    enrollment.status = models.EnrollmentStatus.SUBMITTED
    enrollment.submitted_at = datetime.now()
    db.commit()
    db.refresh(enrollment)
    
    return {
        "id": enrollment.id,
        "status": enrollment.status.value.lower(),
        "submitted_at": enrollment.submitted_at.isoformat() if enrollment.submitted_at else None
    }


@router.post("/enrollment/{enrollment_id}/review")
def review_enrollment(
    enrollment_id: int,
    decision: str = Query(..., description="accept or reject"),
    reason: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Review and decide on enrollment application (Manager only)"""
    validators.validate_manager_role(current_user)
    
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    
    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)
    
    if enrollment.status != models.EnrollmentStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted applications can be reviewed")
    
    if decision == "accept":
        enrollment.status = models.EnrollmentStatus.ACTIVE
        enrollment.enrollment_start_date = date.today()
    elif decision == "reject":
        enrollment.status = models.EnrollmentStatus.REJECTED
        enrollment.status_reason = reason
    else:
        raise HTTPException(status_code=400, detail="Decision must be 'accept' or 'reject'")
    
    enrollment.decision_by = current_user.id
    enrollment.decision_at = datetime.now()
    db.commit()
    db.refresh(enrollment)
    
    return {
        "id": enrollment.id,
        "status": enrollment.status.value.lower(),
        "decision_at": enrollment.decision_at.isoformat() if enrollment.decision_at else None
    }


@router.post("/enrollments/{enrollment_id}/review")
def review_enrollment_plural_alias(
    enrollment_id: int,
    decision: Optional[str] = Query(default=None, description="accept or reject"),
    reason: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compatibility endpoint for frontend plural enrollment review path."""
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


@router.post("/attendance/check-in")
def check_in_child(
    child_id: int,
    method: str = Query(..., description="pin, qr, or manual"),
    dropped_by_name: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check in a child for attendance"""
    validators.validate_supervisor_role(current_user)
    
    # Verify child has active enrollment
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    
    if not active_enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")
    
    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)
    
    # Check if already checked in today (any record, even if checked out)
    today = date.today()
    existing_checkin = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today
    ).first()
    
    if existing_checkin:
        raise HTTPException(status_code=400, detail="Child already checked in today (one record per day allowed)")
    
    # Create attendance log
    attendance = models.AttendanceLog(
        child_id=child_id,
        date=today,
        check_in_at=datetime.now(),
        method=models.AttendanceMethod(method.upper()),
        dropped_by_name=dropped_by_name
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    
    return {
        "id": attendance.id,
        "child_id": attendance.child_id,
        "date": attendance.date.isoformat(),
        "check_in_at": attendance.check_in_at.isoformat() if attendance.check_in_at else None,
        "check_out_at": None,
        "dropped_by_name": attendance.dropped_by_name
    }


@router.post("/attendance/check-out")
def check_out_child(
    child_id: int,
    picked_by_name: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check out a child from attendance"""
    validators.validate_supervisor_role(current_user)
    
    # Find today's check-in without check-out
    today = date.today()
    attendance = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today,
        models.AttendanceLog.check_out_at.is_(None)
    ).first()
    
    if not attendance:
        raise HTTPException(status_code=400, detail="Child is not checked in today")
    
    attendance.check_out_at = datetime.now()
    attendance.picked_by_name = picked_by_name
    db.commit()
    db.refresh(attendance)
    
    return {
        "id": attendance.id,
        "child_id": attendance.child_id,
        "date": attendance.date.isoformat(),
        "check_in_at": attendance.check_in_at.isoformat() if attendance.check_in_at else None,
        "check_out_at": attendance.check_out_at.isoformat() if attendance.check_out_at else None,
        "picked_by_name": attendance.picked_by_name
    }


@router.post("/attendance")
def mark_attendance(
    attendance_data: AttendanceMarkRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compatibility endpoint for simple attendance actions from the UI."""
    status_value = attendance_data.status.upper()
    if status_value in {"PRESENT", "LATE"}:
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

    today = date.today()
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


@router.get("/attendance/report", response_model=AttendanceReportResponse)
def get_attendance_report(
    request: AttendanceReportRequest = Depends(),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attendance report matrix for specified period"""
    # Authorization: Admin can see all, others only their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        validators.validate_supervisor_role(current_user)

    # Validate kindergarten exists and user has access
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == request.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    if current_user.role != models.UserRole.ADMIN:
        validators.validate_kindergarten_scope(current_user, request.kindergarten_id)

    # Determine date range
    if request.period_type == "range":
        try:
            start_date = date.fromisoformat(request.start_date)
            end_date = date.fromisoformat(request.end_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format")
    else:
        try:
            anchor_date = date.fromisoformat(request.date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format")

        if request.period_type == "day":
            start_date = end_date = anchor_date
        elif request.period_type == "week":
            start_date = anchor_date - timedelta(days=anchor_date.weekday())
            end_date = start_date + timedelta(days=6)
        elif request.period_type == "month":
            start_date = anchor_date.replace(day=1)
            if anchor_date.month == 12:
                end_date = anchor_date.replace(year=anchor_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = anchor_date.replace(month=anchor_date.month + 1, day=1) - timedelta(days=1)

    # Validate date range (max 62 days)
    if (end_date - start_date).days > 62:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 62 days")

    # Get target children
    children_query = db.query(models.Child).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.kindergarten_id == request.kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )

    if request.class_ids:
        # Validate classes belong to kindergarten
        valid_classes = db.query(models.Class.id).filter(
            models.Class.kindergarten_id == request.kindergarten_id,
            models.Class.id.in_(request.class_ids)
        ).all()
        valid_class_ids = [c[0] for c in valid_classes]
        if len(valid_class_ids) != len(request.class_ids):
            raise HTTPException(status_code=422, detail="Some class_ids do not belong to this kindergarten")

        children_query = children_query.filter(
            models.EnrollmentApplication.class_id.in_(valid_class_ids)
        )

    if request.child_ids:
        children_query = children_query.filter(models.Child.id.in_(request.child_ids))

    children = children_query.all()

    # Get attendance data efficiently
    attendance_data = db.query(
        models.AttendanceLog.child_id,
        models.AttendanceLog.date,
        models.AttendanceLog.check_in_at,
        models.AttendanceLog.check_out_at
    ).filter(
        models.AttendanceLog.child_id.in_([c.id for c in children]),
        models.AttendanceLog.date >= start_date,
        models.AttendanceLog.date <= end_date
    ).all()

    # Build matrix
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    matrix = {}
    totals = {"per_child": {}, "per_day": {}, "overall": {"present": 0, "absent": 0}}

    for child in children:
        child_id = child.id
        matrix[child_id] = {}
        totals["per_child"][child_id] = {"present": 0, "absent": 0}

        for date_str in dates:
            # Check if child was present on this date
            present = any(a.child_id == child_id and a.date.isoformat() == date_str for a in attendance_data)
            status = "present" if present else "absent"
            matrix[child_id][date_str] = {"status": status, "label": "حاضر" if present else "غائب"}

            if present:
                totals["per_child"][child_id]["present"] += 1
                totals["overall"]["present"] += 1
            else:
                totals["per_child"][child_id]["absent"] += 1
                totals["overall"]["absent"] += 1

    # Per day totals
    for date_str in dates:
        present_count = sum(1 for child_id in matrix if matrix[child_id][date_str]["status"] == "present")
        totals["per_day"][date_str] = present_count

    # Children info
    children_info = []
    for child in children:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()
        class_info = db.query(models.Class).filter(models.Class.id == enrollment.class_id).first() if enrollment else None

        children_info.append({
            "id": child.id,
            "name_ar": f"{child.first_name_ar} {child.last_name_ar}",
            "name_en": f"{child.first_name_en or ''} {child.last_name_en or ''}".strip(),
            "class_id": enrollment.class_id if enrollment else None,
            "class_name": class_info.name if class_info else None
        })

    # Chart data
    total_days = len(dates)
    total_children = len(children)
    attendance_rate = (totals["overall"]["present"] / (total_children * total_days)) * 100 if total_children * total_days > 0 else 0

    chart_data = {
        "breakdown_by_status": {
            "present": totals["overall"]["present"],
            "absent": totals["overall"]["absent"]
        },
        "trend_present_by_day": [{"date": d, "count": totals["per_day"][d]} for d in dates]
    }

    return AttendanceReportResponse(
        meta={
            "kindergarten": {
                "id": kindergarten.id,
                "name_ar": kindergarten.name_ar,
                "name_en": kindergarten.name_en,
                "governorate": kindergarten.governorate,
                "city": kindergarten.city,
                "area": kindergarten.area,
                "phone": kindergarten.contact_phone,
                "address": kindergarten.address_line
            },
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "period_type": request.period_type
        },
        dates=dates,
        children=children_info,
        matrix=matrix,
        totals={
            **totals,
            "summary": {
                "total_children": total_children,
                "total_school_days": total_days,
                "attendance_rate": round(attendance_rate, 2)
            }
        },
        chart_data=chart_data
    )


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


@router.get("/daily-reports")
def list_daily_reports(
    report_date: Optional[str] = Query(default=None, alias="date"),
    child_id: Optional[int] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List daily reports for the reports page."""
    query = db.query(models.DailyReport).join(models.Child)

    if report_date:
        try:
            query = query.filter(models.DailyReport.date == date.fromisoformat(report_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    if child_id:
        query = query.filter(models.DailyReport.child_id == child_id)

    if status_filter:
        normalized_status = status_filter.upper()
        try:
            query = query.filter(models.DailyReport.status == models.DailyReportStatus(normalized_status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid report status")

    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return {"reports": [], "summary": {"total": 0, "sent": 0, "attendance_rate": 0, "eating_rate": 0}}
        query = query.filter(
            models.Child.parent_id == parent_profile.id,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        )
    elif current_user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        if not current_user.kindergarten_id:
            return {"reports": [], "summary": {"total": 0, "sent": 0, "attendance_rate": 0, "eating_rate": 0}}
        query = query.join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.DailyReport.child_id
        ).filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)

    reports = query.order_by(models.DailyReport.date.desc(), models.DailyReport.id.desc()).all()

    report_items = []
    for report in reports:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == report.child_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).order_by(models.EnrollmentApplication.id.desc()).first()
        class_obj = enrollment.class_ if enrollment else None
        nap_minutes = report.nap_duration_minutes or _minutes_between(report.nap_start, report.nap_end)

        report_items.append({
            "id": report.id,
            "child_id": report.child_id,
            "child_name": f"{report.child.first_name} {report.child.last_name}",
            "class_name": (class_obj.name_ar or class_obj.name_en) if class_obj else None,
            "date": report.date.isoformat(),
            "status": report.status.value.lower(),
            "mood": "happy",
            "meal_rating": _meal_rating(report),
            "nap_minutes": nap_minutes,
            "bathroom_count": None,
            "notes": report.notes,
        })

    total = len(report_items)
    sent = sum(1 for report in reports if report.status in [models.DailyReportStatus.SUBMITTED, models.DailyReportStatus.APPROVED])
    eating_count = sum(1 for report in reports if _meal_rating(report) != "none")

    return {
        "reports": report_items,
        "summary": {
            "total": total,
            "sent": sent,
            "attendance_rate": 100 if total else 0,
            "eating_rate": round((eating_count / total) * 100, 1) if total else 0,
        }
    }


@router.post("/daily-reports/create")
def create_daily_report(
    report_data: DailyReportCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new daily report (Supervisor only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only supervisors can create daily reports")
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == report_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
        
    # Verify active enrollment and scope
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == report_data.child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    
    if not active_enrollment:
         raise HTTPException(status_code=400, detail="Child not active in any class")
         
    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)
    
    # Validate date
    report_date = date.fromisoformat(report_data.date)
    if report_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot create reports for future dates")
    
    report = models.DailyReport(
        child_id=report_data.child_id,
        date=report_date,
        status=models.DailyReportStatus.DRAFT,
        submitted_by=current_user.id,
        arrival_time=report_data.arrival_time,
        leave_time=report_data.leave_time,
        breakfast=report_data.breakfast,
        snack=report_data.snack,
        milk=report_data.milk,
        lunch=report_data.lunch,
        nap_start=report_data.nap_start,
        nap_end=report_data.nap_end,
        activities=report_data.activities,
        notes=report_data.notes
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "child_id": report.child_id,
        "date": report.date.isoformat(),
        "status": report.status.value.lower()
    }


@router.post("/daily-reports/{report_id}/submit")
def submit_daily_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit daily report for approval"""
    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")
    
    if report.status != models.DailyReportStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft reports can be submitted")
    
    report.status = models.DailyReportStatus.SUBMITTED
    report.submitted_at = datetime.now()
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None
    }


@router.post("/daily-reports/{report_id}/approve")
def approve_daily_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a daily report (Manager only)"""
    validators.validate_manager_role(current_user)
    
    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")
    
    if report.status != models.DailyReportStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted reports can be approved")
    
    report.status = models.DailyReportStatus.APPROVED
    report.approved_by = current_user.id
    report.approved_at = datetime.now()
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "approved_at": report.approved_at.isoformat() if report.approved_at else None
    }


@router.get("/daily-reports/child/{child_id}")
def get_child_daily_reports(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get daily reports for a child (parents only see approved reports)"""
    # Parents: enforce that the child belongs to them
    if current_user.role == models.UserRole.PARENT:
        child = db.query(models.Child).filter(models.Child.id == child_id).first()
        if not child or child.parent_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied to this child's reports")

    query = db.query(models.DailyReport).filter(models.DailyReport.child_id == child_id)

    # Parents only see approved reports
    if current_user.role == models.UserRole.PARENT:
        query = query.filter(models.DailyReport.status == models.DailyReportStatus.APPROVED)
    
    reports = query.order_by(models.DailyReport.date.desc()).all()
    
    return {
        "reports": [
            {
                "id": r.id,
                "date": r.date.isoformat(),
                "status": r.status.value,
                "arrival_time": r.arrival_time,
                "leave_time": r.leave_time,
                "activities": r.activities,
                "notes": r.notes
            }
            for r in reports
        ]
    }


# ============================================================================
# Incidents Endpoints
# ============================================================================

class IncidentCreateRequest(BaseModel):
    child_id: int
    kindergarten_id: Optional[int] = None
    type: str
    severity_level: str
    description: str
    occurred_at: str
    followup_required_flag: Optional[bool] = False


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
def create_incident_json(
    incident_data: IncidentCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create incident report with JSON body"""
    validators.validate_supervisor_role(current_user)
    
    # Use user's kindergarten if not provided
    kindergarten_id = incident_data.kindergarten_id or current_user.kindergarten_id
    if not kindergarten_id:
        raise HTTPException(status_code=400, detail="Kindergarten ID required")
    
    validators.validate_kindergarten_scope(current_user, kindergarten_id)

    # Verify child belongs to this kindergarten
    child_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == incident_data.child_id,
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()

    if not child_enrollment:
        # Check if child exists at all first to give better error
        child_exists = db.query(models.Child).filter(models.Child.id == incident_data.child_id).first()
        if not child_exists:
            raise HTTPException(status_code=404, detail="Child not found")
        raise HTTPException(status_code=403, detail="Child is not enrolled in this kindergarten")

    incident = models.Incident(
        child_id=incident_data.child_id,
        kindergarten_id=kindergarten_id,
        type=models.IncidentType(incident_data.type.upper()),
        severity_level=models.SeverityLevel(incident_data.severity_level.upper()),
        description=incident_data.description,
        occurred_at=datetime.fromisoformat(incident_data.occurred_at.replace('Z', '+00:00')),
        followup_required_flag=incident_data.followup_required_flag or False,
        notify_parent_at=datetime.now()
    )
    
    if incident.followup_required_flag:
        # Set 48 hour SLA
        incident.followup_sla_deadline = datetime.now() + timedelta(hours=48)
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    return {
        "id": incident.id,
        "child_id": incident.child_id,
        "kindergarten_id": incident.kindergarten_id,
        "type": incident.type.value,
        "severity_level": incident.severity_level.value,
        "followup_required_flag": incident.followup_required_flag
    }


@router.get("/incidents")
def list_incidents(
    child_id: Optional[int] = None,
    kindergarten_id: Optional[int] = None,
    severity: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List incidents with optional filtering"""
    query = db.query(models.Incident)
    
    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Incident.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.Incident.kindergarten_id == kindergarten_id)
    
    if child_id:
        query = query.filter(models.Incident.child_id == child_id)
    
    if severity:
        try:
            severity_enum = models.SeverityLevel(severity.upper())
            query = query.filter(models.Incident.severity_level == severity_enum)
        except ValueError:
            pass
    
    incidents = query.order_by(models.Incident.occurred_at.desc()).all()
    
    return [
        {
            "id": i.id,
            "child_id": i.child_id,
            "kindergarten_id": i.kindergarten_id,
            "type": i.type.value,
            "severity_level": i.severity_level.value,
            "description": i.description,
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
            "followup_required_flag": i.followup_required_flag
        }
        for i in incidents
    ]


@router.post("/incidents/create", status_code=status.HTTP_201_CREATED)
def create_incident(
    kindergarten_id: int,
    child_id: int,
    incident_type: str,
    severity_level: str,
    description: str,
    occurred_at: str,
    followup_required: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create incident report (Manager only)"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    incident = models.Incident(
        child_id=child_id,
        kindergarten_id=kindergarten_id,
        type=models.IncidentType(incident_type.upper()),
        severity_level=models.SeverityLevel(severity_level.upper()),
        description=description,
        occurred_at=datetime.fromisoformat(occurred_at),
        followup_required_flag=followup_required,
        notify_parent_at=datetime.now()
    )
    
    if followup_required:
        # Set 48 hour SLA
        incident.followup_sla_deadline = datetime.now() + timedelta(hours=48)
    
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    return {
        "id": incident.id,
        "type": incident.type.value,
        "severity_level": incident.severity_level.value,
        "followup_required": incident.followup_required_flag
    }


# ============================================================================
# KPI Endpoints
# ============================================================================

@router.get("/kpi/attendance-rate")
def get_attendance_rate_kpi(
    kindergarten_id: int,
    period_start: str,
    period_end: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate attendance rate KPI for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)
    
    # Get all active enrollments for this kindergarten
    active_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).count()
    
    if active_enrollments == 0:
        return {
            "kpi_name": "attendance_rate",
            "kpi_value": 0,
            "period_start": period_start,
            "period_end": period_end,
            "kindergarten_id": kindergarten_id
        }
    
    # Count attendance records in period
    child_ids = [e.child_id for e in db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).all()]
    
    attendance_count = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id.in_(child_ids),
        models.AttendanceLog.date >= start_date,
        models.AttendanceLog.date <= end_date
    ).count()
    
    # Calculate working days
    days = (end_date - start_date).days + 1
    working_days = days * 5 // 7  # Rough estimate
    
    expected_attendance = active_enrollments * working_days
    rate = (attendance_count / expected_attendance * 100) if expected_attendance > 0 else 0
    
    return {
        "kpi_name": "attendance_rate",
        "kpi_value": min(100, round(rate, 2)),
        "period_start": period_start,
        "period_end": period_end,
        "kindergarten_id": kindergarten_id
    }


# @router.get("/kpi/summary")  # Moved to kpi_service.py
# def get_kpi_summary(
#     kindergarten_id: Optional[int] = None,
#     period_start: Optional[str] = None,
#     period_end: Optional[str] = None,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get comprehensive KPI summary dashboard for all metrics"""
#     if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
#         raise HTTPException(status_code=403, detail="Only admin or manager can view KPI summaries")
#     
#     # Determine kindergarten scope
#     if kindergarten_id is None:
#         if current_user.role == models.UserRole.MANAGER:
#             kindergarten_id = current_user.kindergarten_id
#         else:
#             # Admin without kindergarten_id sees all (return first kindergarten for demo)
#             first_kg = db.query(models.Kindergarten).first()
#             kindergarten_id = first_kg.id if first_kg else None
#     
#     if not kindergarten_id:
#         raise HTTPException(status_code=400, detail="No kindergarten available")
#     
#     # Set default period to current month if not provided
#     if not period_start or not period_end:
#         today = date.today()
#         period_start = date(today.year, today.month, 1).isoformat()
#         last_day = date(today.year, today.month + 1, 1) - timedelta(days=1) if today.month < 12 else date(today.year, 12, 31)
#         period_end = last_day.isoformat()
#     
#     # Get active enrollments count
#     active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
#     ).scalar() or 0
#     
#     # Get total capacity across all classes
#     total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
#         models.Class.kindergarten_id == kindergarten_id,
#         models.Class.is_active == True
#     ).scalar() or 0
#     
#     # Calculate occupancy rate
#     occupancy_rate = (active_enrollments / total_capacity * 100) if total_capacity > 0 else 0
#     
#     # Count attendance records in period
#     start_date = date.fromisoformat(period_start)
#     end_date = date.fromisoformat(period_end)
#     
#     child_ids = [e.child_id for e in db.query(models.EnrollmentApplication).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
#     ).all()]
#     
#     attendance_count = db.query(func.count(models.AttendanceLog.id)).filter(
#         models.AttendanceLog.child_id.in_(child_ids) if child_ids else False,
#         models.AttendanceLog.date >= start_date,
#         models.AttendanceLog.date <= end_date
#     ).scalar() or 0
#     
#     # Calculate attendance rate
#     days = (end_date - start_date).days + 1
#     working_days = max(1, days * 5 // 7)  # Rough estimate
#     expected_attendance = active_enrollments * working_days
#     attendance_rate = (attendance_count / expected_attendance * 100) if expected_attendance > 0 else 0
#     
#     # Count incidents in period
#     incident_count = db.query(func.count(models.Incident.id)).filter(
#         models.Incident.kindergarten_id == kindergarten_id,
#         func.date(models.Incident.occurred_at) >= start_date,
#         func.date(models.Incident.occurred_at) <= end_date
#     ).scalar() or 0
#     
#     # Count pending daily reports
#     pending_reports = db.query(func.count(models.DailyReport.id)).join(
#         models.Child
#     ).join(
#     models.EnrollmentApplication
#     ).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.DailyReport.status == models.DailyReportStatus.SUBMITTED
#     ).scalar() or 0
#     
#     # Calculate governance score (weighted composite)
#     safety_score = max(0, 100 - (incident_count * 5))  # Deduct 5 points per incident
#     reports_score = 100 if pending_reports == 0 else max(50, 100 - (pending_reports * 2))
#     compliance_score = 85  # Placeholder for license/compliance checks
#     
#     governance_score = (
#         attendance_rate * 0.25 +
#         safety_score * 0.30 +
#         reports_score * 0.20 +
#         compliance_score * 0.25
#     )
#     
#     # Determine governance band
#     if governance_score >= 80:
#         governance_band = "GREEN"
#     elif governance_score >= 60:
#         governance_band = "AMBER"
#     else:
#         governance_band = "RED"
#     
#     return {
#         "kindergarten_id": kindergarten_id,
#         "period_start": period_start,
#         "period_end": period_end,
#         "kpis": {
#             "occupancy_rate": {
#                 "value": round(occupancy_rate, 2),
#                 "unit": "percent",
#                 "description": "Enrollment vs total capacity",
#                 "enrolled": active_enrollments,
#                 "capacity": total_capacity
#             },
#             "attendance_rate": {
#                 "value": round(min(100, attendance_rate), 2),
#                 "unit": "percent",
#                 "description": "Daily attendance rate",
#                 "attendance_count": attendance_count,
#                 "expected": expected_attendance
#             },
#             "governance_score": {
#                 "value": round(governance_score, 2),
#                 "unit": "score",
#                 "band": governance_band,
#                 "description": "Composite governance score"
#             },
#             "incident_count": {
#                 "value": incident_count,
#                 "unit": "count",
#                 "description": "Total incidents reported"
#             },
#             "pending_reports": {
#                 "value": pending_reports,
#                 "unit": "count",
#                 "description": "Daily reports pending approval"
#             }
#         }
#     }


@router.get("/kpi/governance-score")
def get_governance_score(
    kindergarten_id: int,
    period_start: str,
    period_end: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate governance score with traffic light band"""
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only admin or manager can view governance scores")
    
    if current_user.role == models.UserRole.MANAGER:
        validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    # Calculate sub-scores (simplified)
    # In production, these would be calculated from actual data
    attendance_score = 75.0
    safety_score = 90.0
    reports_score = 80.0
    compliance_score = 85.0
    
    # Weighted average
    final_score = (
        attendance_score * 0.25 +
        safety_score * 0.30 +
        reports_score * 0.20 +
        compliance_score * 0.25
    )
    
    # Determine band
    if final_score >= 80:
        band = "GREEN"
    elif final_score >= 60:
        band = "AMBER"
    else:
        band = "RED"
    
    return {
        "kindergarten_id": kindergarten_id,
        "period_start": period_start,
        "period_end": period_end,
        "final_governance_score": round(final_score, 2),
        "band": band,
        "sub_scores": {
            "attendance": attendance_score,
            "safety": safety_score,
            "daily_reports": reports_score,
            "compliance": compliance_score
        }
    }


# ============================================================================
# Supervisor Endpoints
# ============================================================================

class SupervisorAssignmentRequest(BaseModel):
    supervisor_id: int
    class_id: int
    start_date: str
    is_primary: bool = False


@router.post("/supervisor/assign")
def assign_supervisor(
    assignment_data: SupervisorAssignmentRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign supervisor to class (Manager only)"""
    validators.validate_manager_role(current_user)
    
    # Verify class exists
    class_obj = db.query(models.Class).filter(models.Class.id == assignment_data.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")
    
    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)
    
    # Verify supervisor exists and has correct role
    supervisor = db.query(models.User).filter(
        models.User.id == assignment_data.supervisor_id,
        models.User.role == models.UserRole.SUPERVISOR
    ).first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    
    assignment = models.SupervisorAssignment(
        class_id=assignment_data.class_id,
        supervisor_id=assignment_data.supervisor_id,
        start_date=date.fromisoformat(assignment_data.start_date),
        is_primary=assignment_data.is_primary
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return {
        "id": assignment.id,
        "supervisor_id": assignment.supervisor_id,
        "class_id": assignment.class_id,
        "is_primary": assignment.is_primary,
        "start_date": assignment.start_date.isoformat()
    }


class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str
    mastery_level: Optional[str] = None


@router.post("/observations", status_code=status.HTTP_201_CREATED)
def create_observation(
    observation_data: ObservationRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new observation (Supervisor/Manager/Admin only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create observations")
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == observation_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    # Parse observed_at from ISO string if provided
    observed_at = datetime.now()
    if hasattr(observation_data, 'observed_at') and observation_data.observed_at:
        try:
            observed_at = datetime.fromisoformat(observation_data.observed_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=observed_at
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value,
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }


@router.get("/children/{child_id}/observations")
def get_child_observations(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all observations for a specific child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Parents can only see their own child's observations
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")

    observations = db.query(models.Observation).filter(
        models.Observation.child_id == child_id
    ).order_by(models.Observation.observed_at.desc()).all()

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": o.id,
            "child_id": o.child_id,
            "domain": o.domain.value,
            "observation_text": o.observation_text,
            "mastery_level": o.mastery_level.value if o.mastery_level else None,
            "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            "observed_by": o.observed_by
        }
        for o in observations
    ]


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


@router.post("/supervisor/observations/record")
def record_observation(
    observation_data: ObservationRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record child observation (Supervisor only)"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can record observations")
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == observation_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=datetime.now()
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value,
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }


@router.get("/supervisor/children")
def get_supervisor_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all children in classes assigned to current supervisor"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")

    from supervisor_service import SupervisorService
    children = SupervisorService.get_supervisor_children(db, current_user)
    
    # Enrich with today's attendance status
    today = date.today()
    results = []
    
    for child in children:
        # Get active enrollment for class info
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        attendance = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == child.id,
            models.AttendanceLog.date == today
        ).first()
        
        status = "absent"
        check_in_time = None
        check_out_time = None
        
        if attendance:
            status = "present" if not attendance.check_out_at else "checked_out"
            check_in_time = attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None
            check_out_time = attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None
            
        results.append({
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value,
            "photo_url": None,
            "class_id": enrollment.class_id if enrollment else None,
            "attendance_status": status,
            "check_in_time": check_in_time,
            "check_out_time": check_out_time
        })
        
    return {"children": results}


@router.get("/children")
def list_children(
    kindergarten_id: Optional[int] = None,
    class_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List children with optional filtering by kindergarten or class"""
    query = db.query(models.Child).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )

    # Filter by kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id)
    elif kindergarten_id:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

    if class_id:
        query = query.filter(models.EnrollmentApplication.class_id == class_id)

    children = query.all()

    result = []
    for child in children:
        # Get enrollment info
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        child_info = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "first_name_ar": child.first_name,
            "last_name_ar": child.last_name,
            "gender": child.gender.value if child.gender else None,
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "photo_url": None,
            "enrollment_id": enrollment.id if enrollment else None,
            "class_id": enrollment.class_id if enrollment else None,
            "kindergarten_id": enrollment.kindergarten_id if enrollment else None
        }
        result.append(child_info)

    return {"children": result}


@router.get("/supervisor/my-classes")
def get_supervisor_classes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get classes assigned to current supervisor"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")
    
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= date.today()
        )
    ).all()
    
    classes = []
    for assignment in assignments:
        class_obj = assignment.class_
        classes.append({
            "id": class_obj.id,
            "name_ar": class_obj.name_ar,
            "name_en": class_obj.name_en,
            "kindergarten_id": class_obj.kindergarten_id,
            "is_primary": assignment.is_primary
        })
    
    return {"classes": classes}


@router.get("/supervisor/dashboard")
def get_supervisor_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get supervisor dashboard data"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access dashboard")
    
    # Get supervisor's classes
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= date.today()
        )
    ).all()
    
    class_ids = [a.class_id for a in assignments]
    
    # Count children in assigned classes
    total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0
    
    # Count today's attendance
    today = date.today()
    today_attendance = db.query(func.count(models.AttendanceLog.id)).join(
        models.EnrollmentApplication,
        models.AttendanceLog.child_id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.AttendanceLog.date == today
    ).scalar() or 0
    
    # Pending daily reports
    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.submitted_by == current_user.id,
        models.DailyReport.status == models.DailyReportStatus.DRAFT
    ).scalar() or 0
    
    return {
        "supervisor_id": current_user.id,
        "assigned_classes": len(class_ids),
        "total_children": total_children,
        "today_attendance": today_attendance,
        "pending_reports": pending_reports,
        "date": today.isoformat()
    }


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


@router.get("/portfolios")
def list_portfolios(
    child_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List portfolio entries (filtered by role and status)"""
    query = db.query(models.Portfolio)

    # Parents can only see published portfolios for their own children
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        
        if not parent_profile:
            return {"portfolios": []}
        
        # Get child IDs
        child_ids = [c.id for c in db.query(models.Child).filter(
            models.Child.parent_id == parent_profile.id
        ).all()]
        
        query = query.filter(
            models.Portfolio.child_id.in_(child_ids),
            models.Portfolio.status == models.PortfolioStatus.PUBLISHED
        )
    else:
        # Staff can see all portfolios in their kindergarten
        if child_id:
            query = query.filter(models.Portfolio.child_id == child_id)
        
        if status_filter:
            try:
                status_enum = models.PortfolioStatus(status_filter.upper())
                query = query.filter(models.Portfolio.status == status_enum)
            except ValueError:
                pass

    portfolios = query.order_by(models.Portfolio.created_at.desc()).all()

    return {
        "portfolios": [
            {
                "id": p.id,
                "child_id": p.child_id,
                "title": p.title,
                "description": p.description,
                "status": p.status.value,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in portfolios
        ]
    }


@router.get("/children/{child_id}/portfolio")
def get_child_portfolio(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all portfolio entries for a specific child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Parents can only see their own child's published portfolios
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        portfolios = db.query(models.Portfolio).filter(
            models.Portfolio.child_id == child_id,
            models.Portfolio.status == models.PortfolioStatus.PUBLISHED
        ).order_by(models.Portfolio.created_at.desc()).all()
    else:
        # Staff can see all portfolios
        portfolios = db.query(models.Portfolio).filter(
            models.Portfolio.child_id == child_id
        ).order_by(models.Portfolio.created_at.desc()).all()

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": p.id,
            "child_id": p.child_id,
            "title": p.title,
            "description": p.description,
            "status": p.status.value,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in portfolios
    ]


@router.post("/portfolios", status_code=status.HTTP_201_CREATED)
def create_portfolio_entry(
    portfolio_data: PortfolioCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new portfolio entry (Supervisor/Manager only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create portfolio entries")

    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == portfolio_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Accept status from request, default to DRAFT
    status_value = models.PortfolioStatus.DRAFT
    if hasattr(portfolio_data, 'status') and portfolio_data.status:
        try:
            status_value = models.PortfolioStatus(portfolio_data.status.upper())
        except (ValueError, AttributeError):
            pass

    portfolio = models.Portfolio(
        child_id=portfolio_data.child_id,
        title=portfolio_data.title,
        description=portfolio_data.description,
        status=status_value,
        published_at=datetime.now() if status_value == models.PortfolioStatus.PUBLISHED else None
    )

    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return {
        "id": portfolio.id,
        "child_id": portfolio.child_id,
        "title": portfolio.title,
        "status": portfolio.status.value
    }


@router.post("/portfolios/{portfolio_id}/publish")
def publish_portfolio_entry(
    portfolio_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Publish a portfolio entry (makes it visible to parents)"""
    validators.validate_manager_role(current_user)

    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if portfolio.status == models.PortfolioStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Portfolio already published")

    portfolio.status = models.PortfolioStatus.PUBLISHED
    portfolio.published_at = datetime.now()

    db.commit()
    db.refresh(portfolio)

    return {
        "id": portfolio.id,
        "status": portfolio.status.value,
        "published_at": portfolio.published_at.isoformat()
    }


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


@router.get("/children/{child_id}/health-alerts")
def get_child_health_alerts(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all health alerts for a child"""
    # Verify access
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Parents can only see their own child's alerts
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        
        if not parent_profile or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Access denied")

    alerts = db.query(models.HealthAlert).filter(
        models.HealthAlert.child_id == child_id
    ).order_by(models.HealthAlert.created_at.desc()).all()

    # Return list directly (backwards compatible with tests)
    return [
        {
            "id": a.id,
            "child_id": a.child_id,
            "alert_type": a.alert_type,
            "description": a.description,
            "severity": a.severity,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in alerts
    ]


@router.post("/children/{child_id}/health-alerts", status_code=status.HTTP_201_CREATED)
def create_health_alert(
    child_id: int,
    alert_data: HealthAlertCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a health alert for a child (Manager/Supervisor only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create health alerts")

    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Scope Check: Ensure child is active in user's KG
    if current_user.role != models.UserRole.ADMIN:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()

        if not enrollment:
             raise HTTPException(status_code=403, detail="Child is not active in your kindergarten")

    alert = models.HealthAlert(
        child_id=child_id,
        alert_type=alert_data.alert_type,
        description=alert_data.description,
        severity=alert_data.severity
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    return {
        "id": alert.id,
        "child_id": alert.child_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity
    }


@router.delete("/health-alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_health_alert(
    alert_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a health alert (Manager only)"""
    validators.validate_manager_role(current_user)

    alert = db.query(models.HealthAlert).filter(models.HealthAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Health alert not found")

    db.delete(alert)
    db.commit()

    return None


# ============================================================================
# Audit Logs Endpoints
# ============================================================================

@router.get("/audit-logs")
def list_audit_logs(
    page: int = 1,
    limit: int = 25,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    date: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List audit logs (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to view audit logs")

    query = db.query(
        models.AuditLog,
        models.User.username.label('user_name')
    ).outerjoin(
        models.User, models.AuditLog.user_id == models.User.id
    )

    # Apply filters
    if action:
        query = query.filter(models.AuditLog.action == action)

    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)

    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))

    if date:
        query = query.filter(func.date(models.AuditLog.created_at) == date)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * limit
    results = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    # Format results
    logs = []
    for audit_log, user_name in results:
        logs.append({
            "id": audit_log.id,
            "user_id": audit_log.user_id,
            "user_name": user_name,
            "action": audit_log.action,
            "entity_type": audit_log.entity_type,
            "entity_id": audit_log.entity_id,
            "details": audit_log.details,
            "ip_address": audit_log.ip_address,
            "sensitivity_level": audit_log.sensitivity_level,
            "created_at": audit_log.created_at.isoformat() if audit_log.created_at else None
        })

    total_pages = (total + limit - 1) // limit

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


@router.get("/audit-logs/export")
def export_audit_logs(
    format: str = "csv",
    period: str = "30",
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export audit logs (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to export audit logs")

    query = db.query(
        models.AuditLog,
        models.User.username.label('user_name')
    ).outerjoin(
        models.User, models.AuditLog.user_id == models.User.id
    )

    # Apply date filter based on period
    if period != "all":
        days = int(period)
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(models.AuditLog.created_at >= cutoff_date)

    # Apply other filters
    if action:
        query = query.filter(models.AuditLog.action == action)

    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)

    if user:
        query = query.filter(models.User.username.ilike(f"%{user}%"))

    results = query.order_by(models.AuditLog.created_at.desc()).all()

    # Format data for export
    data = []
    for audit_log, user_name in results:
        data.append({
            "id": audit_log.id,
            "user_name": user_name or "غير محدد",
            "action": audit_log.action,
            "entity_type": audit_log.entity_type,
            "entity_id": audit_log.entity_id,
            "details": audit_log.details,
            "ip_address": audit_log.ip_address,
            "created_at": audit_log.created_at.isoformat() if audit_log.created_at else None
        })

    if format == "csv":
        # Return CSV response
        import csv
        import io
        from fastapi.responses import StreamingResponse

        def generate_csv():
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys() if data else [])
            writer.writeheader()
            for row in data:
                writer.writerow(row)
            output.seek(0)
            yield output.getvalue()

        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit-logs.csv"}
        )

    elif format == "json":
        # Return JSON response
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content={"audit_logs": data},
            headers={"Content-Disposition": "attachment; filename=audit-logs.json"}
        )

    else:
        raise HTTPException(status_code=400, detail="Unsupported export format")


# ============================================================================
# Parent Profile Endpoint
# ============================================================================

@router.get("/parent/profile")
def get_parent_profile(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get parent profile. Returns 403 with translated message for non-parent users."""
    if current_user.role != models.UserRole.PARENT:
        from i18n import request_language, gettext
        lang = request_language(request)
        if lang == "ar":
            detail = "الوصول للوالدين فقط"
        else:
            detail = "Parent access only"
        raise HTTPException(status_code=403, detail=detail)

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()

    if not parent_profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")

    return {
        "id": parent_profile.id,
        "first_name": parent_profile.first_name,
        "last_name": parent_profile.last_name,
        "phone_number": parent_profile.phone_number,
        "user_id": parent_profile.user_id,
    }
