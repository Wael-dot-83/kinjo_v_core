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

from audit_actions import AuditAction
from database import get_db
from models import AuditLog, Kindergarten, User, UserRole, UserStatus
from rate_limiter import limiter
from config import settings
from auth import create_access_token
from cache_service import cache_service
from dependencies import get_current_user
from rbac import IMPERSONATION_COOKIE_NAME, require_role

router = APIRouter()

_require_admin = require_role(UserRole.ADMIN)


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
) -> None:
    entry = AuditLog(
        user_id=admin_id,          # actor who performed the action
        action=action,
        entity_type="User",
        entity_id=target_id,       # subject being impersonated
        details=json.dumps({"reason": reason}),
        ip_address=ip,
        sensitivity_level=4,
        impersonated_by=admin_id,
        impersonation_reason=reason,
    )
    db.add(entry)
    db.commit()


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
    target = db.query(User).filter(
        User.id == payload.target_user_id,
        User.deleted_at.is_(None),
        User.status == UserStatus.ACTIVE,
    ).first()
    if not target:
        _write_audit(
            db,
            admin_id=current_admin.id,
            target_id=payload.target_user_id,
            action=AuditAction.IMPERSONATION_ATTEMPT_FAILED,
            reason=f"User not found: {payload.target_user_id}",
            ip=_get_ip(request),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target.role != UserRole.MANAGER:
        _write_audit(
            db,
            admin_id=current_admin.id,
            target_id=target.id,
            action=AuditAction.IMPERSONATION_ATTEMPT_FAILED,
            reason=f"Target role is {target.role.value}, not MANAGER",
            ip=_get_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only managers can be impersonated.",
        )

    started_at = datetime.now(_JORDAN_TZ).isoformat()
    lifetime = min(settings.ACCESS_TOKEN_EXPIRE_MINUTES, 30)
    max_age = lifetime * 60
    target_token = create_access_token(
        {
            "sub": target.username,
            "role": target.role.value,
            "impersonated_by": current_admin.id,
            "impersonation_reason": payload.reason,
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
            "jti": secrets.token_urlsafe(24),
        },
        expires_delta=timedelta(minutes=lifetime),
    )

    _write_audit(
        db,
        admin_id=current_admin.id,
        target_id=target.id,
        action=AuditAction.IMPERSONATION_START,
        reason=payload.reason,
        ip=_get_ip(request),
    )

    kg_name = ""
    if target.kindergarten_id:
        kg = db.query(Kindergarten).filter(Kindergarten.id == target.kindergarten_id).first()
        kg_name = kg.name_ar if kg else ""

    response = JSONResponse({
        "message": "Impersonation started.",
        "impersonating": {
            "user_id": target.id,
            "username": target.username,
            "name": target.full_name or target.username,
            "role": target.role.value,
            "kindergarten_name": kg_name,
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
