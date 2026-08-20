"""
FastAPI Dependencies for KinJo platform
"""
import logging
from enum import Enum
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import models
from database import get_db
from config import settings
from session_service import SessionInvalid

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)

def _enforce_access_session(payload: dict, user: models.User, request: Request) -> None:
    """Validate the per-token server-side binding and cache it on the request."""
    from session_service import SessionStoreUnavailable, validate_and_refresh_access_session

    jti = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if not isinstance(jti, str) or not jti:
        raise SessionInvalid("Access token is missing jti")
    try:
        jwt_iat = int(issued_at)
        jwt_expires_at = float(expires_at)
    except (TypeError, ValueError) as exc:
        raise SessionInvalid("Access token timestamps are invalid") from exc

    try:
        validate_and_refresh_access_session(
            user.username,
            jti,
            jwt_iat=jwt_iat,
            jwt_expires_at=jwt_expires_at,
            password_changed_at=user.password_changed_at,
        )
    except SessionStoreUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication security store is unavailable.",
        ) from exc

    request.state.session_username = user.username
    request.state.session_jti = jti


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
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            raise credentials_exception
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(
        models.User.username == username,
        models.User.deleted_at.is_(None),
    ).first()
    if user is None:
        raise credentials_exception

    if user.status != models.UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    # Temporary and expired credentials may authenticate only long enough to
    # replace the password. Enforce this centrally so no API can bypass the
    # policy by using a different router dependency.
    from auth import requires_password_change

    if requires_password_change(user) and request.url.path not in {
        "/api/users/change-password",
        "/users/change-password",
        "/api/supervisor/change-password",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
            headers={"X-Password-Change-Required": "true"},
        )

    try:
        _enforce_access_session(payload, user, request)
    except SessionInvalid:
        raise credentials_exception

    impersonated_by = payload.get("impersonated_by")
    if impersonated_by is not None:
        try:
            impersonated_by = int(impersonated_by)
        except (TypeError, ValueError):
            raise credentials_exception
        db.info["impersonated_by"] = impersonated_by
        db.info["impersonation_reason"] = payload.get("impersonation_reason")
        request.state.impersonated_by = impersonated_by
    else:
        db.info.pop("impersonated_by", None)
        db.info.pop("impersonation_reason", None)

    # Cache resolved id on request.state so middleware (e.g. structured access log)
    # can read it without re-decoding the JWT.
    try:
        request.state.user_id = user.id
    except Exception:
        pass

    return user


async def get_current_user_with_password_check(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    kinjo_session: Optional[str] = Cookie(default=None),
    kinjo_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
) -> models.User:
    """Get current user and check if password change is required"""
    user = await get_current_user(
        request=request,
        token=token,
        kinjo_session=kinjo_session,
        kinjo_token=kinjo_token,
        db=db,
    )

    # Import here to avoid circular imports
    from auth import requires_password_change

    if requires_password_change(user):
        # Reject with 403 so API callers receive a clear signal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
            headers={"X-Password-Change-Required": "true"},
        )

    return user


async def get_current_admin_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    if not has_permission(current_user, Permission.ADMIN_PANEL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access only"
        )
    return current_user


def require_role(*roles: models.UserRole):
    """Dependency factory for role-based access control"""
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied."
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
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            return None
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user = db.query(models.User).filter(
        models.User.username == username,
        models.User.deleted_at.is_(None),
    ).first()
    if user and user.status == models.UserStatus.ACTIVE:
        try:
            _enforce_access_session(payload, user, request)
        except SessionInvalid:
            return None
        impersonated_by = payload.get("impersonated_by")
        if impersonated_by is not None:
            try:
                impersonated_by = int(impersonated_by)
            except (TypeError, ValueError):
                return None
            db.info["impersonated_by"] = impersonated_by
            db.info["impersonation_reason"] = payload.get("impersonation_reason")
            request.state.impersonated_by = impersonated_by
        else:
            db.info.pop("impersonated_by", None)
            db.info.pop("impersonation_reason", None)
        return user
    return None

def require_manager_with_kindergarten():
    """Dependency that ensures manager role and returns their kindergarten_id"""
    async def manager_kg_checker(
        current_user: models.User = Depends(require_admin_or_manager)
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

# =============================================================================
# ADMIN-001 — Centralized permission model
# =============================================================================
# Replaces the inline role-comparison checks that were scattered
# across endpoints and service helpers with one declarative permission layer.
#
# Three entry points, one policy table:
#   require_permission(*perms)          FastAPI dependency  -> use with Depends()
#   enforce_permission(user, *perms)    imperative guard    -> raises 403
#   has_permission(user, *perms)        predicate           -> returns bool
#
# The predicate form exists because a large share of the replaced checks were
# not gates but *branches* ("admin sees every kindergarten, everyone else is
# scoped"), and rewriting those as gates would change behaviour.


class Permission(str, Enum):
    """Discrete capabilities that can be granted to a role."""

    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    USER_MANAGE = "admin:users:manage"
    KG_READ = "admin:kindergartens:read"
    KG_WRITE = "admin:kindergartens:write"
    REPORT_EXPORT = "admin:reports:export"
    REPORT_GENERATE = "admin:reports:generate"
    IMPERSONATE = "admin:impersonate"
    AUDIT_READ = "admin:audit:read"
    SYSTEM_HEALTH = "admin:system:health"

    # --- Extensions beyond the specification's enum (ADMIN-001) ---------------
    # ADMIN_PANEL: the spec grants MANAGER the ADMIN_READ permission, so mapping
    # the existing ``require_admin`` dependency onto ADMIN_READ would silently
    # open every admin-only endpoint to managers. ADMIN_PANEL preserves today's
    # admin-only semantics without weakening the spec's role table.
    ADMIN_PANEL = "admin:panel"
    # SCOPE_ALL: "this actor is not restricted to an assigned kindergarten or
    # governorate". Carries the branch semantics of the old compound checks.
    SCOPE_ALL = "admin:scope:all"


# Role -> permission grants. Admin is handled by the ``is_admin`` short-circuit
# in the checkers below, but is listed explicitly so the table is readable and
# so ``ROLE_PERMISSIONS`` can be introspected by tests and audit tooling.
ROLE_PERMISSIONS: "dict[models.UserRole, list[Permission]]" = {
    models.UserRole.ADMIN: list(Permission),
    models.UserRole.SUPERVISOR: [
        Permission.KG_READ,
        Permission.REPORT_GENERATE,
    ],
    models.UserRole.MANAGER: [
        Permission.ADMIN_READ,
        Permission.KG_READ,
        Permission.KG_WRITE,
        Permission.REPORT_GENERATE,
        Permission.REPORT_EXPORT,
    ],
    models.UserRole.PARENT: [],
}

_INSUFFICIENT_PERMISSIONS_AR = "ليس لديك الصلاحية المطلوبة"
_INSUFFICIENT_PERMISSIONS_EN = "You do not have the required permission"


def permissions_for_role(role: "models.UserRole") -> "set[Permission]":
    """Return the permission set granted to *role* (empty for unknown roles)."""
    return set(ROLE_PERMISSIONS.get(role, ()))


def has_permission(user: Optional["models.User"], *permissions: Permission) -> bool:
    """True when *user* holds every one of *permissions*.

    Predicate form — use inside compound conditions. An unauthenticated user
    (``None``) holds nothing.
    """
    if user is None:
        return False
    if user.role == models.UserRole.ADMIN:
        return True
    granted = permissions_for_role(user.role)
    return all(p in granted for p in permissions)


def missing_permissions(user: Optional["models.User"], *permissions: Permission) -> "list[Permission]":
    """Return the subset of *permissions* that *user* does not hold."""
    if user is None:
        return list(permissions)
    if user.role == models.UserRole.ADMIN:
        return []
    granted = permissions_for_role(user.role)
    return [p for p in permissions if p not in granted]


def permission_denied(missing: "list[Permission]") -> HTTPException:
    """Build the bilingual 403 raised on a failed permission check."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "INSUFFICIENT_PERMISSIONS",
            "message": _INSUFFICIENT_PERMISSIONS_AR,
            "message_ar": _INSUFFICIENT_PERMISSIONS_AR,
            "message_en": _INSUFFICIENT_PERMISSIONS_EN,
            "missing": [p.value for p in missing],
        },
    )


def enforce_permission(user: Optional["models.User"], *permissions: Permission) -> "models.User":
    """Imperative guard — raise 403 unless *user* holds every permission.

    For service-layer helpers and non-endpoint call sites, where a FastAPI
    dependency is not available.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    missing = missing_permissions(user, *permissions)
    if missing:
        raise permission_denied(missing)
    return user


def require_permission(*permissions: Permission):
    """FastAPI dependency factory — ``Depends(require_permission(Permission.X))``.

    Returns the checker callable itself (not a pre-wrapped ``Depends``) so the
    same factory works both as a dependency and as a direct call on a user
    object, which is how the specification uses it in both §2.1 and §5.1.
    """

    def checker(current_user: "models.User" = Depends(get_current_user)) -> "models.User":
        return enforce_permission(current_user, *permissions)

    return checker


def has_role(user: Optional["models.User"], *roles: "models.UserRole") -> bool:
    """True when *user* holds one of *roles*.

    Predicate replacement for the inline role-identity comparisons. Roles are
    identity, not capability: a parent-only or supervisor-only endpoint is not
    expressible as an admin permission grant, so those guards keep using roles
    while routing through this single helper.
    """
    if user is None:
        return False
    return user.role in roles


def enforce_role(
    user: Optional["models.User"],
    *roles: "models.UserRole",
    detail: str = "Access denied.",
) -> "models.User":
    """Imperative guard — raise 403 unless *user* holds one of *roles*."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if not has_role(user, *roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return user


def has_global_scope(user: Optional["models.User"]) -> bool:
    """True when *user* is not restricted to an assigned kindergarten/governorate.

    Replacement for the ``role != ADMIN and not allowed_kgs`` branch idiom.
    """
    return has_permission(user, Permission.SCOPE_ALL)


# Common role dependencies
require_admin = require_role(models.UserRole.ADMIN)
require_admin_or_manager = require_role(models.UserRole.ADMIN, models.UserRole.MANAGER)
require_supervisor = require_role(models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR)


class ParentIdentity:
    """Bundle of the authenticated parent user and their ParentProfile.

    Returned by :func:`get_current_parent` so parent-facing endpoints stop
    re-implementing the same role guard + profile lookup (single enforcement
    point for parent authorization).
    """

    __slots__ = ("user", "profile")

    def __init__(self, user: "models.User", profile: "models.ParentProfile"):
        self.user = user
        self.profile = profile


def get_current_parent(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ParentIdentity:
    """Dependency for parent-only endpoints.

    Enforces the PARENT role and resolves the caller's ParentProfile in one
    place, raising the same localized 403/404 the handlers used inline.
    """
    from i18n import gettext as _

    lang = getattr(current_user, "preferred_language", None) or "ar"

    if not has_role(current_user, models.UserRole.PARENT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Parent access only", lang))

    profile = (
        db.query(models.ParentProfile)
        .filter(models.ParentProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Parent profile not found", lang))

    return ParentIdentity(user=current_user, profile=profile)


# ---------------------------------------------------------------------------
# Manager / supervisor kindergarten scoping — single source of truth (S2)
# ---------------------------------------------------------------------------

class ManagerScope:
    """Canonical kindergarten-scope checks for manager/supervisor endpoints.

    Consolidates the previously-overlapping helpers (manager_scope.ManagerScope,
    rbac.assert_manager_owns_kindergarten, routers.manager._require_manager) into
    one place with one policy:

    - ADMIN may access any kindergarten.
    - MANAGER/SUPERVISOR are restricted to their own kindergarten; a cross-tenant
      target returns 404 (never 403 — do not leak that the resource exists).
    - A non-admin with no kindergarten association is a misconfigured account: 400.
    """

    _SCOPED_ROLES = (models.UserRole.MANAGER, models.UserRole.SUPERVISOR)

    @staticmethod
    def validate_manager(user: models.User) -> None:
        """Require MANAGER role with a kindergarten assigned."""
        if not has_role(user, models.UserRole.MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="This operation requires manager role")
        if not user.kindergarten_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Manager must be assigned to a kindergarten")

    @staticmethod
    def get_manager_kindergarten_id(user: models.User) -> int:
        """Return the caller's own kindergarten id (manager/supervisor)."""
        if user.role == models.UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Admins do not have a single assigned kindergarten")
        if not user.kindergarten_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="User must be assigned to a kindergarten")
        return user.kindergarten_id

    @staticmethod
    def assert_kindergarten_access(user: models.User, target_kindergarten_id: int) -> None:
        """Authorize access to a specific kindergarten (IDOR guard)."""
        if user.role == models.UserRole.ADMIN:
            return
        if user.role in ManagerScope._SCOPED_ROLES:
            if not user.kindergarten_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="User must be assigned to a kindergarten")
            if user.kindergarten_id != target_kindergarten_id:
                # 404, not 403 — do not reveal that another tenant's resource exists.
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="Resource not found")
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Insufficient permissions")


def require_manager(current_user: models.User = Depends(get_current_user)) -> models.User:
    """FastAPI dependency for manager-only endpoints: MANAGER role + own KG.

    Returns 403 for a non-manager and 403 for a manager with no kindergarten
    association (a NULL-scoped account has nothing in scope). 403 (rather than
    the spec's suggested 400) is kept here so all manager routes agree with the
    existing /api/manager/dashboard and /api/absence-requests guards; moving the
    whole app to 400 would require touching the app-wide validators.validate_
    manager_role callers, which is outside this change.
    """
    if not has_role(current_user, models.UserRole.MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Manager access only.")
    if current_user.kindergarten_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No kindergarten is associated with this account.")
    return current_user


# ---------------------------------------------------------------------------
# Shared class-scope helpers (single source of truth for class lookups)
# ---------------------------------------------------------------------------

def get_class_or_404(db, class_id: int, *, include_deleted: bool = False) -> "models.Class":
    """Fetch a class by id, 404 if missing. Soft-deleted classes are hidden
    unless include_deleted=True, so normal APIs never surface them."""
    q = db.query(models.Class).filter(models.Class.id == class_id)
    if not include_deleted:
        q = q.filter(models.Class.deleted_at.is_(None))
    cls = q.first()
    if cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return cls


def get_class_for_user_or_404(
    db,
    class_id: int,
    current_user: models.User,
    *,
    include_deleted: bool = False,
) -> "models.Class":
    """Fetch a class enforcing role + kindergarten scope (IDOR guard).

    Policy (consistent with ManagerScope, S2/#14):
      - ADMIN: any class.
      - MANAGER / SUPERVISOR: only their own kindergarten's class; a cross-tenant
        id returns 404 (never 403) so we don't leak that it exists.
      - Any other role (e.g. PARENT): 403.
      - Manager/supervisor with no kindergarten: 400 (misconfigured account).
    Soft-deleted classes are hidden (404) unless include_deleted=True.
    """
    cls = get_class_or_404(db, class_id, include_deleted=include_deleted)
    ManagerScope.assert_kindergarten_access(current_user, cls.kindergarten_id)
    return cls


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
        original_url = request.url.path
        if request.url.query:
            original_url = f"{original_url}?{request.url.query}"
        redirect_url = f"/login?redirect={quote(original_url, safe='')}"
        raise RedirectToLogin(redirect_url)

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("purpose"):
            raise RedirectToLogin("/login?expired=true")
        username: str = payload.get("sub")
        if username is None:
            logger.error("JWT payload missing 'sub'")
            raise RedirectToLogin("/login?expired=true")
    except JWTError as e:
        logger.error(f"JWTError in get_current_user_or_redirect: {str(e)} | token: {token[:10]}...")
        raise RedirectToLogin("/login?expired=true")

    user = db.query(models.User).filter(
        models.User.username == username,
        models.User.deleted_at.is_(None),
    ).first()
    if user is None:
        logger.error(f"User not found for username: {username}")
        raise RedirectToLogin("/login")

    if user.status != models.UserStatus.ACTIVE:
        raise RedirectToLogin("/login?inactive=true")

    try:
        _enforce_access_session(payload, user, request)
    except SessionInvalid:
        raise RedirectToLogin("/login?expired=true")
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            raise
        raise RedirectToLogin("/login?expired=true")

    # Cache resolved id on request.state so middleware can read it without re-decoding the JWT.
    try:
        request.state.user_id = user.id
    except Exception:
        pass

    # Enforce server-side must_change_password — redirect to /change-password
    # unless the user is already on that page (prevents infinite redirect loop).
    from auth import requires_password_change
    if requires_password_change(user) and request.url.path != "/change-password":
        raise RedirectToLogin("/change-password")

    return user
