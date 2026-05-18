"""
Role-based access control helpers shared across API and frontend routes.

Guards:
  require_role(*roles)          — raises 403 if current user's role is not in roles
  block_role(*roles)            — raises 403 if current user's role IS in roles
  get_supervisor_class_ids      — returns the set of class IDs the supervisor is assigned to
  require_supervisor_class      — raises 403 if a child/class is outside supervisor's scope
  get_impersonation_context     — reads impersonation state from request session
"""

from __future__ import annotations

from typing import Optional, Set

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import SupervisorAssignment, User, UserRole, EnrollmentApplication, EnrollmentStatus


# ---------------------------------------------------------------------------
# Role guards
# ---------------------------------------------------------------------------

def require_role(*roles: UserRole):
    """FastAPI dependency — raises 403 if user is not one of *roles*."""
    async def _dep(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        return current_user
    return _dep


def block_role(*roles: UserRole):
    """FastAPI dependency — raises 403 if user IS one of *roles*."""
    async def _dep(current_user: User = Depends(get_current_user)):
        if current_user.role in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        return current_user
    return _dep


# ---------------------------------------------------------------------------
# Supervisor class-scoping
# ---------------------------------------------------------------------------

def get_supervisor_class_ids(supervisor_id: int, db: Session) -> Set[int]:
    """Return the set of active class IDs the supervisor is assigned to."""
    rows = (
        db.query(SupervisorAssignment.class_id)
        .filter(
            SupervisorAssignment.supervisor_id == supervisor_id,
            SupervisorAssignment.deleted_at.is_(None),
        )
        .all()
    )
    return {r.class_id for r in rows}


def get_supervisor_child_ids(supervisor_id: int, db: Session) -> Set[int]:
    """Return the set of child IDs in the supervisor's assigned classes (active enrollments)."""
    class_ids = get_supervisor_class_ids(supervisor_id, db)
    if not class_ids:
        return set()
    rows = (
        db.query(EnrollmentApplication.child_id)
        .filter(
            EnrollmentApplication.class_id.in_(class_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .all()
    )
    return {r.child_id for r in rows}


def assert_supervisor_owns_child(supervisor_id: int, child_id: int, db: Session) -> None:
    """Raise 403 if child_id is not in the supervisor's assigned classes."""
    allowed = get_supervisor_child_ids(supervisor_id, db)
    if child_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Child is not in your assigned class.",
        )


def assert_supervisor_owns_class(supervisor_id: int, class_id: int, db: Session) -> None:
    """Raise 403 if class_id is not assigned to this supervisor."""
    allowed = get_supervisor_class_ids(supervisor_id, db)
    if class_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Class is not in your assignment.",
        )


# ---------------------------------------------------------------------------
# Manager kindergarten-scoping
# ---------------------------------------------------------------------------

def assert_manager_owns_kindergarten(manager: User, kindergarten_id: int) -> None:
    """Raise 403 if the manager is not assigned to this kindergarten."""
    if manager.kindergarten_id != kindergarten_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kindergarten is outside your management scope.",
        )


# ---------------------------------------------------------------------------
# Impersonation helpers
# ---------------------------------------------------------------------------

IMPERSONATION_SESSION_KEY = "impersonation"


def get_impersonation_context(request: Request) -> Optional[dict]:
    """Return impersonation dict from session, or None if not impersonating."""
    session = getattr(request.state, "session", None)
    if session is None:
        return None
    return session.get(IMPERSONATION_SESSION_KEY)


def is_impersonating(request: Request) -> bool:
    return get_impersonation_context(request) is not None
