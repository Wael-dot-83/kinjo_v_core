"""
Admin impersonation endpoints.

POST /api/admin/impersonate         — start impersonating a manager
POST /api/admin/exit-impersonation  — end impersonation and return to admin identity
GET  /api/admin/managers            — list managers (for the picker UI)
GET  /api/admin/impersonate/audit   — recent impersonation audit log entries
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

_JORDAN_TZ = timezone(timedelta(hours=3))

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from audit_actions import AuditAction
from database import get_db
from models import AuditLog, Kindergarten, User, UserRole
from rate_limiter import limiter
from config import settings
from rbac import IMPERSONATION_SESSION_KEY, require_role

router = APIRouter()

_require_admin = require_role(UserRole.ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ImpersonateRequest(BaseModel):
    target_user_id: int
    reason: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> Optional[str]:
    client = request.client
    return client.host if client else None


def _get_session(request: Request) -> dict:
    """Return a mutable session dict from request.state, or a plain dict fallback."""
    session = getattr(request.state, "session", None)
    if session is None:
        # Provide a simple dict-backed fallback so the endpoint doesn't crash
        # when no session middleware is configured.
        request.state.session = {}
        return request.state.session
    return session


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

@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
@router.post("/impersonate", status_code=status.HTTP_200_OK)
def start_impersonation(
    payload: ImpersonateRequest,
    request: Request,
    current_admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(
        User.id == payload.target_user_id,
        User.deleted_at.is_(None),
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

    session = _get_session(request)
    session[IMPERSONATION_SESSION_KEY] = {
        "admin_id": current_admin.id,
        "admin_username": current_admin.username,
        "user_id": target.id,
        "username": target.full_name or target.username,
        "role": target.role.value,
        "started_at": datetime.now(_JORDAN_TZ).isoformat(),
    }

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

    return {
        "message": "Impersonation started.",
        "impersonating": {
            "user_id": target.id,
            "username": target.username,
            "name": target.full_name or target.username,
            "role": target.role.value,
            "kindergarten_name": kg_name,
        },
    }


# ---------------------------------------------------------------------------
# Exit impersonation
# ---------------------------------------------------------------------------

@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
@router.post("/exit-impersonation", status_code=status.HTTP_200_OK)
def exit_impersonation(
    request: Request,
    current_admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    session = _get_session(request)
    imp_data = session.get(IMPERSONATION_SESSION_KEY)

    if not imp_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not currently impersonating.")

    target_id = imp_data.get("user_id")

    _write_audit(
        db,
        admin_id=current_admin.id,   # always use JWT-verified identity
        target_id=target_id or current_admin.id,
        action=AuditAction.IMPERSONATION_END,
        reason=None,
        ip=_get_ip(request),
    )

    session.pop(IMPERSONATION_SESSION_KEY, None)

    return {"message": "Impersonation ended."}


# ---------------------------------------------------------------------------
# Audit log (last N impersonation events)
# ---------------------------------------------------------------------------

@router.get("/impersonate/audit")
def impersonation_audit(
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
