"""
Validation utilities and audit logging for KInJo platform
"""
import re
from datetime import date, datetime
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models
from config import settings


class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_jordan_phone(phone: str) -> bool:
    """Validate Jordanian phone number format"""
    pattern = settings.JORDAN_PHONE_PATTERN
    return bool(re.match(pattern, phone))


def validate_child_age(date_of_birth: date) -> bool:
    """Validate child age is within acceptable range (70 days to 56 months)"""
    today = date.today()
    age_days = (today - date_of_birth).days
    age_months = age_days / 30.44  # Average days per month

    return settings.MIN_CHILD_AGE_DAYS <= age_days and age_months <= settings.MAX_CHILD_AGE_MONTHS


def validate_manager_role(user: models.User) -> None:
    """Validate user has manager or admin role"""
    if user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin role required"
        )


def validate_supervisor_role(user: models.User) -> None:
    """Validate user has supervisor, manager, or admin role"""
    if user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor, Manager, or Admin role required"
        )


def validate_admin_role(user: models.User) -> None:
    """Validate user has admin role"""
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )


def validate_kindergarten_scope(user: models.User, kindergarten_id: int) -> None:
    """Validate user has access to the specified kindergarten"""
    if user.role == models.UserRole.ADMIN:
        return  # Admins can access all kindergartens

    if user.kindergarten_id != kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this kindergarten"
        )


def validate_national_id(national_id: str) -> bool:
    """Validate Jordanian National ID format"""
    # Jordanian national ID is typically 10 digits
    return bool(re.match(r"^\d{10}$", national_id))


def validate_enrollment_dates(start_date: date, end_date: Optional[date]) -> None:
    """Validate enrollment dates are valid"""
    if start_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrollment start date cannot be in the past"
        )

    if end_date and end_date <= start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date"
        )


def validate_age_band_eligibility(date_of_birth: date, min_months: int, max_months: int) -> None:
    """Validate child age fits within class age band"""
    today = date.today()
    age_days = (today - date_of_birth).days
    age_months = age_days / 30.44

    if not (min_months <= age_months <= max_months):
        raise ValidationError(
            f"Child age {age_months:.1f} months is outside class range {min_months}-{max_months} months"
        )


def log_audit_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    sensitivity_level: int = 1
) -> models.AuditLog:
    """Log an audit action"""
    audit_log = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        sensitivity_level=sensitivity_level
    )
    db.add(audit_log)
    db.commit()
    return audit_log


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS"""
    import bleach
    return bleach.clean(text, strip=True)


def validate_time_format(time_str: str) -> bool:
    """Validate time string format (HH:MM)"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False
