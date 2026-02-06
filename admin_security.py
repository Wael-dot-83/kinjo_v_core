"""
Admin Security Module - Comprehensive security hardening for admin endpoints

This module provides:
- Standardized error response contract
- Correlation ID middleware
- Enhanced audit logging with before/after diffs
- Rate limiting policies for admin operations
- Object-level authorization helpers
- CSV import validation with per-row error reporting
- Pagination enforcement
- Bulk operation guardrails
"""
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable, TypeVar, Union
from functools import wraps
from contextvars import ContextVar
from enum import Enum

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, field_validator, EmailStr
from sqlalchemy.orm import Session

import models
from database import get_db
from config import settings

# =============================================================================
# Context Variables for Request Tracking
# =============================================================================

# Store correlation ID for current request context
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')
request_ip_var: ContextVar[str] = ContextVar('request_ip', default='')


def get_correlation_id() -> str:
    """Get the correlation ID for the current request"""
    return correlation_id_var.get() or str(uuid.uuid4())


def get_request_ip() -> str:
    """Get the IP address for the current request"""
    return request_ip_var.get() or 'unknown'


# =============================================================================
# Standardized Error Codes and Response Contract
# =============================================================================

class ErrorCode(str, Enum):
    """Standardized error codes"""
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"


class ErrorResponse(BaseModel):
    """Standardized error response structure"""
    code: str
    message: str
    fields: Optional[Dict[str, str]] = None
    correlation_id: str
    details: Optional[Dict[str, Any]] = None


class APIError(HTTPException):
    """Custom exception that follows the standardized error contract"""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        fields: Optional[Dict[str, str]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.fields = fields
        self.details = details
        super().__init__(status_code=status_code, detail=message)


def create_error_response(
    code: ErrorCode,
    message: str,
    fields: Optional[Dict[str, str]] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standardized error response dictionary"""
    return {
        "error": {
            "code": code.value,
            "message": message,
            "fields": fields,
            "correlation_id": get_correlation_id(),
            "details": details
        }
    }


# Pre-defined error creators
def unauthenticated_error(message: str = "Authentication required") -> APIError:
    return APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=ErrorCode.UNAUTHENTICATED,
        message=message
    )


def forbidden_error(message: str = "You do not have permission to perform this action") -> APIError:
    return APIError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=ErrorCode.FORBIDDEN,
        message=message
    )


def validation_error(message: str, fields: Optional[Dict[str, str]] = None) -> APIError:
    return APIError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=ErrorCode.VALIDATION_ERROR,
        message=message,
        fields=fields
    )


def not_found_error(message: str = "Resource not found") -> APIError:
    return APIError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=ErrorCode.NOT_FOUND,
        message=message
    )


def conflict_error(message: str, fields: Optional[Dict[str, str]] = None) -> APIError:
    return APIError(
        status_code=status.HTTP_409_CONFLICT,
        code=ErrorCode.CONFLICT,
        message=message,
        fields=fields
    )


def rate_limited_error(retry_after: int = 60) -> APIError:
    return APIError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code=ErrorCode.RATE_LIMITED,
        message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
        details={"retry_after": retry_after}
    )


# =============================================================================
# Correlation ID Middleware
# =============================================================================

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject correlation ID into every request"""

    CORRELATION_ID_HEADER = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        # Get correlation ID from header or generate new one
        correlation_id = request.headers.get(self.CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Set context variables
        correlation_id_var.set(correlation_id)

        # Get client IP
        client_ip = request.client.host if request.client else 'unknown'
        # Check for X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        request_ip_var.set(client_ip)

        # Call next middleware/endpoint
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers[self.CORRELATION_ID_HEADER] = correlation_id

        return response


# =============================================================================
# Enhanced Audit Logging with Before/After Diffs
# =============================================================================

# Sensitive fields that should never be logged
SENSITIVE_FIELDS = {
    'password', 'hashed_password', 'secret', 'token', 'api_key',
    'admin_password', 'new_password', 'old_password', 'access_token',
    'refresh_token', 'private_key', 'secret_key'
}


def redact_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive fields from data for audit logging"""
    if not data:
        return data

    redacted = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_sensitive_data(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value

    return redacted


def compute_diff(before: Optional[Dict], after: Optional[Dict]) -> Dict[str, Any]:
    """Compute the diff between before and after states"""
    if not before and not after:
        return {}

    if not before:
        return {"added": redact_sensitive_data(after)}

    if not after:
        return {"removed": redact_sensitive_data(before)}

    diff = {"changed": {}, "added": {}, "removed": {}}

    all_keys = set(before.keys()) | set(after.keys())

    for key in all_keys:
        before_val = before.get(key)
        after_val = after.get(key)

        if key.lower() in SENSITIVE_FIELDS:
            if before_val != after_val:
                diff["changed"][key] = {"before": "[REDACTED]", "after": "[REDACTED]"}
        elif key in before and key not in after:
            diff["removed"][key] = before_val
        elif key not in before and key in after:
            diff["added"][key] = after_val
        elif before_val != after_val:
            diff["changed"][key] = {"before": before_val, "after": after_val}

    # Remove empty sections
    return {k: v for k, v in diff.items() if v}


def model_to_dict(model: Any) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dictionary for audit logging"""
    if model is None:
        return {}

    result = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name, None)
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, datetime):
            value = value.isoformat()
        result[column.name] = value

    return result


class AuditEvent(BaseModel):
    """Structured audit event for logging"""
    action: str
    actor_id: Optional[int]
    actor_username: Optional[str]
    target_type: str
    target_ids: List[int] = []
    correlation_id: str
    ip_address: str
    timestamp: datetime
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    diff: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    sensitivity_level: int = 1


def log_audit_event(
    db: Session,
    action: str,
    actor: Optional[models.User],
    target_type: str,
    target_ids: Union[int, List[int], None] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    sensitivity_level: int = 1
) -> models.AuditLog:
    """
    Log an audit event with full context including before/after diffs.

    Args:
        db: Database session
        action: Action name (e.g., "USER_CREATED", "BULK_DELETE")
        actor: The user performing the action
        target_type: Entity type being acted upon
        target_ids: ID(s) of the target entity/entities
        before_state: State before the action (for updates/deletes)
        after_state: State after the action (for creates/updates)
        metadata: Additional context data
        sensitivity_level: 1=low, 2=medium, 3=high
    """
    # Normalize target_ids to list
    if target_ids is None:
        ids_list = []
    elif isinstance(target_ids, int):
        ids_list = [target_ids]
    else:
        ids_list = list(target_ids)

    # Compute diff
    diff = compute_diff(before_state, after_state)

    # Build details JSON
    details_dict = {
        "correlation_id": get_correlation_id(),
        "target_ids": ids_list,
    }

    if diff:
        details_dict["diff"] = diff

    if metadata:
        details_dict["metadata"] = redact_sensitive_data(metadata)

    # For bulk operations, truncate if too large
    details_str = json.dumps(details_dict, default=str)
    if len(details_str) > 10000:  # 10KB limit
        details_dict["truncated"] = True
        details_dict["diff"] = {"summary": f"Diff too large ({len(ids_list)} records)"}
        details_str = json.dumps(details_dict, default=str)

    # Create audit log entry
    audit_log = models.AuditLog(
        user_id=actor.id if actor else None,
        action=action,
        entity_type=target_type,
        entity_id=ids_list[0] if len(ids_list) == 1 else None,
        details=details_str,
        ip_address=get_request_ip(),
        sensitivity_level=sensitivity_level
    )

    db.add(audit_log)
    db.commit()

    return audit_log


# =============================================================================
# Admin Authorization Middleware
# =============================================================================

def require_admin_role(current_user: models.User) -> models.User:
    """
    Dependency that enforces admin role.
    Returns 401 if not authenticated, 403 if authenticated but not admin.
    """
    if current_user is None:
        raise unauthenticated_error("Authentication required")

    if current_user.role != models.UserRole.ADMIN:
        raise forbidden_error("Admin access required")

    return current_user


def require_admin_or_manager_role(current_user: models.User) -> models.User:
    """
    Dependency that enforces admin or manager role.
    """
    if current_user is None:
        raise unauthenticated_error("Authentication required")

    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise forbidden_error("Admin or Manager access required")

    return current_user


# =============================================================================
# Object-Level Authorization (IDOR Protection)
# =============================================================================

def can_admin_access_user(actor: models.User, target: models.User) -> bool:
    """
    Check if actor can access/modify target user.

    Rules:
    - Admin can access all non-admin users
    - Admin cannot modify other admin accounts
    - Manager can only access users in their kindergarten
    """
    if actor.role == models.UserRole.ADMIN:
        # Admins cannot manage other admins
        if target.role == models.UserRole.ADMIN and target.id != actor.id:
            return False
        return True

    if actor.role == models.UserRole.MANAGER:
        # Managers can only access users in their kindergarten
        if target.kindergarten_id != actor.kindergarten_id:
            return False
        # Managers cannot manage admins or other managers
        if target.role in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
            return target.id == actor.id  # Can only manage self
        return True

    # Other roles can only access themselves
    return target.id == actor.id


def can_admin_access_kindergarten(actor: models.User, kindergarten_id: int) -> bool:
    """Check if actor can access/modify a kindergarten"""
    if actor.role == models.UserRole.ADMIN:
        return True

    if actor.role == models.UserRole.MANAGER:
        return actor.kindergarten_id == kindergarten_id

    return False


def validate_bulk_targets(
    db: Session,
    actor: models.User,
    target_ids: List[int],
    model_class: type,
    access_check: Callable[[models.User, Any], bool]
) -> Dict[str, List[int]]:
    """
    Validate access to multiple targets for bulk operations.

    Returns:
        Dict with 'allowed' and 'forbidden' lists of IDs
    """
    allowed = []
    forbidden = []
    not_found = []

    for target_id in target_ids:
        target = db.query(model_class).filter(model_class.id == target_id).first()
        if target is None:
            not_found.append(target_id)
        elif access_check(actor, target):
            allowed.append(target_id)
        else:
            forbidden.append(target_id)

    return {
        "allowed": allowed,
        "forbidden": forbidden,
        "not_found": not_found
    }


# =============================================================================
# Rate Limiting Policies
# =============================================================================

class RateLimitPolicy:
    """Rate limit configuration for different operation types"""

    # Strict limits for sensitive operations
    PASSWORD_RESET = "3/minute"
    PASSWORD_RESET_REQUEST = "5/minute"

    # Moderate limits for bulk operations
    BULK_CREATE = "10/minute"
    BULK_UPDATE = "10/minute"
    BULK_DELETE = "5/minute"

    # Standard limits for admin operations
    ADMIN_READ = "60/minute"
    ADMIN_WRITE = "30/minute"

    # CSV import (longer operations)
    CSV_IMPORT = "5/minute"


# =============================================================================
# CSV Import Validation
# =============================================================================

class CSVRowError(BaseModel):
    """Error for a single CSV row"""
    row_number: int
    field: Optional[str] = None
    error_code: str
    message: str


class CSVImportResult(BaseModel):
    """Result of CSV import validation/execution"""
    total_rows: int
    succeeded: int
    failed: int
    errors: List[CSVRowError] = []
    created_ids: List[int] = []
    dry_run: bool = False


def sanitize_csv_cell(value: str) -> str:
    """
    Sanitize CSV cell to prevent CSV injection attacks.
    Prefixes dangerous characters with a single quote.
    """
    if not value:
        return value

    value = value.strip()

    # Characters that can trigger formula injection in spreadsheets
    dangerous_prefixes = ('=', '+', '-', '@', '\t', '\r', '\n')

    if value.startswith(dangerous_prefixes):
        return "'" + value

    return value


def validate_csv_row(
    row: Dict[str, str],
    row_number: int,
    schema: type,  # Pydantic model class
    db: Session
) -> tuple[Optional[Any], List[CSVRowError]]:
    """
    Validate a single CSV row against a Pydantic schema.

    Returns:
        Tuple of (validated_data or None, list of errors)
    """
    errors = []

    # Sanitize all values
    sanitized = {k: sanitize_csv_cell(str(v)) if v else v for k, v in row.items()}

    try:
        validated = schema(**sanitized)
        return validated, []
    except Exception as e:
        if hasattr(e, 'errors'):
            for error in e.errors():
                field = '.'.join(str(loc) for loc in error.get('loc', []))
                errors.append(CSVRowError(
                    row_number=row_number,
                    field=field,
                    error_code="VALIDATION_ERROR",
                    message=error.get('msg', str(error))
                ))
        else:
            errors.append(CSVRowError(
                row_number=row_number,
                error_code="PARSE_ERROR",
                message=str(e)
            ))

    return None, errors


# =============================================================================
# Pagination Enforcement
# =============================================================================

class PaginationConfig:
    """Configuration for pagination limits"""
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100
    MIN_PAGE_SIZE = 1


def enforce_pagination(
    page: int = 1,
    page_size: int = PaginationConfig.DEFAULT_PAGE_SIZE
) -> tuple[int, int, int]:
    """
    Enforce pagination limits and return (page, page_size, offset).

    Args:
        page: Page number (1-indexed)
        page_size: Requested page size

    Returns:
        Tuple of (page, capped_page_size, offset)
    """
    # Ensure page is at least 1
    page = max(1, page)

    # Cap page size
    page_size = min(max(PaginationConfig.MIN_PAGE_SIZE, page_size), PaginationConfig.MAX_PAGE_SIZE)

    # Calculate offset
    offset = (page - 1) * page_size

    return page, page_size, offset


# =============================================================================
# Bulk Operation Guardrails
# =============================================================================

class BulkOperationConfig:
    """Configuration for bulk operation limits"""
    MAX_BULK_CREATE = 100
    MAX_BULK_UPDATE = 500
    MAX_BULK_DELETE = 100

    # Require confirmation for operations affecting more than this many records
    CONFIRMATION_THRESHOLD = 10


class BulkOperationRequest(BaseModel):
    """Base request for bulk operations with confirmation support"""
    confirmation_token: Optional[str] = None
    dry_run: bool = False


def generate_confirmation_token(
    action: str,
    target_ids: List[int],
    actor_id: int
) -> str:
    """Generate a confirmation token for dangerous bulk operations"""
    payload = f"{action}:{sorted(target_ids)}:{actor_id}:{datetime.now(timezone.utc).date()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def verify_confirmation_token(
    token: str,
    action: str,
    target_ids: List[int],
    actor_id: int
) -> bool:
    """Verify a confirmation token"""
    expected = generate_confirmation_token(action, target_ids, actor_id)
    return token == expected


class BulkOperationResult(BaseModel):
    """Result of a bulk operation"""
    action: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    succeeded_ids: List[int] = []
    failed_ids: List[int] = []
    errors: List[Dict[str, Any]] = []
    requires_confirmation: bool = False
    confirmation_token: Optional[str] = None
    dry_run: bool = False


# =============================================================================
# Exception Handler for APIError
# =============================================================================

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle APIError exceptions and return standardized response"""
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            code=exc.code,
            message=exc.message,
            fields=exc.fields,
            details=exc.details
        ),
        headers={
            "X-Correlation-ID": get_correlation_id()
        }
    )


# =============================================================================
# Input Validation Schemas for Admin Operations
# =============================================================================

class UserCreateSchema(BaseModel):
    """Schema for creating a user with strict validation"""
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=72)
    role: models.UserRole
    kindergarten_id: Optional[int] = None

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.lower().strip()

    @field_validator('username')
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip()


class UserUpdateSchema(BaseModel):
    """Schema for updating a user with strict validation"""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)
    role: Optional[models.UserRole] = None
    status: Optional[models.UserStatus] = None
    kindergarten_id: Optional[int] = None

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.lower().strip()


class BulkStatusUpdateSchema(BaseModel):
    """Schema for bulk status update"""
    user_ids: List[int] = Field(..., min_length=1, max_length=BulkOperationConfig.MAX_BULK_UPDATE)
    new_status: models.UserStatus
    confirmation_token: Optional[str] = None
    dry_run: bool = False


class BulkDeleteSchema(BaseModel):
    """Schema for bulk delete"""
    user_ids: List[int] = Field(..., min_length=1, max_length=BulkOperationConfig.MAX_BULK_DELETE)
    confirmation_token: Optional[str] = None
    dry_run: bool = False


class BulkCreateSchema(BaseModel):
    """Schema for bulk user creation"""
    users: List[UserCreateSchema] = Field(..., min_length=1, max_length=BulkOperationConfig.MAX_BULK_CREATE)
    dry_run: bool = False


# =============================================================================
# Password Reset Schemas
# =============================================================================

class PasswordResetRequestSchema(BaseModel):
    """Schema for password reset request"""
    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class PasswordResetConfirmSchema(BaseModel):
    """Schema for password reset confirmation"""
    token: str = Field(..., min_length=32, max_length=64)
    new_password: str = Field(..., min_length=8, max_length=72)


class AdminPasswordResetSchema(BaseModel):
    """Schema for admin-initiated password reset"""
    new_password: str = Field(..., min_length=8, max_length=72)
    admin_password: str = Field(..., min_length=8, max_length=72)
