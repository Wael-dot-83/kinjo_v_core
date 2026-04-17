"""
FastAPI Dependencies for KInJo platform
"""
from typing import Optional

from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import models
from database import get_db
from config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


def _extract_bearer_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    header = value.strip()
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None


def _get_request_token(request: Request, token: Optional[str], session_cookie: Optional[str], legacy_cookie: Optional[str]) -> Optional[str]:
    """Resolve JWT from bearer auth first, then secure session cookie, then legacy cookie."""
    bearer_token = _extract_bearer_token(token)
    if bearer_token:
        return bearer_token

    auth_header = _extract_bearer_token(request.headers.get("Authorization"))
    if auth_header:
        return auth_header

    if session_cookie:
        return session_cookie

    if legacy_cookie:
        return legacy_cookie

    return None


def get_token_from_request(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_session: Optional[str] = Cookie(default=None),
    kinjo_token: Optional[str] = Cookie(default=None),
) -> Optional[str]:
    """Extract token from Authorization header or cookie"""
    return _get_request_token(request, token, kinjo_session, kinjo_token)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_session: Optional[str] = Cookie(default=None),
    kinjo_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
) -> models.User:
    """Get current authenticated user from JWT token (header or cookie)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = _get_request_token(request, token, kinjo_session, kinjo_token)
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
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


async def get_current_user_with_password_check(
    request: Request,
    db: Session = Depends(get_db)
) -> models.User:
    """Get current user and check if password change is required"""
    user = await get_current_user(request, db)
    
    # Import here to avoid circular imports
    from auth import requires_password_change
    
    if requires_password_change(user):
        # Redirect to password change page instead of allowing access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
            headers={"X-Password-Change-Required": "true"}
        )
    
    return user


async def get_current_admin_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الإجراء متاح للإداريين فقط"
        )
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
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_session: Optional[str] = Cookie(default=None),
    kinjo_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """Get current user if authenticated, None otherwise"""
    token = _get_request_token(request, token, kinjo_session, kinjo_token)
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user = db.query(models.User).filter(models.User.username == username).first()
    if user and user.status == models.UserStatus.ACTIVE:
        return user
    return None

def require_manager_with_kindergarten():
    """Dependency that ensures manager role and returns their kindergarten_id"""
    async def manager_kg_checker(
        current_user: models.User = Depends(require_manager)
    ) -> int:
        if not current_user.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager must be assigned to a kindergarten"
            )
        return current_user.kindergarten_id
    return manager_kg_checker


def require_kindergarten_scoped_access(allow_admin: bool = True):
    """
    Dependency factory for kindergarten-scoped access.
    - Admin: Can access any kindergarten
    - Manager/Supervisor: Can only access their assigned kindergarten
    Returns the allowed kindergarten_id(s) for the current user.
    """
    async def kg_scope_checker(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> list[int]:
        if current_user.role == models.UserRole.ADMIN and allow_admin:
            # Admin can access all kindergartens
            from models import Kindergarten
            kg_ids = db.query(Kindergarten.id).all()
            return [kg.id for kg in kg_ids]
        elif current_user.role in {models.UserRole.MANAGER, models.UserRole.SUPERVISOR}:
            if not current_user.kindergarten_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User must be assigned to a kindergarten"
                )
            return [current_user.kindergarten_id]
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
    return kg_scope_checker

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
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_session: Optional[str] = Cookie(default=None),
    kinjo_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
) -> models.User:
    """Get current user or redirect to login page (for frontend routes)"""
    from config import settings

    token = _get_request_token(request, token, kinjo_session, kinjo_token)
    if not token:
        # Redirect to login with the original URL as redirect parameter
        redirect_url = f"/login?redirect={request.url.path}"
        raise RedirectToLogin(redirect_url)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
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
