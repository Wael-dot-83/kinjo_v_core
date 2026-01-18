"""
Authentication and authorization services
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from config import settings
import models


# Password hashing - explicitly set backend to avoid bcrypt compatibility issues
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# Handle bcrypt compatibility issues
try:
    import bcrypt
    # Check if bcrypt has the __about__ attribute
    if not hasattr(bcrypt, '__about__'):
        # For newer bcrypt versions, manually set the version
        bcrypt.__about__ = type('about', (), {'__version__': '4.0.0'})()
except ImportError:
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


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
