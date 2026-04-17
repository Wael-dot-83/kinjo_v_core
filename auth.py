"""
Authentication and authorization services
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from config import settings
import models

# Bcrypt limits: enforce up front (bytes, not characters)
MIN_PASSWORD_LENGTH = settings.PASSWORD_MIN_LENGTH
MAX_PASSWORD_BYTES = 72


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
    """Verify a password against its hash"""
    password_bytes = plain_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_password.encode())


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
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    """Authenticate a user by username or email, with account lockout support."""
    from sqlalchemy import or_

    user = db.query(models.User).filter(
        or_(
            models.User.username == username,
            models.User.email == username
        )
    ).first()

    if not user:
        return None

    # Check if account is locked
    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        return None  # Account locked — return None (caller handles messaging)

    if not verify_password(password, user.hashed_password):
        # Increment failed login count
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCKOUT_DURATION_MINUTES)
        db.commit()
        return None

    # Successful login — reset lockout counters
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    return user


def create_user(db: Session, username: str, email: str, password: str,
                role: models.UserRole, kindergarten_id: Optional[int] = None,
                must_change_password: bool = False) -> models.User:
    """Create a new user account"""
    hashed_password = get_password_hash(password)

    user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        kindergarten_id=kindergarten_id,
        status=models.UserStatus.ACTIVE,
        must_change_password=must_change_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def change_user_password(db: Session, user: models.User, new_password: str) -> None:
    """Change a user's password and clear must_change_password flag"""
    hashed_password = get_password_hash(new_password)
    
    now = datetime.now(timezone.utc)
    user.hashed_password = hashed_password
    user.must_change_password = False
    user.password_changed_at = now
    user.updated_at = now
    
    db.commit()


def requires_password_change(user: models.User) -> bool:
    """Check if user must change password (flag or age-based expiry)"""
    if user.must_change_password:
        return True

    # Enforce PASSWORD_MAX_AGE_DAYS if configured (0 = disabled)
    max_age = settings.PASSWORD_MAX_AGE_DAYS
    if max_age > 0 and hasattr(user, "password_changed_at") and user.password_changed_at:
        age = datetime.now(timezone.utc) - user.password_changed_at
        if age > timedelta(days=max_age):
            return True

    return False
