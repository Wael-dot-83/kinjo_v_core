"""
Admin impersonation endpoints.

POST /api/admin/impersonate         — start impersonating a manager
POST /api/admin/exit-impersonation  — end impersonation and return to admin identity
GET  /api/admin/managers            — list managers (for the picker UI)
GET  /api/admin/impersonate/audit   — recent impersonation audit log entries
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

_JORDAN_TZ = timezone(timedelta(hours=3))

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import logging
import uuid

from audit_actions import AuditAction
from database import get_db
from models import AuditLog, Kindergarten, User, UserRole, UserStatus
from rate_limiter import limiter
from config import settings
from auth import create_access_token
from cache_service import cache_service
from session_service import revoke_access_session
from dependencies import Permission, get_current_user, has_role, require_permission
from rbac import IMPERSONATION_COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter()

_require_admin = require_permission(Permission.IMPERSONATE)

# ADMIN-003 section 2.2 -- hard limits, none of them configurable at runtime.
IMPERSONATION_MAX_DURATION_MINUTES = 30
IMPERSONATION_CHAIN_MAX_DEPTH = 1   # A->B only, never A->B->C
IMPERSONATION_MAX_SESSIONS_PER_DAY = 5


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ImpersonateRequest(BaseModel):
    target_user_id: int
    reason: str = Field(..., min_length=3, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> Optional[str]:
    client = request.client
    return client.host if client else None


def _set_auth_cookie(response: JSONResponse, token: str, *, max_age: int) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=True,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _rotate_csrf_cookie(response: JSONResponse, *, max_age: int) -> None:
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=secrets.token_hex(32),
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=False,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _set_restore_cookie(response: JSONResponse, token: str, *, max_age: int) -> None:
    response.set_cookie(
        key=IMPERSONATION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=True,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _write_audit(
    db: Session,
    *,
    admin_id: int,
    target_id: int,
    action: str,
    reason: Optional[str],
    ip: Optional[str],
    session_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    details = {"reason": reason}
    if extra:
        details.update(extra)
    entry = AuditLog(
        user_id=admin_id,          # actor who performed the action
        action=action,
        entity_type="User",
        entity_id=target_id,       # subject being impersonated
        details=json.dumps(details, ensure_ascii=False),
        ip_address=ip,
        sensitivity_level=4,
        impersonated_by=admin_id,
        impersonation_reason=reason,
        impersonation_session_id=session_id,
    )
    db.add(entry)
    db.commit()


def _jordan_day_start() -> datetime:
    """Midnight today in Jordan (UTC+3), as an aware datetime."""
    now = datetime.now(_JORDAN_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _sessions_started_today(db: Session, admin_id: int) -> int:
    """Count this admin's impersonation starts since Jordan midnight.

    Counted from the audit table rather than a cache counter: the cache falls
    back to an in-process dict when Redis is unavailable, which would give each
    worker its own quota. The audit log is the record of truth and survives a
    restart.
    """
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.action == AuditAction.IMPERSONATION_START,
            AuditLog.user_id == admin_id,
            AuditLog.created_at >= _jordan_day_start(),
        )
        .count()
    )


def _is_currently_impersonating(request: Request) -> bool:
    """True when this request is already running inside an impersonation.

    Two independent signals, because either alone can be spoofed away by
    dropping a cookie: the restore cookie that exit-impersonation consumes,
    and the ``impersonated_by`` claim the access token carries.
    """
    if request.cookies.get(IMPERSONATION_COOKIE_NAME):
        return True
    return getattr(request.state, "impersonated_by", None) is not None


def _notify_target(target: User, admin: User, started_at: datetime, ip: Optional[str]) -> bool:
    """Tell the target their account was accessed. Returns whether mail went out.

    Requirement 4 of section 2.2. A failure here is recorded in the audit entry
    rather than swallowed: an SMTP outage must be visible to whoever reviews the
    log, not silently turn the notification into a no-op.
    """
    if not target.email:
        return False

    admin_name = admin.full_name or admin.username
    when = started_at.strftime("%Y-%m-%d %H:%M")
    where = ip or "unknown"

    # TODO(i18n-review): ADMIN-I18N-001 -- the Arabic subject and body below
    # were authored here, not taken from the specification (its Arabic did not
    # survive PDF extraction). This text reaches a real user as a security
    # notice, so it should get the native-speaker pass first.
    subject = "تنبيه أمني: تم الوصول إلى حسابك | Security alert: your account was accessed"
    body = "\n".join([
        f"قام المسؤول {admin_name} بالوصول إلى حسابك بتاريخ {when} "
        f"(بتوقيت الأردن) من عنوان IP {where}.",
        "إذا لم يكن هذا الوصول مصرحاً به، يرجى التواصل مع الدعم فوراً.",
        "",
        "-----",
        "",
        f"Admin {admin_name} accessed your account at {when} (Jordan time) "
        f"from IP {where}.",
        "If this was not authorized, contact support.",
        "",
    ])

    try:
        from email_service import send_email

        send_email(target.email, subject, body)
        return True
    except Exception:
        logger.warning(
            "Impersonation notification could not be delivered to user %s", target.id,
            exc_info=True,
        )
        return False


# ---------------------------------------------------------------------------
# Start impersonation
# ---------------------------------------------------------------------------

@router.post("/impersonate", status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def start_impersonation(
    payload: ImpersonateRequest,
    request: Request,
    current_admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    ip = _get_ip(request)

    def _deny(reason: str, status_code: int, detail: str, target_id: int):
        """Record the refused attempt, then raise. Every refusal is auditable."""
        _write_audit(
            db,
            admin_id=current_admin.id,
            target_id=target_id,
            action=AuditAction.IMPERSONATION_ATTEMPT_FAILED,
            reason=reason,
            ip=ip,
        )
        raise HTTPException(status_code=status_code, detail=detail)

    # Requirement 3: chain prevention. Checked before anything else so an
    # already-impersonating session cannot even probe for valid targets.
    if _is_currently_impersonating(request):
        _deny(
            "Chained impersonation refused: session is already impersonating",
            status.HTTP_409_CONFLICT,
            "Already impersonating. Exit the current session first.",
            payload.target_user_id,
        )

    # Requirement 8: daily quota, counted from the audit log.
    used_today = _sessions_started_today(db, current_admin.id)
    if used_today >= IMPERSONATION_MAX_SESSIONS_PER_DAY:
        _deny(
            f"Daily impersonation quota exhausted ({used_today}/"
            f"{IMPERSONATION_MAX_SESSIONS_PER_DAY})",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily impersonation limit reached.",
            payload.target_user_id,
        )

    # Requirement 1: never yourself. Checked against the id rather than the
    # role so it holds even if the role table changes later.
    if payload.target_user_id == current_admin.id:
        _deny(
            "Self-impersonation refused",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "You cannot impersonate yourself.",
            payload.target_user_id,
        )

    target = db.query(User).filter(
        User.id == payload.target_user_id,
        User.deleted_at.is_(None),
        User.status == UserStatus.ACTIVE,
    ).first()
    if not target:
        _deny(
            f"User not found: {payload.target_user_id}",
            status.HTTP_404_NOT_FOUND,
            "User not found.",
            payload.target_user_id,
        )

    # Requirement 2: never another admin.
    if has_role(target, UserRole.ADMIN):
        _deny(
            "Admin-to-admin impersonation refused",
            status.HTTP_403_FORBIDDEN,
            "Administrators cannot be impersonated.",
            target.id,
        )

    if not has_role(target, UserRole.MANAGER):
        _deny(
            f"Target role is {target.role.value}, not MANAGER",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only managers can be impersonated.",
            target.id,
        )

    session_id = str(uuid.uuid4())
    started_at_dt = datetime.now(_JORDAN_TZ)
    started_at = started_at_dt.isoformat()
    # Requirement 5: 30 minutes, hard. Never longer than the platform's own
    # access-token lifetime, and never extendable -- there is no refresh path
    # for an impersonated token, so expiry ends the session outright.
    lifetime = min(settings.ACCESS_TOKEN_EXPIRE_MINUTES, IMPERSONATION_MAX_DURATION_MINUTES)
    expires_at = (started_at_dt + timedelta(minutes=lifetime)).isoformat()
    max_age = lifetime * 60
    target_token = create_access_token(
        {
            "sub": target.username,
            "role": target.role.value,
            "impersonated_by": current_admin.id,
            "impersonation_reason": payload.reason,
            # Requirement 6: rides on every request made as the target, so the
            # before_flush audit listener can stamp each row it writes.
            "impersonation_session_id": session_id,
        },
        expires_delta=timedelta(minutes=lifetime),
    )
    restore_token = create_access_token(
        {
            "sub": current_admin.username,
            "purpose": "impersonation_restore",
            "admin_id": current_admin.id,
            "target_user_id": target.id,
            "target_username": target.username,
            "target_display_name": target.full_name or target.username,
            "target_role": target.role.value,
            "started_at": started_at,
            "expires_at": expires_at,
            "impersonation_session_id": session_id,
            "jti": secrets.token_urlsafe(24),
        },
        expires_delta=timedelta(minutes=lifetime),
    )

    # Requirement 4: notify the target. The outcome is audited either way, so a
    # dead SMTP shows up in the log instead of silently skipping the notice.
    notified = _notify_target(target, current_admin, started_at_dt, ip)

    _write_audit(
        db,
        admin_id=current_admin.id,
        target_id=target.id,
        action=AuditAction.IMPERSONATION_START,
        reason=payload.reason,
        ip=ip,
        session_id=session_id,
        extra={
            "impersonation_session_id": session_id,
            "expires_at": expires_at,
            "target_notified": notified,
            "sessions_used_today": used_today + 1,
        },
    )

    kg_name = ""
    if target.kindergarten_id:
        kg = db.query(Kindergarten).filter(Kindergarten.id == target.kindergarten_id).first()
        kg_name = kg.name_ar if kg else ""

    target_display = target.full_name or target.username
    response = JSONResponse({
        "message": "Impersonation started.",
        "session_id": session_id,
        "expires_at": expires_at,
        "target_notified": notified,
        "impersonating": {
            "user_id": target.id,
            "username": target.username,
            "name": target_display,
            "role": target.role.value,
            "kindergarten_name": kg_name,
        },
        # Requirement 7: the banner text the UI must display, supplied by the
        # server so both languages stay in one place.
        "banner": {
            # TODO(i18n-review): ADMIN-I18N-001 -- Arabic banner text authored here.
            "ar": f"أنت تعمل باسم {target_display} — تنتهي الجلسة في {expires_at}",
            "en": f"You are acting as {target_display} — session ends at {expires_at}",
        },
    })
    _set_auth_cookie(response, target_token, max_age=max_age)
    _set_restore_cookie(response, restore_token, max_age=max_age)
    _rotate_csrf_cookie(response, max_age=max_age)
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Exit impersonation
# ---------------------------------------------------------------------------

@router.post("/exit-impersonation", status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def exit_impersonation(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restore_token = request.cookies.get(IMPERSONATION_COOKIE_NAME)
    if not restore_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not currently impersonating.")
    try:
        imp_data = jwt.decode(restore_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Impersonation session is invalid or expired.")
    if imp_data.get("purpose") != "impersonation_restore":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid impersonation session.")
    restore_jti = imp_data.get("jti")
    if not restore_jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Impersonation session has been revoked.")
    if imp_data.get("target_user_id") != current_user.id or imp_data.get("target_username") != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Impersonation identity mismatch.")

    admin = db.query(User).filter(
        User.id == imp_data.get("admin_id"),
        User.username == imp_data.get("sub"),
        User.role == UserRole.ADMIN,
        User.status == UserStatus.ACTIVE,
        User.deleted_at.is_(None),
    ).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Original administrator is unavailable.")

    target_id = current_user.id

    now = int(datetime.now(timezone.utc).timestamp())
    ttl = max(1, int(imp_data.get("exp", now + 1)) - now)
    consumed = cache_service.add_if_absent(
        f"impersonation_restore_revoked:{restore_jti}", True, ttl_seconds=ttl
    )
    if consumed is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Impersonation security store is unavailable.",
        )
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Impersonation session has been revoked.",
        )

    # The target access token is a normal independently tracked session.  The
    # cookie replacement below is not revocation: a captured bearer would
    # otherwise remain usable until its JWT expiry.
    target_session_username = getattr(request.state, "session_username", None)
    target_session_jti = getattr(request.state, "session_jti", None)
    if target_session_username and target_session_jti:
        revoke_access_session(target_session_username, target_session_jti)

    _write_audit(
        db,
        admin_id=admin.id,
        target_id=target_id,
        action=AuditAction.IMPERSONATION_END,
        reason=None,
        ip=_get_ip(request),
    )

    lifetime = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    max_age = lifetime * 60
    admin_token = create_access_token(
        {"sub": admin.username, "role": admin.role.value},
        expires_delta=timedelta(minutes=lifetime),
    )
    response = JSONResponse({"message": "Impersonation ended."})
    _set_auth_cookie(response, admin_token, max_age=max_age)
    _rotate_csrf_cookie(response, max_age=max_age)
    response.delete_cookie(
        key=IMPERSONATION_COOKIE_NAME,
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Audit log (last N impersonation events)
# ---------------------------------------------------------------------------

@router.get("/impersonate/audit")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def impersonation_audit(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_([AuditAction.IMPERSONATION_START, AuditAction.IMPERSONATION_END]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    user_ids = {r.impersonated_by for r in rows if r.impersonated_by} | \
               {r.entity_id for r in rows if r.entity_id}
    users = {u.id: (u.full_name or u.username) for u in
             db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return {
        "events": [
            {
                "id": r.id,
                "action": r.action,
                "admin_id": r.impersonated_by,
                "admin_name": users.get(r.impersonated_by, ""),
                "target_user_id": r.entity_id,
                "target_name": users.get(r.entity_id, ""),
                "reason": r.impersonation_reason,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
