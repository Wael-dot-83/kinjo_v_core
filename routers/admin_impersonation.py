"""
Admin impersonation endpoints.

POST /api/admin/impersonate         — start impersonating a manager
POST /api/admin/exit-impersonation  — end impersonation and return to admin identity
GET  /api/admin/managers            — list managers (for the picker UI)
GET  /api/admin/impersonate/audit   — recent impersonation audit log entries
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import AuditLog, Kindergarten, User, UserRole
from rbac import IMPERSONATION_SESSION_KEY, require_role

router = APIRouter()

_require_admin = require_role(UserRole.ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ImpersonateRequest(BaseModel):
    target_user_id: int
    reason: Optional[str] = None


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
        user_id=target_id,
        action=action,
        entity_type="User",
        entity_id=target_id,
        details=json.dumps({"reason": reason}),
        ip_address=ip,
        sensitivity_level=4,
        impersonated_by=admin_id,
        impersonation_reason=reason,
    )
    db.add(entry)
    db.commit()


# ---------------------------------------------------------------------------
# List managers (for the picker UI on /admin/impersonate page)
# ---------------------------------------------------------------------------

@router.get("/admin/managers")
def list_managers(
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    managers = (
        db.query(User)
        .filter(User.role == UserRole.MANAGER, User.deleted_at.is_(None))
        .order_by(User.full_name)
        .all()
    )
    kg_map: dict[int, str] = {}
    kg_ids = [m.kindergarten_id for m in managers if m.kindergarten_id]
    if kg_ids:
        rows = db.query(Kindergarten.id, Kindergarten.name_ar).filter(Kindergarten.id.in_(kg_ids)).all()
        kg_map = {r.id: r.name_ar for r in rows}

    return {
        "managers": [
            {
                "id": m.id,
                "username": m.username,
                "name": m.full_name or m.username,
                "email": m.email,
                "kindergarten_id": m.kindergarten_id,
                "kindergarten_name": kg_map.get(m.kindergarten_id, "") if m.kindergarten_id else "",
            }
            for m in managers
        ]
    }


# ---------------------------------------------------------------------------
# Start impersonation
# ---------------------------------------------------------------------------

@router.post("/admin/impersonate", status_code=status.HTTP_200_OK)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target.role != UserRole.MANAGER:
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
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_audit(
        db,
        admin_id=current_admin.id,
        target_id=target.id,
        action="IMPERSONATION_START",
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

@router.post("/admin/exit-impersonation", status_code=status.HTTP_200_OK)
def exit_impersonation(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_session(request)
    imp_data = session.get(IMPERSONATION_SESSION_KEY)

    if not imp_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not currently impersonating.")

    admin_id = imp_data.get("admin_id", current_user.id)
    target_id = imp_data.get("user_id")

    _write_audit(
        db,
        admin_id=admin_id,
        target_id=target_id or current_user.id,
        action="IMPERSONATION_END",
        reason=None,
        ip=_get_ip(request),
    )

    session.pop(IMPERSONATION_SESSION_KEY, None)

    return {"message": "Impersonation ended."}


# ---------------------------------------------------------------------------
# Audit log (last N impersonation events)
# ---------------------------------------------------------------------------

@router.get("/admin/impersonate/audit")
def impersonation_audit(
    limit: int = 20,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["IMPERSONATION_START", "IMPERSONATION_END"]))
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 100))
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
