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
import secrets
import enum
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Dict, Any, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File
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
from messaging_permissions import ACTIVE_ENROLLMENT_STATUSES, ensure_kindergartens_exist
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


# =============================================================================
# Manager Assignment Service Functions
# =============================================================================

def validate_manager_assignment(
    db: Session,
    role: models.UserRole,
    kindergarten_id: Optional[int],
    exclude_user_id: Optional[int] = None
) -> None:
    """
    Validate manager assignment rules.

    Business Rules:
    - Manager must be assigned to a kindergarten
    - Each kindergarten can have at most one active manager

    Args:
        db: Database session
        role: User role being assigned
        kindergarten_id: Kindergarten ID being assigned
        exclude_user_id: User ID to exclude from uniqueness check (for updates)

    Raises:
        APIError: If validation fails
    """
    if role == models.UserRole.MANAGER:
        # Manager must be assigned to a kindergarten
        if kindergarten_id is None:
            raise validation_error(
                "Manager must be assigned to a kindergarten",
                {"kindergarten_id": "Kindergarten is required for manager role"}
            )

        # Check if kindergarten already has an active manager
        query = db.query(models.User).filter(
            models.User.kindergarten_id == kindergarten_id,
            models.User.role == models.UserRole.MANAGER,
            models.User.status == models.UserStatus.ACTIVE
        )

        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)

        existing_manager = query.first()
        if existing_manager:
            raise conflict_error(
                "Kindergarten already has a manager",
                {"kindergarten_id": f"Kindergarten already has an active manager (ID: {existing_manager.id})"}
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
        if user_data.get('role') == models.UserRole.MANAGER:
            kg_id = user_data.get('kindergarten_id')
            if kg_id is None:
                errors.append({
                    "row": i + 1,
                    "field": "kindergarten_id",
                    "error": "Manager must be assigned to a kindergarten"
                })
            else:
                if kg_id in kg_managers:
                    errors.append({
                        "row": i + 1,
                        "field": "kindergarten_id",
                        "error": f"Multiple managers assigned to kindergarten {kg_id} in this batch"
                    })
                else:
                    kg_managers[kg_id] = i + 1

                # Check against existing managers in database
                existing_manager = db.query(models.User).filter(
                    models.User.kindergarten_id == kg_id,
                    models.User.role == models.UserRole.MANAGER,
                    models.User.status == models.UserStatus.ACTIVE
                ).first()

                if existing_manager:
                    errors.append({
                        "row": i + 1,
                        "field": "kindergarten_id",
                        "error": f"Kindergarten already has an active manager (ID: {existing_manager.id})"
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

    # Business rule: Manager validation
    validate_manager_assignment(db, user_data.role, user_data.kindergarten_id)

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
        status=models.UserStatus.ACTIVE
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

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
        "correlation_id": get_correlation_id()
    }


@router.get("/admin/users/{user_id}")
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
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "correlation_id": get_correlation_id()
    }


@router.put("/admin/users/{user_id}")
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

    validate_manager_assignment(db, target_role, target_kindergarten_id, user_id)

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
        "correlation_id": get_correlation_id()
    }


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
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

@router.post("/admin/users/{user_id}/admin-reset-password")
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
        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        # Invalidate any existing tokens
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used == False
        ).update({"used": True})

        # Create new token
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        db.add(reset_token)
        db.commit()

        # Audit log
        log_audit_event(
            db, "PASSWORD_RESET_REQUESTED", user, "User",
            target_ids=user.id,
            sensitivity_level=2
        )

        # TODO: Send email with reset link
        # In production, the token would be sent via email, not returned
        # For development, we return it
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
    token_record = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == reset_data.token,
        models.PasswordResetToken.used == False,
        models.PasswordResetToken.expires_at > datetime.now(timezone.utc)
    ).first()

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
        for user_id in access_result["allowed"]:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user and user.role == models.UserRole.MANAGER and user.kindergarten_id:
                try:
                    validate_manager_assignment(db, user.role, user.kindergarten_id, user_id)
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

    # Execute update
    succeeded = []
    failed = []
    errors = []

    for user_id in access_result["allowed"]:
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                before_state = model_to_dict(user)
                user.status = bulk_data.new_status
                succeeded.append(user_id)
        except Exception as e:
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

    # Execute delete
    deleted_ids = []
    for user_id in access_result["allowed"]:
        user = db.query(models.User).filter(models.User.id == user_id).first()
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

        # Check for existing username/email (email only if provided)
        # Always check username uniqueness
        existing_username = db.query(models.User).filter(models.User.username == user_data.username).first()
        if existing_username:
            failed.append(row_num)
            errors.append({
                "row": row_num,
                "field": "username",
                "error": "Username already exists"
            })
            continue

        # Check email uniqueness only if email is provided
        if user_data.email is not None:
            existing_email = db.query(models.User).filter(models.User.email == user_data.email).first()
            if existing_email:
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
            except Exception as e:
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
    except Exception as e:
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
        except Exception as e:
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
        db, "USER_EXPORT", current_user, "User",
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
            query = query.filter(or_(
                models.ParentProfile.user_id.in_(enrolled_parent_ids),
                and_(
                    ~models.ParentProfile.user_id.in_(active_parent_ids),
                    models.ParentProfile.home_governorate.in_(governorates)
                )
            ))
        else:
            query = query.filter(models.ParentProfile.user_id.in_(enrolled_parent_ids))

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
    if canonical_governorates and len(canonical_governorates) > 1 and target.mode == AdminMessageTargetMode.GOVERNORATE:
        raise validation_error("Only one governorate is allowed", fields={"governorates": "single"})

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
    except Exception as exc:
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
        if len(canonical_governorates) > 1:
            raise validation_error("Only one governorate is allowed", fields={"governorates": "single"})
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
