"""
Authentication and authorization services
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from config import settings
import models

# Bcrypt limits: enforce up front (bytes, not characters)
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    password_bytes = plain_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_password.encode())


def get_password_hash(password: str) -> str:
    """
    Hash a password with bcrypt, enforcing safe length limits to avoid
    bcrypt's 72-byte truncation/ValueError edge cases.
    """
    password_bytes = password.encode("utf-8")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Password must be at least 8 characters long.")

    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError("Password cannot exceed 72 bytes when UTF-8 encoded.")

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
    """Authenticate a user by username or email"""
    from sqlalchemy import or_

    user = db.query(models.User).filter(
        or_(
            models.User.username == username,
            models.User.email == username
        )
    ).first()

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_user(db: Session, username: str, email: str, password: str,
                role: models.UserRole, kindergarten_id: Optional[int] = None) -> models.User:
    """Create a new user account"""
    hashed_password = get_password_hash(password)

    user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        kindergarten_id=kindergarten_id,
        status=models.UserStatus.ACTIVE
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
