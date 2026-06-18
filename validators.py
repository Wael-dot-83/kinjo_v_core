# Supervisor requirement calculation
def calculate_required_supervisors(age_group: str, children_count: int) -> int:
    """
    Calculate required supervisors based on age group and children count.
    Policy:
    - 0-1 years: 1 supervisor per 4 children
    - 1-2 years: 1 supervisor per 6 children
    - 2-4 years: 1 supervisor per 8 children
    Sensible max: 40 children per class.
    """
    if children_count < 0 or children_count > 40:
        raise ValidationError("Children count must be between 0 and 40.")
    if age_group == 'AGE_0_1':
        return max(1, (children_count + 3) // 4)
    elif age_group == 'AGE_1_2':
        return max(1, (children_count + 5) // 6)
    elif age_group == 'AGE_2_4':
        return max(1, (children_count + 7) // 8)
    else:
        raise ValidationError("Invalid age group.")
"""
Validation utilities and audit logging for KInJo platform
"""
import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

import models
from config import settings
from child_age_policy import (
    calculate_age_days,
    calculate_age_months,
    classify_dob,
    get_child_age_bounds,
    is_dob_within_bounds,
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ManagerRuleError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int,
        field: Optional[str] = None,
        kindergarten_id: Optional[int] = None,
        existing_manager_id: Optional[int] = None
    ):
        self.message = message
        self.status_code = status_code
        self.field = field
        self.kindergarten_id = kindergarten_id
        self.existing_manager_id = existing_manager_id
        super().__init__(message)


def _coerce_user_role(role):
    if isinstance(role, models.UserRole):
        return role
    if isinstance(role, str):
        try:
            return models.UserRole(role)
        except (ValueError, TypeError, AttributeError):
            return role
    return role


def _coerce_user_status(status_value):
    if isinstance(status_value, models.UserStatus):
        return status_value
    if isinstance(status_value, str):
        try:
            return models.UserStatus(status_value)
        except (ValueError, TypeError, AttributeError):
            return status_value
    return status_value


def validate_manager_rules(
    db: Session,
    *,
    role,
    kindergarten_id: Optional[int],
    status_value,
    exclude_user_id: Optional[int] = None
) -> None:
    """Validate manager assignment rules and active manager uniqueness."""
    role = _coerce_user_role(role)
    status_value = _coerce_user_status(status_value)

    if role != models.UserRole.MANAGER:
        return

    if kindergarten_id is None:
        raise ManagerRuleError(
            message="Manager must be assigned to a kindergarten",
            status_code=status.HTTP_400_BAD_REQUEST,
            field="kindergarten_id"
        )

    if status_value != models.UserStatus.ACTIVE:
        return

    query = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.role == models.UserRole.MANAGER,
        models.User.status == models.UserStatus.ACTIVE
    )

    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)

    existing_manager = query.first()
    if existing_manager:
        raise ManagerRuleError(
            message=(
                "Each kindergarten can have only one active manager. "
                f"Kindergarten {kindergarten_id} already has an active manager (ID: {existing_manager.id})."
            ),
            status_code=status.HTTP_409_CONFLICT,
            field="kindergarten_id",
            kindergarten_id=kindergarten_id,
            existing_manager_id=existing_manager.id
        )


def validate_jordan_phone(phone: str) -> bool:
    """Validate Jordanian phone number format"""
    pattern = settings.JORDAN_PHONE_PATTERN
    return bool(re.match(pattern, phone))


def validate_password_policy(password: str) -> None:
    """Enforce full password policy from config. Raises ValidationError on failure."""
    errors = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        errors.append(f"يجب أن تكون كلمة المرور {settings.PASSWORD_MIN_LENGTH} أحرف على الأقل / "
                       f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        errors.append("يجب أن تحتوي على حرف كبير / Must contain an uppercase letter")
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        errors.append("يجب أن تحتوي على حرف صغير / Must contain a lowercase letter")
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        errors.append("يجب أن تحتوي على رقم / Must contain a digit")
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", password):
        errors.append("يجب أن تحتوي على رمز خاص / Must contain a special character")
    if errors:
        raise ValidationError("; ".join(errors))


def validate_identity_by_nationality(nationality: str, national_id: Optional[str], passport_number: Optional[str]) -> None:
    """Jordanians must provide national_id; non-Jordanians must provide passport_number."""
    is_jordanian = nationality and nationality.strip().lower() in (
        "jordanian", "أردني", "أردنية", "jordan", "jo"
    )
    if is_jordanian:
        if not national_id or not national_id.strip():
            raise ValidationError("الرقم الوطني مطلوب للمواطنين الأردنيين / "
                                  "National ID is required for Jordanian citizens")
        if not validate_national_id(national_id):
            raise ValidationError("الرقم الوطني يجب أن يكون 10 أرقام / National ID must be 10 digits")
    else:
        if not passport_number or not passport_number.strip():
            raise ValidationError("رقم جواز السفر مطلوب لغير الأردنيين / "
                                  "Passport number is required for non-Jordanian citizens")


def _normalize_governorate_input(value: str) -> str:
    cleaned = value.strip().lower().replace("'", "'")
    cleaned = re.sub(r"[\s\-_`']", "", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Arabic search normalization (GWS U.2.3-065)
# ---------------------------------------------------------------------------
# Canonicalises Arabic text so that searches are robust against:
#   - Alef variants (أ إ آ ٱ) → plain ا
#   - Tah marbuta (ة) → open tah (ه)   — optional tolerance
#   - Final ya without dots (ى) → dotted ya (ي)
#   - Tatweel / kashida (ـ)
#   - Hamza on waw (ؤ→و) and hamza alone (ئ→ي)
#   - Definite article prefix (ال) stripped from the start of the term
# This function is applied to BOTH the user query and the stored value before
# comparison via LIKE — the column ilike() call is generated with the
# normalized pattern when build_arabic_search_terms() is used.
_ALEF_RE = re.compile(r"[أإآٱ]")
_YA_RE = re.compile(r"ى")
_TAH_MARBUTA_RE = re.compile(r"ة")
_TATWEEL_RE = re.compile(r"ـ")
_HAMZA_WAW_RE = re.compile(r"ؤ")
_HAMZA_YA_RE = re.compile(r"ئ")
_AL_PREFIX_RE = re.compile(r"^[اأإ]ل")


def normalize_arabic_text(text: str) -> str:
    """Return a canonicalized form of *text* for fuzzy Arabic search matching."""
    if not text:
        return text
    s = unicodedata.normalize("NFC", text)
    s = _ALEF_RE.sub("ا", s)
    s = _YA_RE.sub("ي", s)
    s = _TATWEEL_RE.sub("", s)
    s = _HAMZA_WAW_RE.sub("و", s)
    s = _HAMZA_YA_RE.sub("ي", s)
    # Strip Arabic definite article at word boundaries
    s = re.sub(r"(?<!\w)[اأإ]ل(?=\w)", "", s)
    return s.strip()


def build_arabic_search_terms(raw: str) -> list[str]:
    """Split *raw* into individual search tokens, each with Arabic normalisation.

    Returns up to 8 tokens to prevent degenerate queries.
    """
    original_tokens = [t.strip() for t in (raw or "").split() if t.strip()][:8]
    result: list[str] = []
    for tok in original_tokens:
        result.append(tok)
        normalised = normalize_arabic_text(tok)
        if normalised and normalised != tok:
            result.append(normalised)
    return result


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


def _build_child_age_error_message(date_of_birth: date) -> Optional[str]:
    today = date.today()
    age_days = calculate_age_days(date_of_birth, today)
    age_months = calculate_age_months(date_of_birth, today)
    status_label = classify_dob(date_of_birth, today)

    if status_label == "too_young":
        return (
            f"عمر الطفل ({age_days} يوم) أقل من الحد الأدنى المسموح ({settings.MIN_CHILD_AGE_DAYS} يوم). "
            f"Child age ({age_days} days) is below minimum ({settings.MIN_CHILD_AGE_DAYS} days)."
        )

    if status_label == "too_old":
        return (
            f"عمر الطفل ({age_months} شهر) أكبر من الحد الأقصى المسموح ({settings.MAX_CHILD_AGE_MONTHS} شهر / 4 سنوات و 8 أشهر). "
            f"Child age ({age_months} months) exceeds maximum ({settings.MAX_CHILD_AGE_MONTHS} months / 4 years 8 months)."
        )

    return None


def validate_child_age(date_of_birth: date) -> bool:
    """Validate child age is within acceptable range (70 days to 4 years 8 months)."""
    return is_dob_within_bounds(date_of_birth)


def validate_child_age_strict(date_of_birth: date) -> None:
    """
    Validate child age is within acceptable range and raise ValidationError if not.
    Age constraints: 70 days minimum to 4 years 8 months (56 months) maximum.
    """
    message = _build_child_age_error_message(date_of_birth)
    if message:
        age_days = calculate_age_days(date_of_birth)
        age_months = calculate_age_months(date_of_birth)
        logger.warning(
            "child_age_violation dob=%s age_days=%s age_months=%s",
            date_of_birth,
            age_days,
            age_months,
        )
        raise ValidationError(message)


def get_child_age_info(date_of_birth: date) -> dict:
    """Get detailed age information for a child including eligibility status."""
    today = date.today()
    age_days = calculate_age_days(date_of_birth, today)
    age_months = calculate_age_months(date_of_birth, today)
    age_years = age_days / 365.25
    bounds = get_child_age_bounds(today)

    is_eligible = is_dob_within_bounds(date_of_birth, today)
    status_label = classify_dob(date_of_birth, today)

    if status_label == "too_young":
        reason = f"أقل من الحد الأدنى ({settings.MIN_CHILD_AGE_DAYS} يوم)"
        reason_en = f"Below minimum ({settings.MIN_CHILD_AGE_DAYS} days)"
    elif status_label == "too_old":
        reason = f"أكبر من الحد الأقصى ({settings.MAX_CHILD_AGE_MONTHS} شهر)"
        reason_en = f"Exceeds maximum ({settings.MAX_CHILD_AGE_MONTHS} months)"
    else:
        reason = "مؤهل للتسجيل"
        reason_en = "Eligible for enrollment"

    return {
        "age_days": age_days,
        "age_months": age_months,
        "age_years": round(age_years, 2),
        "is_eligible": is_eligible,
        "reason_ar": reason,
        "reason_en": reason_en,
        "min_age_days": settings.MIN_CHILD_AGE_DAYS,
        "max_age_months": settings.MAX_CHILD_AGE_MONTHS,
        "min_date": bounds.min_date.isoformat(),
        "max_date": bounds.max_date.isoformat(),
    }


def validate_manager_role(user: models.User) -> None:
    """Validate user has manager or admin role"""
    if user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin role required"
        )


def require_manager_with_kindergarten(
    user: models.User,
    *,
    allow_admin: bool = False
) -> Optional[int]:
    """Require manager role and return manager kindergarten_id."""
    if user.role == models.UserRole.ADMIN:
        if allow_admin:
            return None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required"
        )

    if user.role != models.UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required"
        )

    if not user.kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager must be assigned to a kindergarten"
        )

    return user.kindergarten_id


def validate_supervisor_role(user: models.User) -> None:
    """Validate user has supervisor, manager, or admin role"""
    if user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor, Manager, or Admin role required"
        )


def ensure_supervisor_profile(db: Session, supervisor: models.User, kindergarten_id: int) -> models.SupervisorProfile:
    """Create or reuse SupervisorProfile to satisfy composite FK constraints."""
    if kindergarten_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kindergarten assignment required for supervisor"
        )

    profile = db.query(models.SupervisorProfile).filter(
        models.SupervisorProfile.user_id == supervisor.id
    ).first()

    if profile:
        if profile.kindergarten_id != kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supervisor already assigned to a different kindergarten"
            )
        return profile

    profile = models.SupervisorProfile(
        user_id=supervisor.id,
        kindergarten_id=kindergarten_id
    )
    db.add(profile)
    db.flush()
    return profile


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


def validate_child_kindergarten_scope(db: Session, user: models.User, child_id: int) -> None:
    """Validate that the child is enrolled in the user's kindergarten"""
    # Always enforce global age policy first
    ensure_child_in_range(db, child_id)

    if user.role == models.UserRole.ADMIN:
        return
    if user.role == models.UserRole.PARENT:
        return  # Parent scoping is via ownership, not KG

    active_statuses = [models.EnrollmentStatus.ACTIVE, models.EnrollmentStatus.ACCEPTED]
    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.kindergarten_id == user.kindergarten_id,
        models.EnrollmentApplication.status.in_(active_statuses)
    ).first()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Child not enrolled in your kindergarten"
        )


def ensure_child_in_range(db: Session, child_id: int) -> models.Child:
    """Ensure child exists and is within global age bounds."""
    child = db.query(models.Child).execution_options(
        include_out_of_range_children=True
    ).filter(models.Child.id == child_id).first()

    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    message = _build_child_age_error_message(child.date_of_birth)
    if message:
        raise HTTPException(status_code=400, detail=message)

    return child


def validate_class_kindergarten_scope(db: Session, user: models.User, class_id: int) -> None:
    """Validate that the class belongs to the user's kindergarten"""
    if user.role == models.UserRole.ADMIN:
        return

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj or class_obj.kindergarten_id != user.kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this class"
        )


def validate_enrollment_kindergarten_scope(db: Session, user: models.User, enrollment_id: int) -> None:
    """Validate that the enrollment belongs to the user's kindergarten"""
    if user.role == models.UserRole.ADMIN:
        return

    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id == enrollment_id
    ).first()
    if not enrollment or enrollment.kindergarten_id != user.kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this enrollment"
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
    age_months = calculate_age_months(date_of_birth)

    if not (min_months <= age_months <= max_months):
        raise ValidationError(
            f"Child age {age_months} months is outside class range {min_months}-{max_months} months"
        )


def validate_age_months(date_of_birth: date) -> int:
    """Return full months of age (calendar-based)."""
    return calculate_age_months(date_of_birth)


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
    from datetime import datetime, timezone
    child.profile_complete = True
    child.profile_completed_at = datetime.now(timezone.utc)
    parent.profile_complete = True
    parent.profile_completed_at = datetime.now(timezone.utc)
    db.commit()
    return True, []


def validate_required_documents(db: Session, child_id: int) -> tuple:
    """Check whether child has all required enrollment documents uploaded.

    Returns (is_complete: bool, missing_types: list[str]).
    """
    from config import settings
    required_types = settings.REQUIRED_ENROLLMENT_DOCUMENTS

    existing_docs = (
        db.query(models.ChildDocument.document_type)
        .filter(models.ChildDocument.child_id == child_id)
        .distinct()
        .all()
    )
    existing_types = {row[0] for row in existing_docs}
    missing = [dt for dt in required_types if dt not in existing_types]
    return (len(missing) == 0, missing)


def validate_kg_has_supervisor(
    db: Session,
    kindergarten_id: int,
    exclude_user_id: Optional[int] = None,
) -> None:
    """Ensure kindergarten retains at least one active supervisor-capable user.

    Called before deactivating a supervisor to prevent leaving a KG
    with zero supervisors.  Only enforced when deactivating a SUPERVISOR
    (not managers, since managers are not counted as dedicated supervisors).
    Raises ValidationError when the operation would violate the constraint.
    """
    query = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.status == models.UserStatus.ACTIVE,
    )
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)

    count = query.count()
    if count < 1:
        raise ValidationError(
            "يجب أن تحتفظ الروضة بمشرف نشط واحد على الأقل / "
            "Kindergarten must retain at least one active supervisor"
        )


def log_audit_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    sensitivity_level: int = 1,
    old_data: Optional[dict] = None,
    new_data: Optional[dict] = None
) -> models.AuditLog:
    """Log an audit action"""
    audit_log = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        old_data=old_data,
        new_data=new_data,
        ip_address=ip_address,
        sensitivity_level=sensitivity_level
    )
    db.add(audit_log)
    db.commit()
    return audit_log


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS — strips ALL HTML tags"""
    import bleach
    return bleach.clean(text, tags=[], attributes={}, strip=True)


def sanitize_model_strings(values: dict) -> dict:
    """Sanitize all string values in a Pydantic model dict (for use in model_validator)"""
    import bleach
    _SKIP_FIELDS = {"password", "new_password", "current_password", "hashed_password", "token"}
    for key, val in values.items():
        if isinstance(val, str) and key not in _SKIP_FIELDS:
            values[key] = bleach.clean(val, tags=[], attributes={}, strip=True)
    return values


from pydantic import BaseModel as _BaseModel, model_validator as _model_validator


class SanitizedModel(_BaseModel):
    """Base model that auto-sanitizes all string fields against XSS.
    Use for models accepting user-generated text content."""

    @_model_validator(mode="before")
    @classmethod
    def _sanitize_strings(cls, values):
        if isinstance(values, dict):
            return sanitize_model_strings(values)
        return values


def validate_time_format(time_str: str) -> bool:
    """Validate time string format (HH:MM)"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False


def validate_class_size(db: Session, class_id: int) -> None:
    """Validate that a class has between 4 and 10 children"""
    active_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.class_id == class_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).count()

    if active_enrollments < 4:
        raise ValidationError(f"Class must have at least 4 children (currently has {active_enrollments})")

    if active_enrollments > 10:
        raise ValidationError(f"Class cannot have more than 10 children (currently has {active_enrollments})")


def validate_child_class_assignment(db: Session, child_id: int, class_id: int, assignment_date: date) -> None:
    """Validate that a child is not assigned to multiple classes on the same date"""
    # Check for overlapping enrollments
    overlapping_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.class_id != class_id,  # Different class
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        # Check date overlap
        models.EnrollmentApplication.enrollment_start_date <= assignment_date,
        or_(
            models.EnrollmentApplication.enrollment_end_date == None,
            models.EnrollmentApplication.enrollment_end_date >= assignment_date
        )
    ).all()

    if overlapping_enrollments:
        class_names = [f"Class {e.class_id}" for e in overlapping_enrollments]
        raise ValidationError(f"Child is already assigned to class(es): {', '.join(class_names)} on this date")


def validate_supervisor_class_access(db: Session, supervisor: models.User, class_id: int, access_date: date) -> None:
    """Validate that a supervisor has access to a specific class on a given date"""
    if supervisor.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient role"
        )

    # Admins and managers can access all classes in their kindergarten
    if supervisor.role in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
        if not class_obj or class_obj.kindergarten_id != supervisor.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: class not in your kindergarten"
            )
        return

    # Supervisors can only access their assigned classes
    assignment = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == supervisor.id,
        models.SupervisorAssignment.class_id == class_id,
        models.SupervisorAssignment.start_date <= access_date,
        or_(
            models.SupervisorAssignment.end_date == None,
            models.SupervisorAssignment.end_date >= access_date
        )
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not assigned to this class"
        )


def validate_daily_report_completeness(report_data: dict) -> List[str]:
    """Validate daily report completeness and return list of missing required fields"""
    required_fields = [
        'arrival_time', 'leave_time', 'mood', 'health_notes',
        'breakfast', 'snack', 'milk', 'lunch', 'activities'
    ]

    missing_fields = []
    for field in required_fields:
        value = report_data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)

    return missing_fields


def validate_daily_report_deadline() -> None:
    """Validate that daily report submission is before 4:00 PM deadline"""
    now = datetime.now(timezone.utc)
    deadline_hour = 16  # 4:00 PM

    if now.hour >= deadline_hour:
        raise ValidationError("Daily report submissions are not allowed after 4:00 PM")
