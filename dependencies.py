"""
FastAPI Dependencies for KInJo platform
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import models
from database import get_db
from config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


def get_token_from_request(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_token: Optional[str] = Cookie(default=None)
) -> Optional[str]:
    """Extract token from Authorization header or cookie"""
    # First try Authorization header
    if token:
        return token
    
    # Then try cookie
    if kinjo_token:
        return kinjo_token
    
    # Check for token in request headers manually (backup)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    
    return None


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> models.User:
    """Get current authenticated user from JWT token (header or cookie)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try to get token from multiple sources
    token = None
    
    # 1. Authorization header (case-insensitive check)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]  # Skip "Bearer " or "bearer "
    
    # 2. Cookie
    if not token:
        token = request.cookies.get("kinjo_token")
    
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception

    if user.status != models.UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Verify user is active"""
    if current_user.status != models.UserStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_role(*roles: models.UserRole):
    """Dependency factory for role-based access control"""
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of these roles: {[r.value for r in roles]}"
            )
        return current_user
    return role_checker


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """Get current user if authenticated, None otherwise"""
    token = None
    
    # 1. Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    
    # 2. Cookie
    if not token:
        token = request.cookies.get("kinjo_token")
    
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user = db.query(models.User).filter(models.User.username == username).first()
    if user and user.status == models.UserStatus.ACTIVE:
        return user
    return None


# Common role dependencies
require_admin = require_role(models.UserRole.ADMIN)
require_manager = require_role(models.UserRole.ADMIN, models.UserRole.MANAGER)
require_supervisor = require_role(models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR)


class RedirectToLogin(Exception):
    """Exception to trigger redirect to login page"""
    def __init__(self, redirect_url: str = "/login"):
        self.redirect_url = redirect_url


async def get_current_user_or_redirect(
    request: Request,
    db: Session = Depends(get_db)
) -> models.User:
    """Get current user or redirect to login page (for frontend routes)"""
    token = None

    # 1. Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]

    # 2. Cookie
    if not token:
        token = request.cookies.get("kinjo_token")

    if not token:
        # Redirect to login with the original URL as redirect parameter
        redirect_url = f"/login?redirect={request.url.path}"
        raise RedirectToLogin(redirect_url)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise RedirectToLogin("/login?expired=true")
    except JWTError:
        raise RedirectToLogin("/login?expired=true")

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise RedirectToLogin("/login")

    if user.status != models.UserStatus.ACTIVE:
        raise RedirectToLogin("/login?inactive=true")

    return user
