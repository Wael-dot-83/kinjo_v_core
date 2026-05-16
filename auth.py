"""
Authentication and authorization services
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import models
from config import settings
from middleware.auth import classify_login_identifier

# Bcrypt limits: enforce up front (bytes, not characters)
MIN_PASSWORD_LENGTH = settings.PASSWORD_MIN_LENGTH
MAX_PASSWORD_BYTES = 72
# Hash for timing-safe checks when the user does not exist or the identifier is invalid.
DUMMY_PASSWORD_HASH = "$2b$12$vBtmA5VghNU59jI84xbECOmvwViP9goXmAm0AV.atG3R7q52blPX."


def validate_password_complexity(password: str) -> List[str]:
    """
    Validate password against complexity rules from config.
    Returns a list of failure reasons (empty = valid).
    """
    errors: List[str] = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long.")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        errors.append("Password cannot exceed 72 bytes when UTF-8 encoded.")
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        errors.append("Password must contain at least one special character.")
    return errors


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode("utf-8")
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode())
    except (ValueError, TypeError):
        return False


class PasswordValidator:
    """Thin shim kept for backward-compat with missing_endpoints.py."""

    @classmethod
    def validate(cls, password: str) -> tuple[bool, str]:
        errors = validate_password_complexity(password)
        if errors:
            return False, " ".join(errors)
        return True, ""

    @classmethod
    def check_breached(cls, password: str) -> bool:
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_jordan_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+962"):
        phone = "0" + phone[4:]
    elif phone.startswith("00962"):
        phone = "0" + phone[5:]
    elif phone.startswith("7") and len(phone) == 9:
        phone = "0" + phone
    return phone


def jordan_phone_login_variants(phone: str) -> list[str]:
    normalized = normalize_jordan_phone(phone)
    variants: list[str] = [normalized]
    if normalized.startswith("07"):
        local_no_zero = normalized[1:]
        intl = "+962" + local_no_zero
        intl_zero = "00962" + local_no_zero
        variants += [local_no_zero, intl, intl_zero]
    return list(dict.fromkeys(variants))


def get_password_hash(password: str) -> str:
    """
    Hash a password with bcrypt, enforcing complexity rules and safe length limits.
    """
    errors = validate_password_complexity(password)
    if errors:
        raise ValueError(" ".join(errors))

    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def normalize_phone_number(phone: str) -> Optional[str]:
    """Normalize a Jordanian phone number to 07XXXXXXXX format."""
    cleaned = re.sub(r"[\s\-\+]", "", str(phone or ""))
    if cleaned.startswith("962") and len(cleaned) == 12:
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("00962") and len(cleaned) == 14:
        cleaned = "0" + cleaned[5:]
    if re.fullmatch(r"07\d{8}", cleaned):
        return cleaned
    return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    """Authenticate a user by username, email, or phone number, with account lockout support."""
    from sqlalchemy import or_

    try:
        identifier_type, normalized_identifier = classify_login_identifier(username)
    except ValueError:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    filters = []
    if identifier_type == "phone":
        filters.append(models.User.phone_number == normalized_identifier)
    elif identifier_type == "email":
        filters.append(models.User.email == normalized_identifier)
    else:
        filters.extend(
            [
                models.User.username == normalized_identifier,
                models.User.email == normalized_identifier.lower(),
            ]
        )

    user = db.query(models.User).filter(or_(*filters)).first()
    if not user:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        return None

    if not verify_password(password, user.hashed_password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCKOUT_DURATION_MINUTES)
        db.commit()
        return None

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: models.UserRole,
    kindergarten_id: Optional[int] = None,
    must_change_password: bool = False,
) -> models.User:
    """Create a new user account."""
    hashed_password = get_password_hash(password)

    user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        kindergarten_id=kindergarten_id,
        status=models.UserStatus.ACTIVE,
        must_change_password=must_change_password,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def change_user_password(db: Session, user: models.User, new_password: str) -> None:
    """Change a user's password and clear must_change_password flag."""
    hashed_password = get_password_hash(new_password)

    now = datetime.now(timezone.utc)
    user.hashed_password = hashed_password
    user.must_change_password = False
    user.password_changed_at = now
    user.updated_at = now

    db.commit()


def requires_password_change(user: models.User) -> bool:
    """Check if user must change password (flag or age-based expiry)."""
    if user.must_change_password:
        return True

    max_age = settings.PASSWORD_MAX_AGE_DAYS
    if max_age > 0 and hasattr(user, "password_changed_at") and user.password_changed_at:
        age = datetime.now(timezone.utc) - user.password_changed_at
        if age > timedelta(days=max_age):
            return True

    return False
