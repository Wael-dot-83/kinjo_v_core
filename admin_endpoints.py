"""
Hardened Admin Endpoints Module

This module provides secure admin endpoints with:
- Explicit admin authorization on all endpoints
- Rate limiting on sensitive operations
- Object-level authorization (IDOR protection)
- Standardized error responses with correlation IDs
- Comprehensive audit logging with before/after diffs
- Pagination enforcement
- Bulk operation guardrails with confirmation tokens
- CSV import with per-row validation and error reporting
- Dry-run/preview mode support
- Manager assignment validation (one active manager per kindergarten)
"""
import csv
import io
import json
import os
import secrets
import enum
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Dict, Any, Set, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, and_, select
from sqlalchemy.exc import SQLAlchemyError

import models
import validators
from database import get_db
from rate_limiter import limiter
from dependencies import get_current_user
from config import settings
from auth import get_password_hash, verify_password
from notification_service import create_message_notifications
from api.auth.password_reset_service import (
    issue_password_reset_token,
    resolve_valid_token,
    deliver_password_reset_email,
)
from messaging_permissions import ACTIVE_ENROLLMENT_STATUSES, ensure_kindergartens_exist
from kindergarten_import_service import KindergartenImportService
from cache_service import cache_service
from audit_actions import AuditAction
from admin_security import (
    # Error handling
    APIError, forbidden_error, unauthenticated_error, validation_error,
    not_found_error, conflict_error, rate_limited_error, create_error_response,
    ErrorCode,
    # Audit logging
    log_audit_event, model_to_dict, get_correlation_id, get_request_ip,
    # Authorization
    can_admin_access_user, validate_bulk_targets,
    # Schemas
    UserCreateSchema, UserUpdateSchema, BulkStatusUpdateSchema,
    BulkDeleteSchema, BulkCreateSchema, AdminPasswordResetSchema,
    PasswordResetRequestSchema, PasswordResetConfirmSchema,
    # Bulk operations
    BulkOperationConfig, BulkOperationResult, generate_confirmation_token,
    verify_confirmation_token,
    # CSV
    CSVRowError, CSVImportResult, sanitize_csv_cell, validate_csv_row,
    # Pagination
    PaginationConfig, enforce_pagination,
)

logger = logging.getLogger(__name__)
_ADMIN_DASHBOARD_CACHE_TTL_SECONDS = 30


def _admin_dashboard_cache_get(key: str):
    if settings.TESTING:
        return None
    try:
        return cache_service.get(key)
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Cache get failed for key '{key}': {e}", exc_info=False)
        return None


def _admin_dashboard_cache_set(
    key: str,
    value: Dict[str, Any],
    ttl_seconds: int = _ADMIN_DASHBOARD_CACHE_TTL_SECONDS,
) -> None:
    if settings.TESTING:
        return
    try:
        cache_service.set(key, value, ttl_seconds=ttl_seconds)
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        # Best-effort caching should never break dashboard reads.
        logger.warning(f"Cache set failed for key '{key}': {e}", exc_info=False)


# =============================================================================
# Manager Assignment Service Functions
# =============================================================================

def validate_manager_assignment(
    db: Session,
    role: models.UserRole,
    kindergarten_id: Optional[int],
    status_value: models.UserStatus,
    exclude_user_id: Optional[int] = None
) -> None:
    """
    Validate manager assignment rules.

    Business Rules:
    - Manager must be assigned to a kindergarten
    - Each kindergarten can have at most one active manager
    """
    try:
        validators.validate_manager_rules(
            db,
            role=role,
            kindergarten_id=kindergarten_id,
            status_value=status_value,
            exclude_user_id=exclude_user_id
        )
    except validators.ManagerRuleError as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            raise conflict_error(exc.message, {"kindergarten_id": exc.message})
        raise validation_error(
            exc.message,
            {"kindergarten_id": "Kindergarten is required for manager role"}
        )


def validate_bulk_manager_assignments(
    db: Session,
    users_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Validate manager assignments for bulk operations.

    Returns list of validation errors for each user that fails validation.
    """
    errors = []

    # Group managers by kindergarten to check for duplicates within the batch
    kg_managers = {}
    for i, user_data in enumerate(users_data):
        role = user_data.get('role')
        if isinstance(role, str):
            try:
                role = models.UserRole(role)
            except ValueError as e:
                logger.warning(f"Invalid role '{role}' at record {i}: {e}")
                role = None
        status_value = user_data.get('status', models.UserStatus.ACTIVE)
        if isinstance(status_value, str):
            try:
                status_value = models.UserStatus(status_value)
            except ValueError as e:
                logger.warning(f"Invalid status '{status_value}' at record {i}: {e}")
                status_value = models.UserStatus.INACTIVE
        if role == models.UserRole.MANAGER:
            kg_id = user_data.get('kindergarten_id')
            if kg_id is None:
                errors.append({
                    "row": i + 1,
                    "field": "kindergarten_id",
                    "error": "Manager must be assigned to a kindergarten"
                })
                continue

            if status_value == models.UserStatus.ACTIVE:
                if kg_id in kg_managers:
                    errors.append({
                        "row": i + 1,
                        "field": "kindergarten_id",
                        "error": f"Multiple managers assigned to kindergarten {kg_id} in this batch"
                    })
                    continue
                kg_managers[kg_id] = i + 1

            try:
                validators.validate_manager_rules(
                    db,
                    role=role,
                    kindergarten_id=kg_id,
                    status_value=status_value
                )
            except validators.ManagerRuleError as exc:
                errors.append({
                    "row": i + 1,
                    "field": "kindergarten_id",
                    "error": exc.message
                })

    return errors


# =============================================================================
# Router Definition
# =============================================================================

router = APIRouter(tags=["Admin"])


# =============================================================================
# Authorization Helpers
# =============================================================================

def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    Dependency that enforces admin role.
    Returns 401 if not authenticated, 403 if authenticated but not admin.
    """
    if current_user.role != models.UserRole.ADMIN:
        raise forbidden_error("Admin access required")
    return current_user


def require_admin_or_manager(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Dependency that enforces admin or manager role."""
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise forbidden_error("Admin or Manager access required")
    return current_user


def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    if request.client:
        return request.client.host
    return "unknown"


# =============================================================================
# User Management Endpoints (Hardened)
# =============================================================================

@router.get("/admin/users")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_users(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    role: Optional[models.UserRole] = None,
    status_filter: Optional[models.UserStatus] = Query(None, alias="status"),
    kindergarten_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    List users with pagination, filtering, and role-based scoping.

    - Admins: See all non-admin users, can filter by any kindergarten
    - Managers: See only users in their kindergarten

    Returns paginated results with enforced page size limits.
    """
    # Enforce pagination limits
    page, page_size, offset = enforce_pagination(page, page_size)

    query = db.query(models.User)

    # Apply role-based scoping
    if current_user.role == models.UserRole.ADMIN:
        # Admins see all except other admins
        query = query.filter(models.User.role != models.UserRole.ADMIN)
        if kindergarten_id:
            query = query.filter(models.User.kindergarten_id == kindergarten_id)
    else:
        # Managers are scoped to their kindergarten
        query = query.filter(models.User.kindergarten_id == current_user.kindergarten_id)
        # Ignore any cross-kindergarten filter attempts
        if kindergarten_id and kindergarten_id != current_user.kindergarten_id:
            log_audit_event(
                db, "ACCESS_DENIED", current_user, "User",
                metadata={"attempted_kindergarten_id": kindergarten_id},
                sensitivity_level=2
            )

    # Apply filters
    if role:
        # Prevent filtering by ADMIN role
        if role == models.UserRole.ADMIN:
            raise forbidden_error("Cannot filter by ADMIN role")
        query = query.filter(models.User.role == role)

    if status_filter:
        query = query.filter(models.User.status == status_filter)

    if search:
        search = search[:100]
        search_term = f"%{search}%"
        query = query.filter(or_(
            models.User.username.ilike(search_term),
            models.User.email.ilike(search_term)
        ))

    # Get total count before pagination
    total = query.count()

    # Apply pagination with stable ordering
    users = query.order_by(models.User.id).offset(offset).limit(page_size).all()

    # Calculate pagination metadata
    total_pages = (total + page_size - 1) // page_size

    return {
        "data": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role.value,
                "status": u.status.value,
                "kindergarten_id": u.kindergarten_id,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "correlation_id": get_correlation_id()
    }


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def create_user(
    request: Request,
    user_data: UserCreateSchema,
    current_user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Create a new user with strict validation.

    Authorization rules:
    - Admins: Can create any non-admin user
    - Managers: Can only create SUPERVISOR/PARENT roles in their kindergarten
    """
    # Authorization check
    if current_user.role == models.UserRole.MANAGER:
        # Manager restrictions
        if user_data.role in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
            log_audit_event(
                db, "ACCESS_DENIED", current_user, "User",
                metadata={"attempted_role": user_data.role.value},
                sensitivity_level=3
            )
            raise forbidden_error("Managers cannot create Admin or Manager accounts")

        # Force kindergarten to manager's kindergarten
        if user_data.kindergarten_id and user_data.kindergarten_id != current_user.kindergarten_id:
            log_audit_event(
                db, "ACCESS_DENIED", current_user, "User",
                metadata={"attempted_kindergarten_id": user_data.kindergarten_id},
                sensitivity_level=3
            )
            raise forbidden_error("Cannot create users for other kindergartens")

        user_data.kindergarten_id = current_user.kindergarten_id
    else:
        # Admin restrictions - cannot create other admins
        if user_data.role == models.UserRole.ADMIN:
            raise forbidden_error("Cannot create admin accounts through this endpoint")

    if user_data.role == models.UserRole.SUPERVISOR and not user_data.kindergarten_id:
        raise validation_error(
            "Supervisor must belong to a kindergarten",
            {"kindergarten_id": "Supervisor accounts require a kindergarten assignment"}
        )

    # Business rule: Manager validation
    validate_manager_assignment(
        db,
        user_data.role,
        user_data.kindergarten_id,
        models.UserStatus.ACTIVE
    )

    # Check for existing username or email (email only if provided)
    # Always check username uniqueness
    existing_username = db.query(models.User).filter(models.User.username == user_data.username).first()
    if existing_username:
        raise conflict_error("Username already exists", {"username": "Username is already taken"})

    # Check email uniqueness only if email is provided
    if user_data.email is not None:
        existing_email = db.query(models.User).filter(models.User.email == user_data.email).first()
        if existing_email:
            raise conflict_error("Email already exists", {"email": "Email is already registered"})

    # Create user
    hashed_password = get_password_hash(user_data.password)

    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role,
        kindergarten_id=user_data.kindergarten_id,
        status=models.UserStatus.ACTIVE,
        must_change_password=(user_data.role in [
            models.UserRole.MANAGER, models.UserRole.SUPERVISOR
        ]),
    )

    # Set profile fields if provided
    for field in ("full_name", "phone_number", "address", "nationality", "national_id", "passport_number"):
        val = getattr(user_data, field, None)
        if val is not None:
            setattr(new_user, field, val)

    # Validate identity by nationality for managers/supervisors
    if (
        user_data.nationality
        and user_data.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]
    ):
        try:
            validators.validate_identity_by_nationality(
                user_data.nationality,
                user_data.national_id,
                user_data.passport_number,
            )
        except validators.ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.message)

    db.add(new_user)
    db.flush()

    if new_user.role == models.UserRole.SUPERVISOR:
        validators.ensure_supervisor_profile(db, new_user, new_user.kindergarten_id)

    db.commit()
    db.refresh(new_user)

    # Handle child creation for PARENT role
    if user_data.role == models.UserRole.PARENT and user_data.children:
        # Create parent profile first
        parent_profile = models.ParentProfile(
            user_id=new_user.id,
            full_name="",  # Will be updated when parent completes profile
            home_governorate="",  # Will be updated when parent completes profile
            home_city="",  # Will be updated when parent completes profile
            home_area="",  # Will be updated when parent completes profile
            home_address_line="",  # Will be updated when parent completes profile
            correspondence_preference=True,
            profile_complete=False
        )
        db.add(parent_profile)
        db.commit()
        db.refresh(parent_profile)

        # Create children
        for child_data in user_data.children:
            try:
                validators.validate_child_age_strict(child_data.date_of_birth)
            except validators.ValidationError as exc:
                raise HTTPException(status_code=400, detail=exc.message)
            new_child = models.Child(
                parent_id=parent_profile.id,
                first_name=child_data.first_name,
                last_name=child_data.last_name,
                gender=child_data.gender,
                date_of_birth=child_data.date_of_birth,
                father_name=child_data.father_name,
                mother_first_name=child_data.mother_first_name,
                mother_second_name=child_data.mother_second_name or "",
                mother_last_name=child_data.mother_last_name or "",
                mother_nationality=child_data.mother_nationality or "",
                media_consent=False,  # Default false
                correspondence_flag=True,  # Default true
                profile_complete=False  # Will be completed later
            )
            db.add(new_child)

        db.commit()

        # Audit log for children creation
        log_audit_event(
            db, "CHILDREN_CREATED", current_user, "Child",
            target_ids=[child.id for child in parent_profile.children],
            metadata={"parent_user_id": new_user.id, "children_count": len(user_data.children)},
            sensitivity_level=2
        )

    # Audit log with after state
    log_audit_event(
        db, "USER_CREATED", current_user, "User",
        target_ids=new_user.id,
        after_state=model_to_dict(new_user),
        sensitivity_level=3
    )

    return {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "role": new_user.role.value,
        "status": new_user.status.value,
        "kindergarten_id": new_user.kindergarten_id,
        "full_name": new_user.full_name,
        "phone_number": new_user.phone_number,
        "address": new_user.address,
        "nationality": new_user.nationality,
        "national_id": new_user.national_id,
        "passport_number": new_user.passport_number,
        "correlation_id": get_correlation_id()
    }


# =============================================================================
# User Export
# =============================================================================

@router.get("/admin/users/export")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def export_users(
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    role: Optional[models.UserRole] = None,
    status_filter: Optional[models.UserStatus] = Query(None, alias="status"),
    kindergarten_id: Optional[int] = None,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Export users list with filtering.
    """
    query = db.query(models.User).filter(models.User.role != models.UserRole.ADMIN)

    if kindergarten_id:
        query = query.filter(models.User.kindergarten_id == kindergarten_id)
    if role:
        query = query.filter(models.User.role == role)
    if status_filter:
        query = query.filter(models.User.status == status_filter)

    users = query.order_by(models.User.id).all()

    # Audit log
    log_audit_event(
        db, AuditAction.USER_EXPORT, current_user, "User",
        metadata={"format": format, "count": len(users)},
        sensitivity_level=2
    )

    if format == "json":
        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role.value,
                "status": u.status.value,
                "kindergarten_id": u.kindergarten_id,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
        return JSONResponse(
            content=data,
            headers={
                "Content-Disposition": f"attachment; filename=users_export_{date.today()}.json"
            }
        )

    # CSV export
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
            u.created_at.isoformat() if u.created_at else ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users_export_{date.today()}.csv"}
    )


@router.get("/admin/users/{user_id:int}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_user(
    request: Request,
    user_id: int,
    current_user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Get user details with IDOR protection.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise not_found_error("User not found")

    # IDOR check
    if not can_admin_access_user(current_user, user):
        log_audit_event(
            db, "ACCESS_DENIED", current_user, "User",
            target_ids=user_id,
            metadata={"reason": "IDOR protection"},
            sensitivity_level=2
        )
        raise forbidden_error("Not authorized to access this user")

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "kindergarten_id": user.kindergarten_id,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "address": user.address,
        "nationality": user.nationality,
        "national_id": user.national_id,
        "passport_number": user.passport_number,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "correlation_id": get_correlation_id()
    }


@router.put("/admin/users/{user_id:int}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdateSchema,
    current_user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Update user with IDOR protection and audit logging.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise not_found_error("User not found")

    # IDOR check
    if not can_admin_access_user(current_user, user):
        log_audit_event(
            db, "ACCESS_DENIED", current_user, "User",
            target_ids=user_id,
            metadata={"reason": "IDOR protection", "action": "update"},
            sensitivity_level=2
        )
        raise forbidden_error("Not authorized to update this user")

    # Business rule: Manager validation for updates
    target_role = user_data.role if user_data.role is not None else user.role
    target_kindergarten_id = user_data.kindergarten_id if user_data.kindergarten_id is not None else user.kindergarten_id

    target_status = user_data.status if user_data.status is not None else user.status
    validate_manager_assignment(
        db,
        target_role,
        target_kindergarten_id,
        target_status,
        user_id
    )

    # Capture before state for audit
    before_state = model_to_dict(user)

    # Apply updates with authorization checks
    if user_data.email is not None:
        # Check uniqueness
        existing = db.query(models.User).filter(
            models.User.email == user_data.email,
            models.User.id != user_id
        ).first()
        if existing:
            raise conflict_error("Email already in use", {"email": "Email is already registered"})
        user.email = user_data.email

    if user_data.password is not None:
        user.hashed_password = get_password_hash(user_data.password)

    # Update profile fields if provided
    for field in ("full_name", "phone_number", "address", "nationality", "national_id", "passport_number"):
        val = getattr(user_data, field, None)
        if val is not None:
            setattr(user, field, val)

    # Validate identity by nationality if nationality changed
    if user_data.nationality and user.role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        try:
            validators.validate_identity_by_nationality(
                user_data.nationality,
                user_data.national_id or user.national_id,
                user_data.passport_number or user.passport_number,
            )
        except validators.ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.message)

    # Only admins can change role and status
    if current_user.role == models.UserRole.ADMIN:
        if user_data.role is not None:
            # Prevent promotion to admin
            if user_data.role == models.UserRole.ADMIN:
                raise forbidden_error("Cannot promote users to admin role")
            # Prevent demotion of admins
            if user.role == models.UserRole.ADMIN:
                raise forbidden_error("Cannot change role of admin users")
            user.role = user_data.role

        if user_data.status is not None:
            # Guard: ensure KG retains at least one supervisor on deactivation
            if (
                user_data.status in [models.UserStatus.INACTIVE, models.UserStatus.SUSPENDED]
                and user.role == models.UserRole.SUPERVISOR
                and user.kindergarten_id
            ):
                try:
                    validators.validate_kg_has_supervisor(db, user.kindergarten_id, exclude_user_id=user.id)
                except validators.ValidationError as exc:
                    raise HTTPException(status_code=400, detail=exc.message)
            user.status = user_data.status

        if user_data.kindergarten_id is not None:
            user.kindergarten_id = user_data.kindergarten_id

    db.commit()
    db.refresh(user)

    # Capture after state
    after_state = model_to_dict(user)

    # Audit log with diff
    log_audit_event(
        db, "USER_UPDATED", current_user, "User",
        target_ids=user.id,
        before_state=before_state,
        after_state=after_state,
        sensitivity_level=3
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "status": user.status.value,
        "kindergarten_id": user.kindergarten_id,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "address": user.address,
        "nationality": user.nationality,
        "national_id": user.national_id,
        "passport_number": user.passport_number,
        "correlation_id": get_correlation_id()
    }


@router.delete("/admin/users/{user_id:int}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def delete_user(
    request: Request,
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete user (Admin only) with IDOR protection.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise not_found_error("User not found")

    # Prevent self-deletion
    if current_user.id == user_id:
        raise validation_error("Cannot delete your own account")

    # Prevent deleting admins
    if user.role == models.UserRole.ADMIN:
        raise forbidden_error("Cannot delete admin accounts")

    # Capture before state for audit
    before_state = model_to_dict(user)

    db.delete(user)
    db.commit()

    # Audit log
    log_audit_event(
        db, "USER_DELETED", current_user, "User",
        target_ids=user_id,
        before_state=before_state,
        sensitivity_level=3
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Password Reset Endpoints (Hardened with Rate Limiting)
# =============================================================================

@router.post("/admin/users/{user_id:int}/admin-reset-password")
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def admin_reset_password(
    request: Request,
    user_id: int,
    reset_data: AdminPasswordResetSchema,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin-initiated password reset with verification.
    Rate limited to 3 requests per minute.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise not_found_error("User not found")

    # Prevent resetting admin passwords
    if user.role == models.UserRole.ADMIN:
        raise forbidden_error("Cannot reset admin passwords through this endpoint")

    # Verify admin's own password
    if not verify_password(reset_data.admin_password, current_user.hashed_password):
        log_audit_event(
            db, "ADMIN_PASSWORD_RESET_FAILED", current_user, "User",
            target_ids=user_id,
            metadata={"reason": "Admin password verification failed"},
            sensitivity_level=3
        )
        raise unauthenticated_error("Admin password verification failed")

    # Reset password
    user.hashed_password = get_password_hash(reset_data.new_password)
    db.commit()

    # Audit log
    log_audit_event(
        db, "ADMIN_PASSWORD_RESET", current_user, "User",
        target_ids=user_id,
        metadata={"initiated_by": current_user.username},
        sensitivity_level=3
    )

    return {
        "message": "Password reset successfully",
        "user_id": user_id,
        "correlation_id": get_correlation_id()
    }


@router.post("/admin/password-reset-request")
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET_REQUEST)
def request_password_reset(
    request: Request,
    reset_request: PasswordResetRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Request password reset token (self-service).
    Rate limited to 5 requests per minute.
    Always returns success to prevent email enumeration.
    """
    user = db.query(models.User).filter(models.User.email == reset_request.email).first()

    if user:
        token = issue_password_reset_token(db, user)

        # Audit log
        log_audit_event(
            db, "PASSWORD_RESET_REQUESTED", user, "User",
            target_ids=user.id,
            sensitivity_level=2
        )

        deliver_password_reset_email(str(request.base_url), user, token)

        # In development, token is returned to support local testing.
        if settings.ENVIRONMENT == "development":
            return {
                "message": "If the email exists, a reset link has been sent",
                "token": token,  # Only in development!
                "correlation_id": get_correlation_id()
            }

    # Always return same response to prevent enumeration
    return {
        "message": "If the email exists, a reset link has been sent",
        "correlation_id": get_correlation_id()
    }


@router.post("/admin/password-reset-confirm")
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def confirm_password_reset(
    request: Request,
    reset_data: PasswordResetConfirmSchema,
    db: Session = Depends(get_db)
):
    """
    Confirm password reset using token.
    Rate limited to 3 requests per minute.
    """
    token_record = resolve_valid_token(db, reset_data.token)

    if not token_record:
        raise validation_error("Invalid or expired token")

    # Reset password
    token_record.user.hashed_password = get_password_hash(reset_data.new_password)
    token_record.used = True
    db.commit()

    # Audit log
    log_audit_event(
        db, "PASSWORD_RESET_COMPLETED", token_record.user, "User",
        target_ids=token_record.user_id,
        sensitivity_level=2
    )

    return {
        "message": "Password reset successfully",
        "correlation_id": get_correlation_id()
    }


# =============================================================================
# MFA Management Endpoints (Admin Only)
# =============================================================================

class MFABypassSchema(BaseModel):
    """Request schema for MFA bypass (emergency admin action)"""
    user_id: int
    reason: str = "Emergency unlock"
    admin_password: str  # Verify admin identity

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_id": 5,
            "reason": "User locked out - lost MFA device",
            "admin_password": "AdminPassword123!"
        }
    })


@router.post("/admin/users/{user_id:int}/mfa-bypass")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def admin_mfa_bypass(
    request: Request,
    user_id: int,
    mfa_request: MFABypassSchema,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Emergency MFA bypass for locked-out users (Admin only).
    Requires admin password verification and logs audit trail.
    
    WARNING: This is an emergency-only endpoint. Use sparingly and audit all usage.
    """
    # Verify admin's own password
    if not verify_password(mfa_request.admin_password, current_user.hashed_password):
        log_audit_event(
            db, "MFA_BYPASS_FAILED_AUTH", current_user, "User",
            target_ids=user_id,
            metadata={"reason": "Admin password verification failed"},
            sensitivity_level=3
        )
        raise unauthenticated_error("Admin password verification failed")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise not_found_error("User not found")

    # Reset MFA but don't disable it - require re-setup
    user.mfa_secret = None
    user.mfa_enabled = False
    user.mfa_enrolled_at = None
    user.mfa_last_verified_at = None
    db.commit()

    # Audit log with high sensitivity
    log_audit_event(
        db, "MFA_BYPASS_INITIATED", current_user, "User",
        target_ids=user_id,
        metadata={
            "reason": mfa_request.reason,
            "initiated_by": current_user.username,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        sensitivity_level=3  # Critical security event
    )

    return {
        "message": "MFA bypass completed. User must re-enroll MFA on next login.",
        "user_id": user_id,
        "correlation_id": get_correlation_id()
    }


@router.get("/admin/users/{user_id:int}/mfa-status")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_user_mfa_status(
    request: Request,
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get MFA status for a user (Admin only)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise not_found_error("User not found")

    return {
        "user_id": user.id,
        "username": user.username,
        "mfa_enabled": user.mfa_enabled,
        "mfa_enrolled_at": user.mfa_enrolled_at.isoformat() if user.mfa_enrolled_at else None,
        "mfa_last_verified_at": user.mfa_last_verified_at.isoformat() if user.mfa_last_verified_at else None,
        "mfa_secret_set": bool(user.mfa_secret),
        "correlation_id": get_correlation_id()
    }


# =============================================================================
# Bulk Operations (Hardened with Guardrails)
# =============================================================================

@router.post("/admin/users/bulk-status-update")
@limiter.limit(settings.RATE_LIMIT_BULK_UPDATE)
def bulk_update_status(
    request: Request,
    bulk_data: BulkStatusUpdateSchema,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Bulk update user status with confirmation for large operations.

    Features:
    - Requires confirmation token for operations affecting > 10 users
    - Supports dry-run mode for preview
    - Returns per-user success/failure results
    - IDOR protection for each target
    """
    if not bulk_data.user_ids:
        raise validation_error("No user IDs provided")

    if len(bulk_data.user_ids) > settings.MAX_BULK_UPDATE:
        raise validation_error(f"Cannot update more than {settings.MAX_BULK_UPDATE} users at once")

    # Check if confirmation is required
    needs_confirmation = len(bulk_data.user_ids) > settings.BULK_CONFIRMATION_THRESHOLD

    if needs_confirmation and not bulk_data.dry_run:
        if not bulk_data.confirmation_token:
            # Generate confirmation token
            token = generate_confirmation_token("bulk_status_update", bulk_data.user_ids, current_user.id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "requires_confirmation": True,
                    "confirmation_token": token,
                    "affected_count": len(bulk_data.user_ids),
                    "message": f"This operation will affect {len(bulk_data.user_ids)} users. Please confirm.",
                    "correlation_id": get_correlation_id()
                }
            )

        # Verify confirmation token
        if not verify_confirmation_token(
            bulk_data.confirmation_token,
            "bulk_status_update",
            bulk_data.user_ids,
            current_user.id
        ):
            raise validation_error("Invalid confirmation token")

    # Validate access to each user
    access_result = validate_bulk_targets(
        db, current_user, bulk_data.user_ids, models.User,
        can_admin_access_user
    )

    if access_result["forbidden"]:
        log_audit_event(
            db, "BULK_ACCESS_DENIED", current_user, "User",
            target_ids=access_result["forbidden"],
            metadata={"action": "bulk_status_update"},
            sensitivity_level=2
        )

    if bulk_data.dry_run:
        return {
            "dry_run": True,
            "would_update": len(access_result["allowed"]),
            "allowed_ids": access_result["allowed"],
            "forbidden_ids": access_result["forbidden"],
            "not_found_ids": access_result["not_found"],
            "correlation_id": get_correlation_id()
        }

    # Validate manager status changes
    if bulk_data.new_status == models.UserStatus.ACTIVE:
        manager_validation_errors = []
        seen_kgs = set()
        # Batch-load all target users to avoid N+1 queries
        target_users = {
            u.id: u for u in
            db.query(models.User).filter(models.User.id.in_(access_result["allowed"])).all()
        }
        for user_id in access_result["allowed"]:
            user = target_users.get(user_id)
            if user and user.role == models.UserRole.MANAGER:
                if user.kindergarten_id is None:
                    manager_validation_errors.append({
                        "user_id": user_id,
                        "error": "Manager must be assigned to a kindergarten",
                        "field": "kindergarten_id"
                    })
                    continue
                if user.kindergarten_id in seen_kgs:
                    manager_validation_errors.append({
                        "user_id": user_id,
                        "error": f"Multiple managers in this batch for kindergarten {user.kindergarten_id}",
                        "field": "status"
                    })
                    continue
                seen_kgs.add(user.kindergarten_id)
                try:
                    validate_manager_assignment(
                        db,
                        user.role,
                        user.kindergarten_id,
                        models.UserStatus.ACTIVE,
                        user_id
                    )
                except APIError as e:
                    manager_validation_errors.append({
                        "user_id": user_id,
                        "error": e.message,
                        "field": "status"
                    })

        if manager_validation_errors:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "message": "Manager activation would violate kindergarten assignment rules",
                    "errors": manager_validation_errors,
                    "correlation_id": get_correlation_id()
                }
            )

    # Execute update (reuse batch-loaded users if available, else batch-load)
    succeeded = []
    failed = []
    errors = []

    if 'target_users' not in dir():
        target_users = {
            u.id: u for u in
            db.query(models.User).filter(models.User.id.in_(access_result["allowed"])).all()
        }

    for user_id in access_result["allowed"]:
        try:
            user = target_users.get(user_id)
            if user:
                before_state = model_to_dict(user)
                user.status = bulk_data.new_status
                succeeded.append(user_id)
        except (AttributeError, ValueError, TypeError) as e:
            failed.append(user_id)
            errors.append({"user_id": user_id, "error": str(e)})

    db.commit()

    # Audit log
    log_audit_event(
        db, "BULK_STATUS_UPDATE", current_user, "User",
        target_ids=succeeded,
        metadata={
            "new_status": bulk_data.new_status.value,
            "succeeded_count": len(succeeded),
            "failed_count": len(failed) + len(access_result["forbidden"]) + len(access_result["not_found"])
        },
        sensitivity_level=3
    )

    return {
        "message": f"Updated {len(succeeded)} users",
        "succeeded_count": len(succeeded),
        "failed_count": len(failed) + len(access_result["forbidden"]) + len(access_result["not_found"]),
        "succeeded_ids": succeeded,
        "failed_ids": failed + access_result["forbidden"] + access_result["not_found"],
        "errors": errors,
        "forbidden_ids": access_result["forbidden"],
        "not_found_ids": access_result["not_found"],
        "correlation_id": get_correlation_id()
    }


@router.post("/admin/users/bulk-delete")
@limiter.limit(settings.RATE_LIMIT_BULK_DELETE)
def bulk_delete_users(
    request: Request,
    bulk_data: BulkDeleteSchema,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Bulk delete users with confirmation and IDOR protection.

    Features:
    - Requires confirmation token for ALL bulk deletes (destructive)
    - Prevents deleting admin accounts
    - Returns detailed results
    """
    if not bulk_data.user_ids:
        raise validation_error("No user IDs provided")

    if len(bulk_data.user_ids) > settings.MAX_BULK_DELETE:
        raise validation_error(f"Cannot delete more than {settings.MAX_BULK_DELETE} users at once")

    # Check for admin accounts in the list
    admin_users = db.query(models.User).filter(
        models.User.id.in_(bulk_data.user_ids),
        models.User.role == models.UserRole.ADMIN
    ).all()

    if admin_users:
        raise forbidden_error(f"Cannot delete admin accounts: {[u.username for u in admin_users]}")

    # Bulk delete ALWAYS requires confirmation
    if not bulk_data.dry_run:
        if not bulk_data.confirmation_token:
            token = generate_confirmation_token("bulk_delete", bulk_data.user_ids, current_user.id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "requires_confirmation": True,
                    "confirmation_token": token,
                    "affected_count": len(bulk_data.user_ids),
                    "warning": "This action is IRREVERSIBLE. Please confirm to proceed.",
                    "correlation_id": get_correlation_id()
                }
            )

        if not verify_confirmation_token(
            bulk_data.confirmation_token,
            "bulk_delete",
            bulk_data.user_ids,
            current_user.id
        ):
            raise validation_error("Invalid confirmation token")

    # Validate access
    access_result = validate_bulk_targets(
        db, current_user, bulk_data.user_ids, models.User,
        can_admin_access_user
    )

    if bulk_data.dry_run:
        return {
            "dry_run": True,
            "would_delete": len(access_result["allowed"]),
            "allowed_ids": access_result["allowed"],
            "forbidden_ids": access_result["forbidden"],
            "not_found_ids": access_result["not_found"],
            "correlation_id": get_correlation_id()
        }

    # Execute delete — batch-load users to avoid N+1
    deleted_ids = []
    target_users = {
        u.id: u for u in
        db.query(models.User).filter(models.User.id.in_(access_result["allowed"])).all()
    }
    for user_id in access_result["allowed"]:
        user = target_users.get(user_id)
        if user:
            before_state = model_to_dict(user)
            db.delete(user)
            deleted_ids.append(user_id)

    db.commit()

    # Audit log
    log_audit_event(
        db, "BULK_USER_DELETE", current_user, "User",
        target_ids=deleted_ids,
        metadata={
            "deleted_count": len(deleted_ids),
            "forbidden_count": len(access_result["forbidden"]),
            "not_found_count": len(access_result["not_found"])
        },
        sensitivity_level=3
    )

    return {
        "message": f"Deleted {len(deleted_ids)} users",
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "forbidden_ids": access_result["forbidden"],
        "not_found_ids": access_result["not_found"],
        "correlation_id": get_correlation_id()
    }


@router.post("/admin/users/bulk-create")
@limiter.limit(settings.RATE_LIMIT_BULK_CREATE)
def bulk_create_users(
    request: Request,
    bulk_data: BulkCreateSchema,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Bulk create users with per-user validation and error reporting.

    Features:
    - Validates each user against schema
    - Reports per-user errors
    - Supports dry-run mode
    - Prevents creating admin accounts
    """
    if not bulk_data.users:
        raise validation_error("No users provided")

    if len(bulk_data.users) > settings.MAX_BULK_CREATE:
        raise validation_error(f"Cannot create more than {settings.MAX_BULK_CREATE} users at once")

    # Validate manager assignments for the entire batch
    manager_errors = validate_bulk_manager_assignments(db, [user.__dict__ for user in bulk_data.users])
    if manager_errors:
        return JSONResponse(
            status_code=status.HTTP_200_OK if bulk_data.dry_run else status.HTTP_400_BAD_REQUEST,
            content={
                "dry_run": bulk_data.dry_run,
                "total": len(bulk_data.users),
                "succeeded_count": 0,
                "failed_count": len(manager_errors),
                "errors": manager_errors,
                "message": "Manager validation failed",
                "correlation_id": get_correlation_id()
            }
        )

    succeeded = []
    failed = []
    errors = []

    # Pre-load existing usernames and emails to avoid N+1 queries
    incoming_usernames = {u.username for u in bulk_data.users}
    incoming_emails = {u.email for u in bulk_data.users if u.email is not None}
    existing_usernames = set(
        row[0] for row in db.query(models.User.username)
        .filter(models.User.username.in_(incoming_usernames)).all()
    ) if incoming_usernames else set()
    existing_emails = set(
        row[0] for row in db.query(models.User.email)
        .filter(models.User.email.in_(incoming_emails)).all()
    ) if incoming_emails else set()

    for i, user_data in enumerate(bulk_data.users):
        row_num = i + 1

        # Prevent creating admins
        if user_data.role == models.UserRole.ADMIN:
            failed.append(row_num)
            errors.append({
                "row": row_num,
                "field": "role",
                "error": "Cannot create admin accounts through bulk create"
            })
            continue

        # Check for existing username/email using pre-loaded sets
        if user_data.username in existing_usernames:
            failed.append(row_num)
            errors.append({
                "row": row_num,
                "field": "username",
                "error": "Username already exists"
            })
            continue

        # Check email uniqueness only if email is provided
        if user_data.email is not None and user_data.email in existing_emails:
                failed.append(row_num)
                errors.append({
                    "row": row_num,
                    "field": "email",
                    "error": "Email already exists"
                })
                continue

        if not bulk_data.dry_run:
            try:
                new_user = models.User(
                    username=user_data.username,
                    email=user_data.email,
                    hashed_password=get_password_hash(user_data.password),
                    role=user_data.role,
                    kindergarten_id=user_data.kindergarten_id,
                    status=models.UserStatus.ACTIVE
                )
                db.add(new_user)
                db.flush()
                succeeded.append({"row": row_num, "id": new_user.id, "username": new_user.username})
            except (SQLAlchemyError, AttributeError, ValueError, KeyError) as e:
                failed.append(row_num)
                errors.append({
                    "row": row_num,
                    "field": "unknown",
                    "error": str(e)
                })
        else:
            succeeded.append({"row": row_num, "username": user_data.username})

    if not bulk_data.dry_run:
        db.commit()

        # Audit log
        log_audit_event(
            db, "BULK_USER_CREATE", current_user, "User",
            target_ids=[s["id"] for s in succeeded if "id" in s],
            metadata={
                "created_count": len(succeeded),
                "failed_count": len(failed)
            },
            sensitivity_level=3
        )

    return {
        "dry_run": bulk_data.dry_run,
        "message": f"{'Would create' if bulk_data.dry_run else 'Created'} {len(succeeded)} users",
        "total": len(bulk_data.users),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "errors": errors,
        "correlation_id": get_correlation_id()
    }


# =============================================================================
# CSV Import with Per-Row Validation
# =============================================================================

@router.post("/admin/users/import-csv")
@limiter.limit(settings.RATE_LIMIT_CSV_IMPORT)
async def import_users_csv(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Preview import without applying"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Import users from CSV with comprehensive validation.

    Features:
    - Per-row validation with detailed error reporting
    - CSV injection protection
    - Dry-run mode for preview
    - Downloadable error report
    """
    if not file.filename.endswith('.csv'):
        raise validation_error("File must be a CSV")

    # Read and decode CSV
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8-sig')  # Handle BOM
    except (UnicodeDecodeError, OSError) as e:
        raise validation_error(f"Could not read file: {str(e)}")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(decoded))

    total_rows = 0
    succeeded = []
    failed = []
    errors: List[CSVRowError] = []
    created_ids = []

    required_fields = {'username', 'email', 'password', 'role'}
    header_fields = set(reader.fieldnames or [])

    # Validate headers
    missing_fields = required_fields - header_fields
    if missing_fields:
        raise validation_error(
            f"Missing required columns: {', '.join(missing_fields)}",
            {field: "Column required" for field in missing_fields}
        )

    manager_kgs_in_csv = set()

    for row in reader:
        total_rows += 1
        row_num = total_rows + 1  # Account for header row

        # Sanitize all cells
        sanitized_row = {k: sanitize_csv_cell(str(v).strip()) if v else '' for k, v in row.items()}

        # Validate role
        role_str = sanitized_row.get('role', '').upper()
        if role_str not in ['MANAGER', 'SUPERVISOR', 'PARENT']:
            errors.append(CSVRowError(
                row_number=row_num,
                field='role',
                error_code='INVALID_ROLE',
                message=f"Invalid role: {role_str}. Must be MANAGER, SUPERVISOR, or PARENT"
            ))
            failed.append(row_num)
            continue

        # Validate and create
        try:
            user_data = UserCreateSchema(
                username=sanitized_row.get('username', ''),
                email=sanitized_row.get('email', ''),
                password=sanitized_row.get('password', ''),
                role=models.UserRole(role_str),
                kindergarten_id=int(sanitized_row['kindergarten_id']) if sanitized_row.get('kindergarten_id') else None
            )
        except (ValueError, AttributeError, KeyError, TypeError) as e:
            if hasattr(e, 'errors'):
                for err in e.errors():
                    errors.append(CSVRowError(
                        row_number=row_num,
                        field='.'.join(str(loc) for loc in err.get('loc', [])),
                        error_code='VALIDATION_ERROR',
                        message=err.get('msg', str(err))
                    ))
            else:
                errors.append(CSVRowError(
                    row_number=row_num,
                    error_code='PARSE_ERROR',
                    message=str(e)
                ))
            failed.append(row_num)
            continue

        # Check for existing
        existing = db.query(models.User).filter(
            or_(
                models.User.username == user_data.username,
                models.User.email == user_data.email
            )
        ).first()

        if existing:
            field = 'username' if existing.username == user_data.username else 'email'
            errors.append(CSVRowError(
                row_number=row_num,
                field=field,
                error_code='DUPLICATE',
                message=f"{field.capitalize()} already exists"
            ))
            failed.append(row_num)
            continue

        if user_data.role == models.UserRole.MANAGER:
            if user_data.kindergarten_id in manager_kgs_in_csv:
                errors.append(CSVRowError(
                    row_number=row_num,
                    field='kindergarten_id',
                    error_code='CONFLICT',
                    message=f"Multiple managers assigned to kindergarten {user_data.kindergarten_id} in this CSV"
                ))
                failed.append(row_num)
                continue

            try:
                validators.validate_manager_rules(
                    db,
                    role=user_data.role,
                    kindergarten_id=user_data.kindergarten_id,
                    status_value=models.UserStatus.ACTIVE
                )
            except validators.ManagerRuleError as exc:
                errors.append(CSVRowError(
                    row_number=row_num,
                    field='kindergarten_id',
                    error_code='CONFLICT' if exc.status_code == status.HTTP_409_CONFLICT else 'VALIDATION_ERROR',
                    message=exc.message
                ))
                failed.append(row_num)
                continue

            manager_kgs_in_csv.add(user_data.kindergarten_id)

        if not dry_run:
            new_user = models.User(
                username=user_data.username,
                email=user_data.email,
                hashed_password=get_password_hash(user_data.password),
                role=user_data.role,
                kindergarten_id=user_data.kindergarten_id,
                status=models.UserStatus.ACTIVE
            )
            db.add(new_user)
            db.flush()
            created_ids.append(new_user.id)

        succeeded.append(row_num)

    if not dry_run and created_ids:
        db.commit()

        # Audit log
        log_audit_event(
            db, "CSV_IMPORT", current_user, "User",
            target_ids=created_ids,
            metadata={
                "filename": file.filename,
                "total_rows": total_rows,
                "succeeded": len(succeeded),
                "failed": len(failed)
            },
            sensitivity_level=3
        )

    result = CSVImportResult(
        total_rows=total_rows,
        succeeded=len(succeeded),
        failed=len(failed),
        errors=errors,
        created_ids=created_ids if not dry_run else [],
        dry_run=dry_run
    )

    return {
        "total_rows": result.total_rows,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "errors": [e.model_dump() for e in result.errors],
        "created_ids": result.created_ids,
        "dry_run": result.dry_run,
        "correlation_id": get_correlation_id()
    }


@router.get("/admin/users/import-csv/error-report")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def download_csv_error_report(
    request: Request,
    errors: str = Query(..., description="JSON-encoded error list"),
    current_user: models.User = Depends(require_admin),
):
    """
    Download CSV import error report as CSV file.
    """
    try:
        error_list = json.loads(errors)
    except json.JSONDecodeError:
        raise validation_error("Invalid error data format")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Row Number', 'Field', 'Error Code', 'Message'])

    for err in error_list:
        writer.writerow([
            err.get('row_number', ''),
            err.get('field', ''),
            err.get('error_code', ''),
            err.get('message', '')
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=import_errors_{date.today()}.csv"
        }
    )


# =============================================================================
# Admin Messaging (Targeted Announcements)
# =============================================================================

class AdminRecipientRole(str, enum.Enum):
    MANAGER = "MANAGER"
    SUPERVISOR = "SUPERVISOR"
    PARENT = "PARENT"


class AdminMessageTargetMode(str, enum.Enum):
    ALL_USERS = "ALL_USERS"
    ALL_MANAGERS = "ALL_MANAGERS"
    ALL_SUPERVISORS = "ALL_SUPERVISORS"
    ALL_PARENTS = "ALL_PARENTS"
    GOVERNORATE = "GOVERNORATE"
    KINDERGARTENS = "KINDERGARTENS"


class AdminMessageTarget(BaseModel):
    mode: AdminMessageTargetMode
    roles: Optional[List[AdminRecipientRole]] = None
    governorates: Optional[List[str]] = None
    kindergarten_ids: Optional[List[int]] = None
    search: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class AdminMessageCreate(BaseModel):
    subject: str
    message_body: str
    target: AdminMessageTarget
    allow_replies: bool = True

    model_config = ConfigDict(extra="ignore")


class AdminMessagePreviewRequest(BaseModel):
    subject: Optional[str] = None
    message_body: Optional[str] = None
    target: AdminMessageTarget
    allow_replies: bool = True
    page: int = 1
    page_size: int = 10

    model_config = ConfigDict(extra="ignore")


class AdminRecipientSummary(BaseModel):
    id: int
    display_name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    kindergarten_id: Optional[int] = None
    kindergarten_name: Optional[str] = None
    governorate: Optional[str] = None


class AdminPaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class AdminRecipientListResponse(BaseModel):
    items: List[AdminRecipientSummary]
    pagination: AdminPaginationMeta


class AdminMessageResponse(BaseModel):
    id: int
    thread_type: str
    subject: Optional[str]
    message_body: str
    created_at: datetime
    recipient_count: int
    warnings: List[str] = []


def _dedupe_int_list(values: Optional[List[int]]) -> List[int]:
    cleaned: List[int] = []
    for value in values or []:
        try:
            cleaned.append(int(value))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys([v for v in cleaned if v]))


def _normalize_governorates(governorates: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for gov in governorates or []:
        if not gov:
            continue
        try:
            ar_value = validators.validate_jordan_governorate(gov)
        except validators.ValidationError:
            raise validation_error("Invalid governorate", fields={"governorates": "invalid"})
        normalized.append(ar_value)
        if ar_value in settings.JORDAN_GOVERNORATES:
            idx = settings.JORDAN_GOVERNORATES.index(ar_value)
            if idx < len(settings.JORDAN_GOVERNORATES_ENGLISH):
                normalized.append(settings.JORDAN_GOVERNORATES_ENGLISH[idx])
    return list(dict.fromkeys(normalized))


def _canonical_governorates(governorates: Optional[List[str]]) -> List[str]:
    canonical: List[str] = []
    for gov in governorates or []:
        if not gov:
            continue
        try:
            canonical.append(validators.validate_jordan_governorate(gov))
        except validators.ValidationError:
            raise validation_error("Invalid governorate", fields={"governorates": "invalid"})
    return list(dict.fromkeys(canonical))


def _validate_csrf_token(request: Request) -> None:
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get("kinjo_csrf_token")
    if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
        raise validation_error("Invalid CSRF token", fields={"csrf_token": "invalid"})


def _build_search_filter(search: Optional[str], columns: List[Any]):
    """Return a compound filter that matches every search token against provided columns."""
    tokens = [token.strip() for token in (search or "").split() if token.strip()]
    if not tokens or not columns:
        return None

    token_clauses = []
    for token in tokens:
        pattern = f"%{token}%"
        token_clauses.append(or_(*(column.ilike(pattern) for column in columns)))
    return and_(*token_clauses)


def _build_staff_recipient_query(
    db: Session,
    roles: List[models.UserRole],
    governorates: List[str],
    kindergarten_ids: List[int],
    search_term: Optional[str]
) -> Any:
    staff_roles = [role for role in roles if role in {models.UserRole.MANAGER, models.UserRole.SUPERVISOR}]
    query = db.query(models.User.id).filter(
        models.User.status == models.UserStatus.ACTIVE,
        models.User.role.in_(staff_roles)
    )

    if kindergarten_ids:
        query = query.filter(models.User.kindergarten_id.in_(kindergarten_ids))

    if governorates:
        query = query.join(
            models.Kindergarten,
            models.User.kindergarten_id == models.Kindergarten.id
        ).filter(models.Kindergarten.governorate.in_(governorates))

    search_cols = [models.User.username, models.User.email]
    if search_term:
        query = query.outerjoin(models.Kindergarten, models.User.kindergarten_id == models.Kindergarten.id)
        search_cols.extend([
            models.Kindergarten.name_ar,
            models.Kindergarten.name_en
        ])
        search_filter = _build_search_filter(search_term, search_cols)
        if search_filter is not None:
            query = query.filter(search_filter)

    return query.distinct()


def _build_parent_recipient_query(
    db: Session,
    governorates: List[str],
    kindergarten_ids: List[int],
    search_term: Optional[str]
) -> Any:
    query = (
        db.query(models.User.id)
        .join(models.ParentProfile, models.ParentProfile.user_id == models.User.id)
        .filter(
            models.User.status == models.UserStatus.ACTIVE,
            models.User.role == models.UserRole.PARENT
        )
    )

    search_cols = [
        models.User.username,
        models.User.email,
        models.ParentProfile.first_name,
        models.ParentProfile.second_name,
        models.ParentProfile.last_name,
        models.ParentProfile.first_name_en,
        models.ParentProfile.last_name_en,
        models.ParentProfile.phone_number
    ]

    if search_term:
        query = query.outerjoin(
            models.Child,
            models.Child.parent_id == models.ParentProfile.id
        ).outerjoin(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).outerjoin(
            models.Kindergarten,
            models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id
        )
        search_cols.extend([
            models.Kindergarten.name_ar,
            models.Kindergarten.name_en
        ])
        search_filter = _build_search_filter(search_term, search_cols)
        if search_filter is not None:
            query = query.filter(search_filter)

    if kindergarten_ids or governorates:
        enrollment_query = (
            db.query(models.ParentProfile.user_id)
            .join(
                models.Child,
                models.Child.parent_id == models.ParentProfile.id
            )
            .join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            )
            .join(
                models.Kindergarten,
                models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id
            )
            .filter(models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES))
        )

        if kindergarten_ids:
            enrollment_query = enrollment_query.filter(
                models.EnrollmentApplication.kindergarten_id.in_(kindergarten_ids)
            )
        if governorates:
            enrollment_query = enrollment_query.filter(models.Kindergarten.governorate.in_(governorates))

        enrolled_parent_ids = enrollment_query.distinct().subquery()
        enrolled_parent_ids_select = select(enrolled_parent_ids.c.user_id)

        if governorates and not kindergarten_ids:
            active_parent_ids = (
                db.query(models.ParentProfile.user_id)
                .join(
                    models.Child,
                    models.Child.parent_id == models.ParentProfile.id
                )
                .join(
                    models.EnrollmentApplication,
                    models.EnrollmentApplication.child_id == models.Child.id
                )
                .filter(
                    models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
                )
                .distinct()
                .subquery()
            )
            active_parent_ids_select = select(active_parent_ids.c.user_id)
            query = query.filter(or_(
                models.ParentProfile.user_id.in_(enrolled_parent_ids_select),
                and_(
                    ~models.ParentProfile.user_id.in_(active_parent_ids_select),
                    models.ParentProfile.home_governorate.in_(governorates)
                )
            ))
        else:
            query = query.filter(models.ParentProfile.user_id.in_(enrolled_parent_ids_select))

    return query.distinct()


def _count_admin_recipients(
    db: Session,
    roles: List[models.UserRole],
    governorates: List[str],
    kindergarten_ids: List[int],
    search: Optional[str]
) -> int:
    total = 0
    search_term = (search or "").strip()

    staff_roles = [role for role in roles if role in {models.UserRole.MANAGER, models.UserRole.SUPERVISOR}]
    if staff_roles:
        staff_query = _build_staff_recipient_query(db, roles, governorates, kindergarten_ids, search_term)
        staff_count_stmt = select(func.count()).select_from(staff_query.subquery())
        total += db.execute(staff_count_stmt).scalar_one()

    if models.UserRole.PARENT in roles:
        parent_query = _build_parent_recipient_query(db, governorates, kindergarten_ids, search_term)
        parent_count_stmt = select(func.count()).select_from(parent_query.subquery())
        total += db.execute(parent_count_stmt).scalar_one()

    return total


def _resolve_parent_governorates(db: Session, parent_ids: List[int]) -> Dict[int, List[str]]:
    """Return a map of parent user IDs to the governorates associated with them."""
    if not parent_ids:
        return {}

    governorates_map: Dict[int, List[str]] = defaultdict(list)

    enrollment_rows = db.query(
        models.ParentProfile.user_id,
        models.Kindergarten.governorate
    ).join(
        models.Child,
        models.Child.parent_id == models.ParentProfile.id
    ).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.Child.id
    ).join(
        models.Kindergarten,
        models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id
    ).filter(
        models.ParentProfile.user_id.in_(parent_ids),
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).distinct().all()

    for user_id, governorate in enrollment_rows:
        if governorate:
            governorates_map[user_id].append(governorate)

    profile_rows = db.query(
        models.ParentProfile.user_id,
        models.ParentProfile.home_governorate
    ).filter(
        models.ParentProfile.user_id.in_(parent_ids)
    ).all()

    for user_id, home_governorate in profile_rows:
        if home_governorate:
            governorates_map[user_id].append(home_governorate)

    return {
        user_id: list(dict.fromkeys(governorates))
        for user_id, governorates in governorates_map.items()
    }


def _parent_matches_governorates(
    db: Session,
    parent_user_id: int,
    target_governorates: List[str]
) -> bool:
    """
    Checks if a parent user is associated with any of the target governorates.
    A parent is associated if their home_governorate matches or any of their
    active enrollments' kindergartens are in the target governorates.
    """
    if not target_governorates:
        return False

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == parent_user_id
    ).first()

    if not parent_profile:
        return False

    # Check home_governorate
    if parent_profile.home_governorate and parent_profile.home_governorate in target_governorates:
        return True

    # Check enrolled kindergartens' governorates
    kindergarten_governorates_count = db.query(models.Kindergarten.governorate).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    ).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id
    ).filter(
        models.Child.parent_id == parent_profile.id,
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
        models.Kindergarten.governorate.in_(target_governorates)
    ).count()

    return kindergarten_governorates_count > 0


def _build_recipient_breakdowns(
    db: Session,
    user_ids: List[int]
) -> Tuple[Dict[str, int], Dict[str, int], Dict[int, int]]:
    """Return role, governorate, and kindergarten counts for the given users."""
    if not user_ids:
        return {}, {}, {}

    rows = db.query(
        models.User.id,
        models.User.role,
        models.User.kindergarten_id
    ).filter(models.User.id.in_(user_ids)).all()

    role_counts: Counter = Counter()
    governorate_counts: Counter = Counter()
    kindergarten_counts: Counter = Counter()
    parent_ids: List[int] = []
    kindergarten_ids: Set[int] = set()

    for user_id, role, kg_id in rows:
        role_counts[role.value] += 1
        if role == models.UserRole.PARENT:
            parent_ids.append(user_id)
        if kg_id:
            kindergarten_counts[kg_id] += 1
            kindergarten_ids.add(kg_id)

    parent_governorates = _resolve_parent_governorates(db, parent_ids) if parent_ids else {}
    for parent_id, gov_list in parent_governorates.items():
        seen: Set[str] = set()
        for gov in gov_list:
            if not gov or gov in seen:
                continue
            governorate_counts[gov] += 1
            seen.add(gov)

    if kindergarten_ids:
        kindergarten_map = {
            kg.id: kg
            for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kindergarten_ids)).all()
        }
        for kg_id, count in list(kindergarten_counts.items()):
            kg = kindergarten_map.get(kg_id)
            if kg and kg.governorate:
                governorate_counts[kg.governorate] += count

    return (
        dict(role_counts),
        dict(governorate_counts),
        dict(kindergarten_counts)
    )


def _normalize_recipient_roles(roles: Optional[List[AdminRecipientRole]]) -> List[models.UserRole]:
    normalized: List[models.UserRole] = []
    for role in roles or []:
        role_value = role.value if hasattr(role, "value") else str(role)
        role_value = role_value.strip().upper()
        try:
            role_enum = models.UserRole(role_value)
        except ValueError:
            raise validation_error("Invalid role", fields={"roles": "invalid"})
        if role_enum == models.UserRole.ADMIN:
            raise validation_error("Invalid role", fields={"roles": "invalid"})
        normalized.append(role_enum)
    return list(dict.fromkeys(normalized))


def _target_roles_for_mode(target: AdminMessageTarget) -> List[models.UserRole]:
    if target.mode == AdminMessageTargetMode.ALL_USERS:
        return [models.UserRole.MANAGER, models.UserRole.SUPERVISOR, models.UserRole.PARENT]
    if target.mode == AdminMessageTargetMode.ALL_MANAGERS:
        return [models.UserRole.MANAGER]
    if target.mode == AdminMessageTargetMode.ALL_SUPERVISORS:
        return [models.UserRole.SUPERVISOR]
    if target.mode == AdminMessageTargetMode.ALL_PARENTS:
        return [models.UserRole.PARENT]
    roles = _normalize_recipient_roles(target.roles)
    if not roles:
        raise validation_error("Recipient roles are required", fields={"roles": "required"})
    return roles


def _resolve_admin_recipient_ids(
    db: Session,
    roles: List[models.UserRole],
    governorates: Optional[List[str]] = None,
    kindergarten_ids: Optional[List[int]] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None
) -> List[int]:
    recipient_ids: List[int] = []
    seen: Set[int] = set()
    governorates = governorates or []
    kindergarten_ids = kindergarten_ids or []
    search_term = (search or "").strip()
    effective_limit = limit if limit and limit > 0 else None

    def _collect_rows(rows) -> bool:
        for row in rows:
            uid = row[0]
            if uid in seen:
                continue
            seen.add(uid)
            recipient_ids.append(uid)
            if effective_limit and len(recipient_ids) >= effective_limit:
                return True
        return False

    staff_roles = [role for role in roles if role in {models.UserRole.MANAGER, models.UserRole.SUPERVISOR}]
    if staff_roles:
        staff_query = _build_staff_recipient_query(db, roles, governorates, kindergarten_ids, search_term).order_by(models.User.id)
        if effective_limit:
            remaining = effective_limit - len(recipient_ids)
            if remaining <= 0:
                return sorted(recipient_ids)
            staff_query = staff_query.limit(remaining)
        if _collect_rows(staff_query.all()):
            return sorted(recipient_ids)

    if models.UserRole.PARENT in roles:
        parent_query = _build_parent_recipient_query(db, governorates, kindergarten_ids, search_term).order_by(models.User.id)
        if effective_limit:
            remaining = effective_limit - len(recipient_ids)
            if remaining <= 0:
                return sorted(recipient_ids)
            parent_query = parent_query.limit(remaining)
        _collect_rows(parent_query.all())

    return sorted(recipient_ids)


def _fetch_admin_recipient_summaries(db: Session, user_ids: List[int]) -> List[AdminRecipientSummary]:
    if not user_ids:
        return []

    users = db.query(models.User).filter(models.User.id.in_(user_ids)).all()
    user_map = {user.id: user for user in users}

    parent_ids = [user.id for user in users if user.role == models.UserRole.PARENT]
    parent_profiles = {}
    if parent_ids:
        parent_profiles = {
            profile.user_id: profile
            for profile in db.query(models.ParentProfile).filter(models.ParentProfile.user_id.in_(parent_ids)).all()
        }

    parent_kindergartens: Dict[int, List[str]] = {}
    parent_governorates = _resolve_parent_governorates(db, parent_ids) if parent_ids else {}
    if parent_ids:
        rows = db.query(
            models.ParentProfile.user_id,
            models.Kindergarten.name_ar,
            models.Kindergarten.name_en
        ).join(
            models.Child,
            models.Child.parent_id == models.ParentProfile.id
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).join(
            models.Kindergarten,
            models.Kindergarten.id == models.EnrollmentApplication.kindergarten_id
        ).filter(
            models.ParentProfile.user_id.in_(parent_ids),
            models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
        ).all()

        for user_id, name_ar, name_en in rows:
            label = name_ar or name_en or ""
            if label:
                parent_kindergartens.setdefault(user_id, []).append(label)

    kindergarten_ids = {user.kindergarten_id for user in users if user.kindergarten_id}
    kindergarten_map = {}
    if kindergarten_ids:
        kindergarten_map = {
            kg.id: kg
            for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kindergarten_ids)).all()
        }

    summaries: List[AdminRecipientSummary] = []
    for user_id in user_ids:
        user = user_map.get(user_id)
        if not user:
            continue
        display_name = user.username
        phone = None
        kindergarten_id = user.kindergarten_id
        kindergarten_name = None
        governorate = None

        if user.role == models.UserRole.PARENT:
            profile = parent_profiles.get(user.id)
            if profile:
                name_parts = [profile.first_name, profile.second_name, profile.last_name]
                display_name = " ".join(part for part in name_parts if part)
                phone = profile.phone_number
                governorates = parent_governorates.get(user.id) or []
                governorate = ", ".join(dict.fromkeys(governorates)) if governorates else profile.home_governorate
                kg_names = parent_kindergartens.get(user.id) or []
                kindergarten_name = ", ".join(dict.fromkeys(kg_names)) if kg_names else None
        else:
            kg = kindergarten_map.get(user.kindergarten_id)
            if kg:
                kindergarten_name = kg.name_ar or kg.name_en
                governorate = kg.governorate

        summaries.append(AdminRecipientSummary(
            id=user.id,
            display_name=display_name or user.username,
            role=user.role.value,
            email=user.email,
            phone=phone,
            kindergarten_id=kindergarten_id,
            kindergarten_name=kindergarten_name,
            governorate=governorate
        ))

    return summaries


@router.get("/admin/message-recipients", response_model=AdminRecipientListResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_message_recipients(
    request: Request,
    roles: Optional[List[str]] = Query(None),
    governorates: Optional[List[str]] = Query(None),
    kindergarten_ids: Optional[List[int]] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    role_values = _normalize_recipient_roles(roles)
    if not role_values:
        role_values = [models.UserRole.MANAGER, models.UserRole.SUPERVISOR, models.UserRole.PARENT]

    governorate_values = _normalize_governorates(governorates)
    kindergarten_id_values = _dedupe_int_list(kindergarten_ids)
    if kindergarten_id_values:
        ensure_kindergartens_exist(db, kindergarten_id_values)

    search_term = (search or "").strip()
    if not search_term:
        search_term = None

    recipient_ids = _resolve_admin_recipient_ids(
        db=db,
        roles=role_values,
        governorates=governorate_values,
        kindergarten_ids=kindergarten_id_values,
        search=search_term
    )

    total = _count_admin_recipients(
        db=db,
        roles=role_values,
        governorates=governorate_values,
        kindergarten_ids=kindergarten_id_values,
        search=search_term
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    page_ids = recipient_ids[offset:offset + page_size]
    items = _fetch_admin_recipient_summaries(db, page_ids)

    return AdminRecipientListResponse(
        items=items,
        pagination=AdminPaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )
    )


@router.post("/admin/messages", status_code=status.HTTP_201_CREATED, response_model=AdminMessageResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def create_admin_message(
    request: Request,
    payload: AdminMessageCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    _validate_csrf_token(request)
    subject = (payload.subject or "").strip()
    message_body = (payload.message_body or "").strip()
    if not subject:
        raise validation_error("Subject is required", fields={"subject": "required"})
    if not message_body:
        raise validation_error("Message body is required", fields={"message_body": "required"})

    subject = validators.sanitize_input(subject)
    message_body = validators.sanitize_input(message_body)

    target = payload.target
    roles = _target_roles_for_mode(target)
    governorate_values = _normalize_governorates(target.governorates)
    canonical_governorates = _canonical_governorates(target.governorates)
    kindergarten_id_values = _dedupe_int_list(target.kindergarten_ids)

    if target.mode == AdminMessageTargetMode.GOVERNORATE:
        if not canonical_governorates:
            raise validation_error("Governorate is required", fields={"governorates": "required"})
    if target.mode == AdminMessageTargetMode.KINDERGARTENS:
        if not kindergarten_id_values:
            raise validation_error("Kindergarten selection is required", fields={"kindergarten_ids": "required"})
    if kindergarten_id_values:
        ensure_kindergartens_exist(db, kindergarten_id_values)

    search_term = (target.search or "").strip()
    if not search_term:
        search_term = None

    total_recipients = _count_admin_recipients(
        db=db,
        roles=roles,
        governorates=governorate_values,
        kindergarten_ids=kindergarten_id_values,
        search=search_term
    )

    if total_recipients == 0:
        raise validation_error("No matching recipients found", fields={"recipients": "empty"})
    if total_recipients > settings.MAX_MESSAGE_RECIPIENTS:
        raise validation_error(
            f"Too many recipients ({total_recipients}). Maximum allowed: {settings.MAX_MESSAGE_RECIPIENTS}",
            fields={"recipients": "too_many"}
        )

    recipient_ids = _resolve_admin_recipient_ids(
        db=db,
        roles=roles,
        governorates=governorate_values,
        kindergarten_ids=kindergarten_id_values,
        search=search_term,
        limit=settings.MAX_MESSAGE_RECIPIENTS
    )

    target_kindergarten_id = None
    if target.mode == AdminMessageTargetMode.KINDERGARTENS and len(kindergarten_id_values) == 1:
        target_kindergarten_id = kindergarten_id_values[0]

    message = models.Message(
        thread_type=models.MessageThreadType.ANNOUNCEMENT,
        sender_id=current_user.id,
        kindergarten_id=target_kindergarten_id,
        subject=subject,
        message_body=message_body,
        recipient_id=None,
        allow_replies=payload.allow_replies,
        target_mode=target.mode.value,
        target_roles=[role.value for role in roles],
        target_governorates=canonical_governorates or None,
        target_kindergarten_ids=kindergarten_id_values or None,
        target_search=search_term,
        recipient_count=len(recipient_ids)
    )

    warnings: List[str] = []
    chunk_size = 500
    try:
        db.add(message)
        db.flush()
        message.thread_id = message.id
        recipients = [
            models.MessageRecipient(
                message_id=message.id,
                recipient_user_id=recipient_id,
                status="queued"
            )
            for recipient_id in recipient_ids
        ]
        for start in range(0, len(recipients), chunk_size):
            db.bulk_save_objects(recipients[start:start + chunk_size])
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to persist admin message: %s", exc)
        raise APIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to create message",
            details={"reason": "Unable to write message to the database"}
        )
    else:
        db.refresh(message)

    log_audit_event(
        db=db,
        action="ADMIN_MESSAGE_SENT",
        actor=current_user,
        target_type="Message",
        target_ids=message.id,
        metadata={
            "recipient_count": len(recipient_ids),
            "target": {
                "mode": target.mode.value,
                "roles": [role.value for role in roles],
                "governorates": canonical_governorates,
                "kindergarten_ids": kindergarten_id_values,
                "search": search_term
            }
        },
        sensitivity_level=2
    )

    recipient_users = db.query(models.User).filter(models.User.id.in_(recipient_ids)).all()
    try:
        notifications_enabled = create_message_notifications(db, message, recipient_users)
        if notifications_enabled and recipient_users:
            log_audit_event(
                db=db,
                action="MESSAGE_NOTIFICATIONS_QUEUED",
                actor=current_user,
                target_type="Message",
                target_ids=message.id,
                metadata={"recipient_count": len(recipient_users)},
                sensitivity_level=1
            )
        if not notifications_enabled:
            warnings.append("إشعارات الرسالة معطلة؛ سيتم مراجعة الحالة لاحقاً.")
            log_audit_event(
                db=db,
                action="MESSAGE_NOTIFICATIONS_SKIPPED",
                actor=current_user,
                target_type="Message",
                target_ids=message.id,
                metadata={"reason": "notifications_disabled"},
                sensitivity_level=1
            )
    except (SQLAlchemyError, RuntimeError, TypeError, AttributeError) as exc:
        logger.warning("Failed to enqueue notifications for message %s: %s", message.id, exc)
        warnings.append("فشل نظام الإشعارات؛ الرجاء التحقق يدوياً.")

    return AdminMessageResponse(
        id=message.id,
        thread_type=message.thread_type.value,
        subject=message.subject,
        message_body=message.message_body,
        created_at=message.created_at,
        recipient_count=len(recipient_ids),
        warnings=warnings
    )


# =============================================================================
# Admin Messaging - Additional Endpoints (Preview & Options)
# =============================================================================

class AdminRecipientPreviewResponse(BaseModel):
    """Response for recipient preview endpoint"""
    total_count: int
    has_more: bool = False
    sample_recipients: List[AdminRecipientSummary] = []
    by_role: Dict[str, int] = {}
    by_governorate: Optional[Dict[str, int]] = None
    by_kindergarten: Optional[Dict[int, int]] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total_count": 150,
            "has_more": True,
            "by_role": {"PARENT": 120, "MANAGER": 15, "SUPERVISOR": 15},
            "by_governorate": {"عمان": 80, "إربد": 70},
            "by_kindergarten": {"12": 40, "21": 50},
            "sample_recipients": [
                {"id": 42, "display_name": "أحمد أحمد", "role": "PARENT", "email": "ahmed@test.com", "governorate": "عمان"}
            ]
        }
    })


class GovernorateOption(BaseModel):
    """Governorate option for dropdown"""
    id: str
    name_ar: str
    name_en: Optional[str] = None


class GovernorateOptionsResponse(BaseModel):
    """Response containing governorate options"""
    governorates: List[GovernorateOption]


@router.get("/admin/options/governorates", response_model=GovernorateOptionsResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_governorate_options(
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get list of available governorates for message targeting.
    Admin only endpoint.
    """
    # Get unique governorates from active kindergartens
    governorate_rows = db.query(
        models.Kindergarten.governorate
    ).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).distinct().all()

    normalized_govs: Set[str] = set()
    for row in governorate_rows:
        gov = row[0]
        if not gov:
            continue
        try:
            normalized = validators.validate_jordan_governorate(gov)
        except validators.ValidationError:
            continue
        normalized_govs.add(normalized)

    sorted_govs = sorted(normalized_govs)
    options = []
    for gov in sorted_govs:
        english_label = None
        if gov in settings.JORDAN_GOVERNORATES:
            idx = settings.JORDAN_GOVERNORATES.index(gov)
            if idx < len(settings.JORDAN_GOVERNORATES_ENGLISH):
                english_label = settings.JORDAN_GOVERNORATES_ENGLISH[idx]
        options.append(GovernorateOption(
            id=gov,
            name_ar=gov,
            name_en=english_label or gov
        ))

    return GovernorateOptionsResponse(governorates=options)


@router.get("/admin/message-recipients/preview", response_model=AdminRecipientPreviewResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def preview_message_recipients(
    request: Request,
    mode: AdminMessageTargetMode,
    roles: Optional[List[str]] = Query(None),
    governorates: Optional[List[str]] = Query(None),
    kindergarten_ids: Optional[List[int]] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=settings.MAX_PAGE_SIZE),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Preview recipient count and sample recipients before sending a message.
    Admin only endpoint.
    """
    if mode == AdminMessageTargetMode.ALL_USERS:
        role_values = [models.UserRole.MANAGER, models.UserRole.SUPERVISOR, models.UserRole.PARENT]
    elif mode == AdminMessageTargetMode.ALL_MANAGERS:
        role_values = [models.UserRole.MANAGER]
    elif mode == AdminMessageTargetMode.ALL_SUPERVISORS:
        role_values = [models.UserRole.SUPERVISOR]
    elif mode == AdminMessageTargetMode.ALL_PARENTS:
        role_values = [models.UserRole.PARENT]
    elif roles:
        role_values = _normalize_recipient_roles(roles)
    else:
        raise validation_error("Roles are required for this targeting mode", fields={"roles": "required"})

    governorate_values = _normalize_governorates(governorates) if governorates else []
    kindergarten_id_values = _dedupe_int_list(kindergarten_ids) if kindergarten_ids else []

    if mode == AdminMessageTargetMode.KINDERGARTENS and not kindergarten_id_values:
        raise validation_error("Kindergarten selection is required", fields={"kindergarten_ids": "required"})
    if mode == AdminMessageTargetMode.GOVERNORATE and not governorate_values:
        raise validation_error("Governorate is required", fields={"governorates": "required"})

    if kindergarten_id_values:
        ensure_kindergartens_exist(db, kindergarten_id_values)

    search_term = (search or "").strip() if search else None
    total_count = _count_admin_recipients(
        db=db,
        roles=role_values,
        governorates=governorate_values,
        kindergarten_ids=kindergarten_id_values,
        search=search_term
    )

    recipient_ids = _resolve_admin_recipient_ids(
        db=db,
        roles=role_values,
        governorates=governorate_values if governorate_values else None,
        kindergarten_ids=kindergarten_id_values if kindergarten_id_values else None,
        search=search_term,
        limit=settings.MAX_MESSAGE_RECIPIENTS
    )

    sample_ids = recipient_ids[:5]
    sample_recipients = _fetch_admin_recipient_summaries(db, sample_ids)

    role_breakdown, governorate_breakdown, kindergarten_breakdown = _build_recipient_breakdowns(
        db, recipient_ids
    )

    target_metadata = {
        "mode": mode.value,
        "roles": [role.value for role in role_values],
        "governorates": governorate_values or None,
        "kindergarten_ids": kindergarten_id_values or None,
        "search": search_term
    }

    log_audit_event(
        db=db,
        action="ADMIN_MESSAGE_PREVIEW",
        actor=current_user,
        target_type="Preview",
        target_ids=None,
        metadata={
            "recipient_count": total_count,
            "target": target_metadata
        },
        sensitivity_level=1
    )

    return AdminRecipientPreviewResponse(
        total_count=total_count,
        has_more=page * page_size < total_count,
        sample_recipients=sample_recipients,
        by_role=role_breakdown,
        by_governorate=governorate_breakdown or None,
        by_kindergarten=kindergarten_breakdown or None
    )


@router.post("/admin/messages/preview", response_model=AdminRecipientListResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def preview_admin_message_post(
    request: Request,
    payload: AdminMessagePreviewRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    target = payload.target
    roles = _target_roles_for_mode(target)
    governorate_values = _normalize_governorates(target.governorates)
    canonical_governorates = _canonical_governorates(target.governorates)
    kindergarten_id_values = _dedupe_int_list(target.kindergarten_ids)

    if target.mode == AdminMessageTargetMode.GOVERNORATE:
        if not canonical_governorates:
            raise validation_error("Governorate is required", fields={"governorates": "required"})
    if target.mode == AdminMessageTargetMode.KINDERGARTENS and not kindergarten_id_values:
        raise validation_error("Kindergarten selection is required", fields={"kindergarten_ids": "required"})

    if kindergarten_id_values:
        ensure_kindergartens_exist(db, kindergarten_id_values)

    search_term = (target.search or "").strip()
    if not search_term:
        search_term = None

    recipient_ids = _resolve_admin_recipient_ids(
        db=db,
        roles=roles,
        governorates=governorate_values if governorate_values else None,
        kindergarten_ids=kindergarten_id_values if kindergarten_id_values else None,
        search=search_term,
        limit=settings.MAX_MESSAGE_RECIPIENTS
    )

    total = len(recipient_ids)
    page = max(1, payload.page)
    page_size = max(1, min(payload.page_size, settings.MAX_PAGE_SIZE))
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    offset = (page - 1) * page_size
    page_ids = recipient_ids[offset:offset + page_size]
    items = _fetch_admin_recipient_summaries(db, page_ids)

    target_metadata = {
        "mode": target.mode.value,
        "roles": [role.value for role in roles],
        "governorates": governorate_values or None,
        "kindergarten_ids": kindergarten_id_values or None,
        "search": search_term
    }

    log_audit_event(
        db=db,
        action="ADMIN_MESSAGE_PREVIEW",
        actor=current_user,
        target_type="Preview",
        target_ids=None,
        metadata={
            "recipient_count": total,
            "target": target_metadata
        },
        sensitivity_level=1
    )

    return AdminRecipientListResponse(
        items=items,
        pagination=AdminPaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, total_pages),
            has_next=page < total_pages,
            has_prev=page > 1
        )
    )


@router.get("/admin/options/kindergartens")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_kindergarten_options(
    request: Request,
    governorate: Optional[str] = Query(None),
    status: Optional[models.KindergartenStatus] = None,
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=500),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get list of kindergartens for message targeting.
    Supports filtering by governorate, status, and search term.
    Admin only endpoint.
    """
    query = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == (status or models.KindergartenStatus.ACTIVE)
    )

    if governorate:
        try:
            gov_normalized = validators.validate_jordan_governorate(governorate)
            query = query.filter(models.Kindergarten.governorate == gov_normalized)
        except validators.ValidationError:
            pass  # Ignore invalid governorate in filter

    if search:
        search = search[:100]
        search_term = f"%{search}%"
        query = query.filter(or_(
            models.Kindergarten.name_ar.ilike(search_term),
            models.Kindergarten.name_en.ilike(search_term),
            models.Kindergarten.city.ilike(search_term),
            models.Kindergarten.contact_phone.ilike(search_term)
        ))

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    kindergartens = query.order_by(
        models.Kindergarten.governorate,
        models.Kindergarten.name_ar
    ).offset(offset).limit(page_size).all()

    return {
        "kindergartens": [
            {
                "id": kg.id,
                "name": kg.name_ar or kg.name_en or f"روضة {kg.id}",
                "name_ar": kg.name_ar,
                "name_en": kg.name_en,
                "governorate": kg.governorate,
                "city": kg.city,
                "status": kg.status.value,
                "contact_phone": kg.contact_phone
            }
            for kg in kindergartens
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size)
        }
    }


# =============================================================================
# Performance Monitoring Endpoints
# =============================================================================

@router.get("/performance/metrics")
def get_performance_metrics(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive performance metrics (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from performance_monitor import performance_monitor, get_performance_report

    try:
        return get_performance_report()
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance metrics")


@router.get("/performance/requests")
def get_request_metrics(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get request performance metrics (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from performance_monitor import performance_monitor

    try:
        return performance_monitor.get_request_metrics()
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to get request metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve request metrics")


@router.get("/performance/database")
def get_database_metrics(
    limit: int = Query(100, description="Number of recent queries to return"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get database query performance metrics (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from performance_monitor import performance_monitor

    try:
        return {
            "recent_queries": performance_monitor.get_db_metrics(limit),
            "slow_queries": performance_monitor.get_slow_queries(2.0)
        }
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to get database metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve database metrics")


@router.get("/performance/system")
def get_system_metrics(
    limit: int = Query(50, description="Number of recent system metrics to return"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system performance metrics (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from performance_monitor import performance_monitor

    try:
        return performance_monitor.get_system_metrics(limit)
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system metrics")


# =============================================================================
# Admin Dashboard Models
# =============================================================================

class DashboardKPICard(BaseModel):
    """KPI card data for dashboard"""
    title: str
    value: Union[str, int, float]
    change: Optional[float] = None
    change_type: Optional[str] = None  # 'positive', 'negative', 'neutral'
    trend: Optional[str] = None  # 'up', 'down', 'stable'
    status: Optional[str] = None  # 'good', 'warning', 'critical'
    icon: Optional[str] = None

# class DashboardChartPoint(BaseModel):
#     """Data point for dashboard charts"""
#     date: str
#     value: Union[int, float]
#     label: Optional[str] = None

# class DashboardActivityItem(BaseModel):
#     """Recent activity item"""
#     id: str
#     type: str  # 'user_login', 'data_submission', 'alert', 'system_event'
#     title: str
#     description: str
#     timestamp: str
#     user: Optional[str] = None
#     severity: Optional[str] = None  # 'info', 'warning', 'error', 'success'

# class DashboardAlert(BaseModel):
#     """System alert for dashboard"""
#     id: str
#     title: str
#     message: str
#     severity: str  # 'info', 'warning', 'error', 'critical'
#     timestamp: str
#     acknowledged: bool = False
#     category: str  # 'system', 'security', 'performance', 'data_quality'

class DashboardSummary(BaseModel):
    """Summary statistics for admin dashboard"""
    attendance_today: int = 0
    pending_applications: int = 0
    pending_daily_reports: int = 0
    recent_incidents: int = 0
    attendance_rate: float = 0.0

class DashboardSystemOverview(BaseModel):
    """System overview statistics"""
    total_kindergartens: int = 0
    active_kindergartens: int = 0
    total_users: int = 0

class DashboardKindergarten(BaseModel):
    """Kindergarten data for dashboard table"""
    id: int
    name_ar: Optional[str] = None
    name_en: Optional[str] = None
    status: str
    license_status: str
    governorate: Optional[str] = None
    city: Optional[str] = None
    enrollments: int = 0
    attendance_today: int = 0
    pending_reports: int = 0
    capacity_utilization: float = 0.0
    total_children: int = 0
    active_children: int = 0
    last_report_date: Optional[str] = None

class DashboardChartPoint(BaseModel):
    """Data point for dashboard charts"""
    date: str
    value: Union[int, float]
    label: Optional[str] = None

class DashboardCharts(BaseModel):
    """Charts data for dashboard"""
    attendance: List[DashboardChartPoint] = []
    enrollment: Dict[str, Any] = {}

class DashboardAlert(BaseModel):
    """System alert for dashboard"""
    id: str
    title: str
    message: str
    severity: str  # 'info', 'warning', 'error', 'critical'
    timestamp: str
    category: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    kindergarten_id: Optional[int] = None

class AdminDashboardResponse(BaseModel):
    """Complete admin dashboard response"""
    summary: DashboardSummary
    system_overview: DashboardSystemOverview
    kindergartens: List[DashboardKindergarten]
    charts: DashboardCharts
    alerts: List[DashboardAlert]
    kpi_cards: List[DashboardKPICard]
    generated_at: str


# =============================================================================
# Admin Dashboard Endpoint
# =============================================================================

@router.get("/admin/dashboard", response_model=AdminDashboardResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_admin_dashboard(
    request: Request,
    period_days: int = Query(30, description="Number of days to analyze", ge=1, le=90),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get comprehensive admin dashboard data with system overview, KPIs, charts, and alerts."""
    now = datetime.now(timezone.utc)
    today = date.today()
    cache_key = f"dashboard:admin:v2:period_{period_days}:date_{today.isoformat()}"
    cached_payload = _admin_dashboard_cache_get(cache_key)
    if isinstance(cached_payload, dict):
        return AdminDashboardResponse(**cached_payload)

    week_ago = today - timedelta(days=7)
    today_start = datetime.combine(today, datetime.min.time())

    total_users = db.query(func.count(models.User.id)).scalar() or 0
    total_kindergartens = db.query(func.count(models.Kindergarten.id)).scalar() or 0
    active_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).scalar() or 0
    active_users_today = db.query(func.count(func.distinct(models.AuditLog.user_id))).filter(
        models.AuditLog.action == "LOGIN_SUCCESS",
        models.AuditLog.user_id.isnot(None),
        models.AuditLog.created_at >= today_start,
    ).scalar() or 0

    pending_applications = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW
    ).scalar() or 0
    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.status == models.DailyReportStatus.SUBMITTED
    ).scalar() or 0
    recent_incidents = db.query(func.count(models.Incident.id)).filter(
        func.date(models.Incident.occurred_at) >= week_ago
    ).scalar() or 0
    attendance_today = db.query(func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date == today,
        models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
    ).scalar() or 0
    active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar() or 0

    attendance_rate = (attendance_today / active_enrollments * 100.0) if active_enrollments > 0 else 0.0

    kpi_cards = [
        DashboardKPICard(title="إجمالي المستخدمين", value=total_users, icon="users", status="good"),
        DashboardKPICard(title="المستخدمون النشطون اليوم", value=active_users_today, icon="user-check", status="good"),
        DashboardKPICard(title="إجمالي الروضات", value=total_kindergartens, icon="building", status="good"),
        DashboardKPICard(
            title="التقارير اليومية المعلقة",
            value=pending_reports,
            icon="journal-text",
            status="warning" if pending_reports > 0 else "good",
        ),
    ]

    summary = DashboardSummary(
        attendance_today=attendance_today,
        pending_applications=pending_applications,
        pending_daily_reports=pending_reports,
        recent_incidents=recent_incidents,
        attendance_rate=round(attendance_rate, 1),
    )

    system_overview = DashboardSystemOverview(
        total_kindergartens=total_kindergartens,
        active_kindergartens=active_kindergartens,
        total_users=total_users,
    )

    kindergartens_list: List[DashboardKindergarten] = []
    all_kindergartens = db.query(models.Kindergarten).all()
    kg_ids = [kg.id for kg in all_kindergartens]

    # Batch-load all per-kindergarten stats to avoid N+1 queries
    kg_enrollment_counts = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id),
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all()
    ) if kg_ids else {}

    kg_attendance_counts = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.AttendanceLog.id),
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.AttendanceLog.date == today,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all()
    ) if kg_ids else {}

    kg_pending_report_counts = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.DailyReport.id),
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.DailyReport.child_id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.DailyReport.status == models.DailyReportStatus.SUBMITTED,
        ).group_by(models.EnrollmentApplication.kindergarten_id).all()
    ) if kg_ids else {}

    kg_capacities = dict(
        db.query(
            models.Class.kindergarten_id,
            func.sum(models.Class.capacity_total),
        ).filter(
            models.Class.kindergarten_id.in_(kg_ids),
            models.Class.is_active.is_(True),
        ).group_by(models.Class.kindergarten_id).all()
    ) if kg_ids else {}

    kg_last_report_dates = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.max(models.DailyReport.date),
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.DailyReport.child_id,
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
        ).group_by(models.EnrollmentApplication.kindergarten_id).all()
    ) if kg_ids else {}

    for kg in all_kindergartens:
        kg_enrollments = kg_enrollment_counts.get(kg.id, 0)
        kg_attendance = kg_attendance_counts.get(kg.id, 0)
        kg_pending_reports_count = kg_pending_report_counts.get(kg.id, 0)
        kg_capacity = kg_capacities.get(kg.id, 0) or 0
        last_report_date = kg_last_report_dates.get(kg.id)

        license_status = "valid"
        if kg.license_valid_until:
            days_to_expiry = (kg.license_valid_until - today).days
            if days_to_expiry < 0:
                license_status = "expired"
            elif days_to_expiry < 30:
                license_status = "expiring_soon"

        kindergartens_list.append(
            DashboardKindergarten(
                id=kg.id,
                name_ar=kg.name_ar,
                name_en=kg.name_en,
                status=kg.status.value,
                license_status=license_status,
                governorate=kg.governorate,
                city=kg.city,
                enrollments=kg_enrollments,
                attendance_today=kg_attendance,
                pending_reports=kg_pending_reports_count,
                capacity_utilization=round((kg_enrollments / kg_capacity) * 100.0, 1) if kg_capacity > 0 else 0.0,
                total_children=kg_enrollments,
                active_children=kg_enrollments,
                last_report_date=last_report_date.isoformat() if last_report_date else None,
            )
        )

    chart_days = max(7, min(period_days, 90))
    chart_start_date = today - timedelta(days=chart_days - 1)
    # Single query for all chart days instead of N+1
    daily_attendance_counts = dict(
        db.query(
            models.AttendanceLog.date,
            func.count(models.AttendanceLog.id),
        ).filter(
            models.AttendanceLog.date >= chart_start_date,
            models.AttendanceLog.date <= today,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        ).group_by(models.AttendanceLog.date).all()
    )
    attendance_chart: List[DashboardChartPoint] = []
    for i in range(chart_days):
        day_value = today - timedelta(days=(chart_days - 1 - i))
        day_count = daily_attendance_counts.get(day_value, 0)
        attendance_chart.append(DashboardChartPoint(date=day_value.isoformat(), value=day_count))

    enrollment_stats = db.query(
        models.EnrollmentApplication.status,
        func.count(models.EnrollmentApplication.id),
    ).group_by(models.EnrollmentApplication.status).all()
    enrollment_chart = {
        (status.value if hasattr(status, "value") else str(status)): count
        for status, count in enrollment_stats
    }

    charts = DashboardCharts(attendance=attendance_chart, enrollment=enrollment_chart)

    alerts: List[DashboardAlert] = []
    if pending_applications > 0:
        alerts.append(
            DashboardAlert(
                id="pending_applications",
                title="طلبات تسجيل بانتظار المراجعة",
                message=f"يوجد {pending_applications} طلب تسجيل يحتاج المراجعة.",
                severity="warning",
                timestamp=now.isoformat(),
                category="applications",
                type="طلبات التسجيل",
                priority="high" if pending_applications > 10 else "medium",
            )
        )

    if recent_incidents > 0:
        alerts.append(
            DashboardAlert(
                id="recent_incidents",
                title="حوادث مسجلة حديثاً",
                message=f"تم تسجيل {recent_incidents} حادث خلال آخر 7 أيام.",
                severity="error" if recent_incidents > 5 else "warning",
                timestamp=now.isoformat(),
                category="safety",
                type="السلامة",
                priority="high" if recent_incidents > 5 else "medium",
            )
        )

    expiring_licenses = db.query(models.Kindergarten).filter(
        models.Kindergarten.license_valid_until.isnot(None),
        models.Kindergarten.license_valid_until <= today + timedelta(days=30),
    ).all()
    for kg in expiring_licenses:
        days_to_expiry = (kg.license_valid_until - today).days
        alerts.append(
            DashboardAlert(
                id=f"license_expiry_{kg.id}",
                title="تنبيه صلاحية الترخيص",
                message=(
                    f"انتهت صلاحية ترخيص {kg.name_ar}."
                    if days_to_expiry < 0
                    else f"تنتهي صلاحية ترخيص {kg.name_ar} خلال {days_to_expiry} يوم."
                ),
                severity="error" if days_to_expiry < 0 else "warning",
                timestamp=now.isoformat(),
                category="compliance",
                type="الترخيص",
                priority="critical" if days_to_expiry < 0 else "high",
                kindergarten_id=kg.id,
            )
        )

    alerts = sorted(
        alerts,
        key=lambda alert: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(alert.priority or "medium", 4),
    )

    # Log dashboard access
    log_audit_event(
        db=db,
        action=AuditAction.ADMIN_DASHBOARD_VIEWED,
        actor=current_user,
        target_type="Dashboard",
        target_ids=None,
        metadata={
            "period_days": period_days,
            "kpi_count": len(kpi_cards)
        },
        sensitivity_level=2,
    )

    response_payload = AdminDashboardResponse(
        summary=summary,
        system_overview=system_overview,
        kindergartens=kindergartens_list,
        charts=charts,
        alerts=alerts,
        kpi_cards=kpi_cards,
        generated_at=now.isoformat()
    )
    _admin_dashboard_cache_set(cache_key, response_payload.model_dump(mode="json"))
    return response_payload


# =============================================================================
# Backup Management Endpoints
# =============================================================================

@router.post("/backup/create")
def create_backup(
    backup_type: str = Query("manual", description="Type of backup (manual, automated)"),
    include_uploads: bool = Query(True, description="Include uploaded files in backup"),
    include_config: bool = Query(True, description="Include configuration files in backup"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new backup (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from backup_manager import backup_manager

    try:
        # Create database backup
        db_backup = backup_manager.create_database_backup(backup_type)

        results = {"database": db_backup}

        if include_uploads:
            uploads_backup = backup_manager.create_uploads_backup(backup_type)
            results["uploads"] = uploads_backup

        if include_config:
            config_backup = backup_manager.create_config_backup(backup_type)
            results["config"] = config_backup

        # Log the backup creation
        log_audit_event(
            db, "BACKUP_CREATED", current_user, "Backup",
            metadata={"backup_type": backup_type, "components": list(results.keys())},
            sensitivity_level=2
        )

        return {
            "message": f"{backup_type.title()} backup created successfully",
            "backups": results
        }

    except HTTPException:
        raise
    except (OSError, IOError, SQLAlchemyError, ValueError) as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail="Backup creation failed")


@router.get("/backup/list")
def list_backups(
    backup_type: Optional[str] = Query(None, description="Filter by backup type (database, uploads, config)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all backups (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from backup_manager import backup_manager

    try:
        return backup_manager.list_backups(backup_type)
    except (OSError, IOError, ValueError, KeyError) as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail="Failed to list backups")


@router.post("/backup/restore/{backup_name}")
def restore_backup(
    backup_name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore from a backup (Admin only - DANGER: This will overwrite current data)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Sanitize backup_name to prevent path traversal
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        raise HTTPException(status_code=400, detail="Invalid backup name")

    from backup_manager import backup_manager

    try:
        # Validate backup exists and is valid
        if not backup_manager.validate_backup(backup_name):
            raise HTTPException(status_code=400, detail="Invalid or corrupted backup")

        metadata = backup_manager.get_backup_info(backup_name)
        if not metadata:
            raise HTTPException(status_code=404, detail="Backup not found")

        # Only allow database restores for now (safest option)
        if metadata["type"] != "database":
            raise HTTPException(
                status_code=400,
                detail="Only database backups can be restored via API. Contact system administrator for other restore types."
            )

        # Perform restore
        success = backup_manager.restore_database_backup(backup_name)

        if success:
            # Log the restore operation
            log_audit_event(
                db, "BACKUP_RESTORED", current_user, "Backup",
                metadata={"backup_name": backup_name},
                sensitivity_level=3
            )

            return {"message": f"Database successfully restored from backup: {backup_name}"}
        else:
            raise HTTPException(status_code=500, detail="Restore operation failed")

    except HTTPException:
        raise
    except (OSError, IOError, SQLAlchemyError, ValueError) as e:
        logger.error(f"Backup restore failed: {e}")
        raise HTTPException(status_code=500, detail="Restore failed due to an internal error")


@router.delete("/backup/{backup_name}")
def delete_backup(
    backup_name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a backup file (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Sanitize backup_name to prevent path traversal
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        raise HTTPException(status_code=400, detail="Invalid backup name")

    from backup_manager import backup_manager

    try:
        metadata = backup_manager.get_backup_info(backup_name)
        if not metadata:
            raise HTTPException(status_code=404, detail="Backup not found")

        backup_path = metadata.get("backup_path")
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)

        if backup_name in backup_manager.metadata:
            del backup_manager.metadata[backup_name]
            backup_manager._save_metadata()

        # Log the deletion
        log_audit_event(
            db, "BACKUP_DELETED", current_user, "Backup",
            metadata={"backup_name": backup_name},
            sensitivity_level=2
        )

        return {"message": f"Backup {backup_name} deleted successfully"}

    except HTTPException:
        raise
    except (OSError, IOError, ValueError, KeyError) as e:
        logger.error(f"Backup deletion failed: {e}")
        raise HTTPException(status_code=500, detail="Deletion failed")


@router.get("/backup/info/{backup_name}")
def get_backup_info(
    backup_name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific backup (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Sanitize backup_name to prevent path traversal
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        raise HTTPException(status_code=400, detail="Invalid backup name")

    from backup_manager import backup_manager

    try:
        metadata = backup_manager.get_backup_info(backup_name)
        if not metadata:
            raise HTTPException(status_code=404, detail="Backup not found")

        # Add validation status
        metadata_copy = metadata.copy()
        metadata_copy["is_valid"] = backup_manager.validate_backup(backup_name)

        return metadata_copy
    except HTTPException:
        raise
    except (OSError, IOError, KeyError, ValueError) as e:
        logger.error(f"Failed to get backup info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve backup info")


@router.post("/backup/cleanup")
def cleanup_old_backups(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clean up old backups beyond retention period (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from backup_manager import backup_manager

    try:
        backup_manager.cleanup_old_backups()

        # Log the cleanup
        log_audit_event(
            db, "BACKUP_CLEANUP", current_user, "Backup",
            metadata={"action": "cleanup_old_backups"},
            sensitivity_level=1
        )

        return {"message": "Old backups cleaned up successfully"}

    except HTTPException:
        raise
    except (OSError, IOError, ValueError, KeyError) as e:
        logger.error(f"Backup cleanup failed: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")


@router.post("/backup/validate/{backup_name}")
def validate_backup(
    backup_name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Validate a backup file integrity (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Sanitize backup_name to prevent path traversal
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        raise HTTPException(status_code=400, detail="Invalid backup name")

    from backup_manager import backup_manager

    try:
        is_valid = backup_manager.validate_backup(backup_name)

        return {
            "backup_name": backup_name,
            "is_valid": is_valid,
            "message": "Backup is valid" if is_valid else "Backup is corrupted or missing"
        }

    except HTTPException:
        raise
    except (OSError, IOError, ValueError, KeyError) as e:
        logger.error(f"Backup validation failed: {e}")
        raise HTTPException(status_code=500, detail="Validation failed")


# =============================================================================
# Kindergarten Excel Import
# =============================================================================

class KindergartenImportResult(BaseModel):
    """Result summary for kindergarten Excel import."""
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_empty: int = 0
    errors: List[Dict[str, Any]] = []
    total_rows: int = 0


@router.post("/kindergartens/import-excel", response_model=KindergartenImportResult)
def import_kindergartens_from_excel(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Preview without writing to DB"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import kindergartens from an Excel (.xlsx) file (Admin only).

    Expected columns in the first sheet:
      - Column A: اسم الروضة (عربي)  → name_ar
      - Column B: اسم الروضة (إنجليزي) → name_en
      - Column C: المحافظة           → governorate
      - Column D: المدينة            → city
      - Column E: المنطقة            → area
      - Column F: العنوان التفصيلي    → address_line
      - Column G: رقم الهاتف         → contact_phone
    """
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl is not installed on the server")

    # Enforce file size limit (10 MB)
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024
    try:
        contents = file.file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10 MB.")
        from io import BytesIO
        wb = openpyxl.load_workbook(BytesIO(contents), read_only=True)
        ws = wb.worksheets[0]  # Use first sheet
        rows = list(ws.iter_rows(min_row=2, values_only=True))  # skip header
        wb.close()
    except (OSError, IOError, KeyError, ValueError, IndexError) as e:
        logger.exception("Failed to read uploaded Excel file")
        raise HTTPException(status_code=400, detail="Could not read Excel file")

    # Build existing-kindergarten set for dedup
    existing = set()
    for kg in db.query(
        models.Kindergarten.name_ar,
        models.Kindergarten.governorate,
        models.Kindergarten.city,
    ).all():
        existing.add((kg.name_ar, kg.governorate, kg.city))

    result = KindergartenImportResult(total_rows=len(rows))
    row_errors: List[Dict[str, Any]] = []

    def _clean(val) -> str:
        return str(val).strip() if val is not None else ""

    for row_num, row in enumerate(rows, start=2):
        if len(row) < 7:
            row_errors.append({"row": row_num, "error": "Row has fewer than 7 columns"})
            continue

        name_ar = _clean(row[0])
        name_en = _clean(row[1])
        governorate = _clean(row[2]) or "غير محدد"
        city = _clean(row[3]) or "غير محدد"
        area = _clean(row[4]) or "غير محدد"
        address_line = _clean(row[5]) or "غير محدد"
        phone = _clean(row[6]) or "غير متوفر"

        if not name_ar:
            result.skipped_empty += 1
            continue

        key = (name_ar, governorate, city)
        if key in existing:
            result.skipped_duplicate += 1
            continue

        if not dry_run:
            try:
                kg = models.Kindergarten(
                    name_ar=name_ar,
                    name_en=name_en or None,
                    governorate=governorate,
                    city=city,
                    area=area,
                    address_line=address_line,
                    contact_phone=phone,
                    status=models.KindergartenStatus.ACTIVE,
                )
                db.add(kg)
            except (SQLAlchemyError, AttributeError, ValueError, KeyError) as exc:
                logger.error(f"Excel import row {row_num} error: {exc}")
                row_errors.append({"row": row_num, "error": "Failed to insert row"})
                continue

        existing.add(key)
        result.inserted += 1

    if not dry_run:
        try:
            db.commit()
        except (SQLAlchemyError, OSError) as e:
            db.rollback()
            logger.exception("Failed to commit kindergarten import")
            raise HTTPException(status_code=500, detail="Database commit failed")

    result.errors = row_errors
    logger.info(
        "Kindergarten Excel import: inserted=%d, dup=%d, empty=%d, errors=%d, dry_run=%s",
        result.inserted, result.skipped_duplicate, result.skipped_empty,
        len(row_errors), dry_run,
    )
    return result


# =============================================================================
# Governance — Daily Report KPI Endpoints
# =============================================================================

from governance_kpi_service import (
    compute_governance_funnel,
    compute_timeliness_metrics,
    compute_quality_metrics,
    compute_consistency_index,
    compute_fair_ranking,
    detect_low_performers,
    check_reminder_cooldown,
    send_governance_reminder,
)


class GovernanceReminderRequest(BaseModel):
    target_type: str  # "kindergarten" or "supervisor"
    target_id: int
    reminder_type: str = "low_submission_rate"


@router.get("/admin/governance/kpis")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
async def get_governance_kpis(
    request: Request,
    start_date: date = Query(..., description="Start date YYYY-MM-DD"),
    end_date: date = Query(..., description="End date YYYY-MM-DD"),
    kindergarten_id: Optional[int] = Query(None, description="Filter by kindergarten"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get governance funnel KPIs for daily report compliance monitoring."""
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="يجب أن يكون تاريخ النهاية أكبر من أو يساوي تاريخ البداية")

    funnel = compute_governance_funnel(db, start_date, end_date, kindergarten_id)
    timeliness = compute_timeliness_metrics(db, start_date, end_date, kindergarten_id)
    quality = compute_quality_metrics(db, start_date, end_date, kindergarten_id)
    consistency = compute_consistency_index(db, start_date, end_date, kindergarten_id)

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "funnel": funnel,
        "timeliness": timeliness,
        "quality": quality,
        "consistency": consistency,
    }


@router.get("/admin/governance/leaderboard")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
async def get_governance_leaderboard(
    request: Request,
    start_date: date = Query(..., description="Start date YYYY-MM-DD"),
    end_date: date = Query(..., description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get Bayesian-ranked kindergarten leaderboard for daily report compliance."""
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="يجب أن يكون تاريخ النهاية أكبر من أو يساوي تاريخ البداية")

    funnel = compute_governance_funnel(db, start_date, end_date)
    ranked = compute_fair_ranking(funnel, db)
    low_performers = detect_low_performers(funnel, db)

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "leaderboard": ranked,
        "low_performers": low_performers,
    }


@router.post("/admin/governance/reminders")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
async def send_governance_reminder_endpoint(
    request: Request,
    body: GovernanceReminderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Send a governance reminder to a kindergarten or supervisor."""
    if body.target_type not in ("kindergarten", "supervisor"):
        raise HTTPException(status_code=400, detail="قيمة target_type يجب أن تكون kindergarten أو supervisor")

    can_send, last_sent_at = check_reminder_cooldown(db, body.target_type, body.target_id)
    if not can_send:
        raise HTTPException(
            status_code=429,
            detail={
                "message": (
                    "لا يمكن إرسال تذكير الآن بسبب فترة التبريد. "
                    f"آخر إرسال كان عند {last_sent_at.isoformat() if last_sent_at else 'غير معروف'}"
                ),
                "cooldown_hours": settings.GOVERNANCE_REMINDER_COOLDOWN_HOURS,
                "last_sent_at": last_sent_at.isoformat() if last_sent_at else None,
            },
        )

    # Build metrics snapshot for the reminder payload
    today = date.today()
    week_ago = today - timedelta(days=7)
    kg_id = body.target_id if body.target_type == "kindergarten" else None
    funnel = compute_governance_funnel(db, week_ago, today, kg_id)
    metrics_snapshot = funnel.get("aggregate", {}) if not kg_id else funnel.get("per_kindergarten", {}).get(kg_id, {})

    reminder = send_governance_reminder(
        db=db,
        admin_user=current_user,
        target_type=body.target_type,
        target_id=body.target_id,
        reminder_type=body.reminder_type,
        metrics_snapshot=metrics_snapshot,
    )

    log_audit_event(
        db=db,
        action="GOVERNANCE_REMINDER_SENT",
        actor=current_user,
        target_type="GovernanceReminder",
        target_ids=reminder.id,
        after_state={"target_type": body.target_type, "target_id": body.target_id, "reminder_type": body.reminder_type},
        sensitivity_level=2,
    )

    return {
        "id": reminder.id,
        "target_type": reminder.target_type,
        "target_id": reminder.target_id,
        "reminder_type": reminder.reminder_type,
        "sent_at": reminder.sent_at.isoformat(),
        "cooldown_expires_at": reminder.cooldown_expires_at.isoformat(),
    }


@router.get("/admin/governance/reminders")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
async def list_governance_reminders(
    request: Request,
    target_type: Optional[str] = Query(None),
    target_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """List governance reminders with optional filters and pagination."""
    q = db.query(models.GovernanceReminder).order_by(models.GovernanceReminder.sent_at.desc())

    if target_type:
        q = q.filter(models.GovernanceReminder.target_type == target_type)
    if target_id is not None:
        q = q.filter(models.GovernanceReminder.target_id == target_id)

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "reminder_type": r.reminder_type,
                "sent_by": r.sent_by,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "cooldown_expires_at": r.cooldown_expires_at.isoformat() if r.cooldown_expires_at else None,
                "payload": r.payload,
            }
            for r in items
        ],
    }


# Kindergarten Import Routes
@router.post("/admin/kindergartens/import")
@limiter.limit("10/minute")
async def import_kindergartens(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload and import kindergartens from Excel file."""
    if current_user.role != models.UserRole.ADMIN:
        raise forbidden_error("Only admins can import kindergartens")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise validation_error("File must be Excel format (.xlsx or .xls)")

    # Create storage directory
    import_dir = os.path.join(settings.STATIC_DIR, "imports")
    os.makedirs(import_dir, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_filename = f"kindergartens_{timestamp}_{secrets.token_hex(4)}.xlsx"
    file_path = os.path.join(import_dir, stored_filename)

    # Save uploaded file
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except (OSError, IOError) as e:
        raise APIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message=f"Failed to save file: {str(e)}",
        )

    # Import data
    try:
        service = KindergartenImportService(db)
        result = service.import_from_excel(file_path, file.filename)

        # Log audit event
        log_audit_event(
            db=db,
            action="KINDERGARTEN_IMPORT",
            actor=current_user,
            target_type="Kindergarten",
            metadata={
                "filename": file.filename,
                "stored_filename": stored_filename,
                "imported_count": result.get("imported_count", 0),
                "updated_count": result.get("updated_count", 0),
                "skipped_count": result.get("skipped_count", 0),
                "error_count": len(result.get("errors", [])),
            },
            sensitivity_level=2,
        )

        return {
            "message": "Import completed",
            "result": result
        }

    except (SQLAlchemyError, OSError, IOError, ValueError) as e:
        # Clean up file on error
        if os.path.exists(file_path):
            os.remove(file_path)
        raise APIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message=f"Import failed: {str(e)}",
        )


@router.get("/admin/kindergartens/imported")
async def list_imported_kindergartens(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    governorate: str = Query(None),
    city: str = Query(None),
    search: str = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List imported kindergartens with filtering and pagination."""
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise forbidden_error("Access denied")

    service = KindergartenImportService(db)
    result = service.get_imported_kindergartens(
        page=page, per_page=per_page,
        governorate=governorate, city=city, search=search
    )

    return result


@router.get("/admin/imports/logs")
async def list_import_logs(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List import logs."""
    if current_user.role != models.UserRole.ADMIN:
        raise forbidden_error("Only admins can view import logs")

    service = KindergartenImportService(db)
    result = service.get_import_logs(page=page, per_page=per_page)

    return result


# =============================================================================
# Admin Incident Reporting Endpoints
# =============================================================================

@router.post("/admin/reports/incidents/generate")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def generate_incident_report(
    request: Request,
    scope_type: str = Form(...),
    kindergarten_id: Optional[int] = Form(None),
    governorate: Optional[str] = Form(None),
    period_type: str = Form(...),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Generate and save an incident report"""
    try:
        # Validate scope
        try:
            scope_enum = models.ReportScopeType(scope_type)
        except ValueError:
            raise validation_error("Invalid scope type")

        # Calculate date range
        from report_service import ReportService
        start_date, end_date = ReportService.calculate_date_range(period_type)

        # Generate metrics
        metrics = ReportService.generate_incident_report(
            scope_enum, start_date, end_date, kindergarten_id, governorate, db
        )

        # Create report record
        report = models.Report(
            report_type=models.ReportType.INCIDENT_SUMMARY,
            scope_type=scope_enum,
            kindergarten_id=kindergarten_id,
            governorate=governorate,
            start_date=start_date,
            end_date=end_date,
            metrics_json=metrics,
            created_by=current_user.id
        )

        db.add(report)
        db.commit()
        db.refresh(report)

        log_audit_event(
            db, "REPORT_GENERATED", current_user, "report",
            target_ids=report.id,
            metadata={
                "description": f"Generated incident report ID {report.id} for scope {scope_type}",
                "correlation_id": get_correlation_id()
            }
        )

        return JSONResponse({
            "success": True,
            "report_id": report.id,
            "message": "تم إنشاء التقرير بنجاح"
        })

    except HTTPException:
        db.rollback()
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to generate incident report: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/reports/incidents")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_incident_reports(
    request: Request,
    scope_filter: Optional[str] = Query(None, description="Filter by scope type: KINDERGARTEN, GOVERNORATE, ALL"),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List incident reports with filtering"""
    try:
        query = db.query(models.Report).filter(
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        )

        # Apply scope filters
        if scope_filter:
            try:
                scope_enum = models.ReportScopeType(scope_filter)
                query = query.filter(models.Report.scope_type == scope_enum)
            except ValueError:
                raise validation_error("Invalid scope filter")

        if kindergarten_id:
            query = query.filter(models.Report.kindergarten_id == kindergarten_id)

        if governorate:
            query = query.filter(models.Report.governorate == governorate)

        # Pagination
        total = query.count()
        reports = query.order_by(models.Report.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        # Format response
        report_list = []
        for report in reports:
            scope_name = ""
            if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
                scope_name = report.kindergarten.name_ar
            elif report.scope_type == models.ReportScopeType.GOVERNORATE:
                scope_name = report.governorate
            elif report.scope_type == models.ReportScopeType.ALL:
                scope_name = "جميع الروضات"

            report_list.append({
                "id": report.id,
                "title": f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
                "scope_type": report.scope_type.value,
                "scope_name": scope_name,
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
                "created_at": report.created_at.isoformat(),
                "created_by": report.creator.username if report.creator else "غير معروف",
                "total_incidents": report.metrics_json.get("total_incidents", 0)
            })

        return {
            "reports": report_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to list incident reports: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/reports/incidents/{report_id}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_incident_report_detail(
    report_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get detailed incident report"""
    try:
        report = db.query(models.Report).filter(
            models.Report.id == report_id,
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        ).first()

        if not report:
            raise not_found_error("Report not found")

        # Format scope name
        scope_name = ""
        if report.scope_type == models.ReportScopeType.KINDERGARTEN and report.kindergarten:
            scope_name = report.kindergarten.name_ar
        elif report.scope_type == models.ReportScopeType.GOVERNORATE:
            scope_name = report.governorate
        elif report.scope_type == models.ReportScopeType.ALL:
            scope_name = "جميع الروضات"

        return {
            "id": report.id,
            "title": f"تقرير الحوادث - {scope_name} ({report.start_date} - {report.end_date})",
            "scope_type": report.scope_type.value,
            "scope_name": scope_name,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "created_at": report.created_at.isoformat(),
            "created_by": report.creator.username if report.creator else "غير معروف",
            "metrics": report.metrics_json
        }

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get incident report detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/reports/incidents/{report_id}/export")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def export_incident_report_csv(
    report_id: int,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Export incident report as CSV"""
    try:
        report = db.query(models.Report).filter(
            models.Report.id == report_id,
            models.Report.report_type == models.ReportType.INCIDENT_SUMMARY
        ).first()

        if not report:
            raise not_found_error("Report not found")

        # Generate CSV content
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        report_title = f"{report.report_type.value.replace('_', ' ').title()} - {report.scope_type.value.title()}"
        writer.writerow(['Report Title', report_title])
        writer.writerow(['Scope', report.scope_type.value])
        writer.writerow(['Start Date', report.start_date.isoformat()])
        writer.writerow(['End Date', report.end_date.isoformat()])
        writer.writerow(['Generated By', report.creator.username if report.creator else 'Unknown'])
        writer.writerow(['Generated At', report.created_at.isoformat()])
        writer.writerow([])

        # Write metrics
        metrics = report.metrics_json
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Incidents', metrics.get('total_incidents', 0)])
        writer.writerow(['Open Incidents', metrics.get('open_incidents', 0)])
        writer.writerow(['Closed Incidents', metrics.get('closed_incidents', 0)])
        writer.writerow([])

        # Incidents by type
        writer.writerow(['Incidents by Type'])
        writer.writerow(['Type', 'Count'])
        for type_name, count in metrics.get('incidents_by_type', {}).items():
            writer.writerow([type_name, count])
        writer.writerow([])

        # Incidents by severity
        writer.writerow(['Incidents by Severity'])
        writer.writerow(['Severity', 'Count'])
        for severity, count in metrics.get('incidents_by_severity', {}).items():
            writer.writerow([severity, count])
        writer.writerow([])

        # Per kindergarten (if applicable)
        per_kg = metrics.get('per_kindergarten', {})
        if per_kg:
            writer.writerow(['Incidents by Kindergarten'])
            writer.writerow(['Kindergarten', 'Count'])
            for kg, count in per_kg.items():
                writer.writerow([kg, count])

        csv_content = output.getvalue()
        output.close()

        log_audit_event(
            db=db,
            action=AuditAction.INCIDENT_REPORT_EXPORT,
            actor=current_user,
            target_type="Report",
            target_ids=report.id,
            metadata={
                "format": "csv",
                "report_type": report.report_type.value,
                "scope_type": report.scope_type.value,
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
            },
            sensitivity_level=2,
        )

        # Return CSV file
        filename = f"incident_report_{report_id}_{report.created_at.date().isoformat()}.csv"
        return Response(
            csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except (SQLAlchemyError, ValueError, IOError, OSError) as e:
        log_audit_event(
            db=db,
            action=AuditAction.INCIDENT_REPORT_EXPORT_FAILED,
            actor=current_user,
            target_type="Report",
            target_ids=report_id,
            metadata={"format": "csv", "error_message": str(e)},
            sensitivity_level=3,
        )
        logger.error(f"Failed to export incident report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/reports/scopes")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_available_scopes(
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get available report scopes for the current user"""
    try:
        from report_service import ReportService
        scopes = ReportService.get_available_scopes(current_user, db)
        return {"scopes": scopes}

    except HTTPException:
        raise
    except (SQLAlchemyError, AttributeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get available scopes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
