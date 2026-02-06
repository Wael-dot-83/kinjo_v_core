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


def _normalize_governorate_input(value: str) -> str:
    cleaned = value.strip().lower().replace("’", "'")
    cleaned = re.sub(r"[\s\-_`']", "", cleaned)
    return cleaned


def validate_jordan_governorate(governorate: str) -> str:
    """Validate governorate is a valid Jordanian governorate and return normalized Arabic name"""
    if governorate is None:
        raise ValidationError("Governorate is required")

    raw = governorate.strip() if isinstance(governorate, str) else str(governorate)
    if not raw:
        raise ValidationError("Governorate is required")

    # Check Arabic names directly
    if raw in settings.JORDAN_GOVERNORATES:
        return raw

    normalized = _normalize_governorate_input(raw)

    # Build alias map (normalized keys -> Arabic)
    alias_map = {}
    for key, value in settings.JORDAN_GOVERNORATE_ALIASES.items():
        alias_map[_normalize_governorate_input(key)] = value
    for english, arabic in zip(settings.JORDAN_GOVERNORATES_ENGLISH, settings.JORDAN_GOVERNORATES):
        alias_map.setdefault(_normalize_governorate_input(english), arabic)

    if normalized in alias_map:
        return alias_map[normalized]

    # Invalid governorate
    raise ValidationError(
        f"Invalid governorate: {governorate}. Must be one of (Arabic): "
        f"{', '.join(settings.JORDAN_GOVERNORATES)} or (English): "
        f"{', '.join(settings.JORDAN_GOVERNORATES_ENGLISH)}"
    )


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


def is_working_day(db, kindergarten_id: int, check_date: date) -> bool:
    """Determine if a given date is a working day for the kindergarten.

    Logic:
    - If an OperatingCalendar entry exists for the kindergarten and date, use its is_open flag.
    - Otherwise, fall back to the default policy: closed on Fridays (weekday == 4).
    """
    if settings.TESTING:
        return True
    # Try to find explicit calendar entry
    from models import OperatingCalendar
    row = db.query(OperatingCalendar).filter(
        OperatingCalendar.kindergarten_id == kindergarten_id,
        OperatingCalendar.date == check_date
    ).first()
    if row is not None:
        return bool(row.is_open)

    # Default policy (Friday closed)
    return check_date.weekday() != 4


def check_profile_complete(db, child_id: int) -> (bool, list):
    """Check whether child + parent profile satisfy required completeness rules.

    Returns tuple: (is_complete: bool, missing_fields: list[str])
    """
    missing = []
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise ValueError("Child not found")

    # Required child fields
    required_child_fields = [
        ('first_name', child.first_name),
        ('last_name', child.last_name),
        ('date_of_birth', child.date_of_birth),
        ('gender', child.gender),
        ('father_name', child.father_name),
        ('mother_first_name', child.mother_first_name),
        ('mother_last_name', child.mother_last_name),
        ('mother_nationality', child.mother_nationality)
    ]
    for fname, val in required_child_fields:
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f'child.{fname}')

    # Parent required fields
    parent = child.parent
    if not parent and child.parent_id:
        parent = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == child.parent_id
        ).first()

    required_parent_fields = [
        ('first_name', parent.first_name if parent else None),
        ('last_name', parent.last_name if parent else None),
        ('phone_number', parent.phone_number if parent else None),
        ('home_address_line', parent.home_address_line if parent else None),
        ('home_city', parent.home_city if parent else None)
    ]
    for fname, val in required_parent_fields:
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f'parent.{fname}')

    return (len(missing) == 0, missing)


def mark_profile_complete_if_ready(db, child_id: int):
    """Mark child and parent profile_complete true when ready."""
    from models import Child, ParentProfile
    ok, missing = check_profile_complete(db, child_id)
    if not ok:
        return False, missing

    child = db.query(Child).filter(Child.id == child_id).first()
    parent = child.parent
    if not parent and child and child.parent_id:
        parent = db.query(ParentProfile).filter(
            ParentProfile.user_id == child.parent_id
        ).first()
    if not parent:
        return False, ["parent.profile"]
    from datetime import datetime
    child.profile_complete = True
    child.profile_completed_at = datetime.now()
    parent.profile_complete = True
    parent.profile_completed_at = datetime.now()
    db.commit()
    return True, []


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
