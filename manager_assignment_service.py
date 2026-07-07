"""
Manager Assignment Service
==========================

Centralised, transactional enforcement of the Kindergarten Management
business rules (FRD §4):

    C1  A MANAGER is bound to exactly one kindergarten at a time.
    C2  A kindergarten has at most one ACTIVE manager.
    C3  Assigning a user as MANAGER of a kindergarten automatically and
        atomically:
          - detaches them from any previous kindergarten,
          - strips every SUPERVISOR artifact they hold,
          - (optionally) vacates the target kindergarten's outgoing manager,
        then binds them to the target kindergarten as an ACTIVE manager.
    C4  A user holds at most one supervisor role (SupervisorProfile).
    C5  MANAGER and SUPERVISOR are mutually exclusive for a single user.

All functions operate on the caller's `Session` and DO NOT commit — the
calling endpoint owns the transaction boundary so the whole assignment
(KG + user + audit) commits or rolls back as one unit.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models
import validators

_JORDAN_TZ = timezone(timedelta(hours=3))


class ManagerAssignmentError(HTTPException):
    """Raised when a manager assignment violates a business rule.

    Subclasses HTTPException so FastAPI serialises it directly; the
    ``code`` is embedded in the detail payload for the frontend.
    """

    def __init__(self, status_code: int, message: str, code: str = "manager_assignment_error"):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def _audit(db: Session, actor_id: Optional[int], action: str, entity_type: str,
           entity_id: Optional[int], details: str) -> None:
    """Best-effort audit row using the shared generic helper (no commit)."""
    from audit_actions import AuditAction  # local import avoids cycles

    resolved = getattr(AuditAction, action, action)
    validators.log_audit_action(
        db=db,
        user_id=actor_id,
        action=resolved,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        sensitivity_level=3,
    )


# ---------------------------------------------------------------------------
# Supervisor-role stripping (C4 / C5)
# ---------------------------------------------------------------------------

def guard_supervisor_coverage(db: Session, user: models.User) -> None:
    """Block the cascade if removing this user as a supervisor would leave
    their kindergarten with zero active supervisors (FRD C3.5).

    Only relevant when the user is currently an ACTIVE SUPERVISOR.
    """
    if user.role != models.UserRole.SUPERVISOR:
        return
    if not user.kindergarten_id:
        return
    if user.status != models.UserStatus.ACTIVE:
        return
    try:
        validators.validate_kg_has_supervisor(
            db, user.kindergarten_id, exclude_user_id=user.id
        )
    except validators.ValidationError as exc:
        raise ManagerAssignmentError(
            status_code=422,
            message=(
                "لا يمكن ترقية هذا المشرف إلى مدير لأن حضانته ستبقى بلا مشرف نشط. "
                "يرجى تعيين مشرف بديل أولاً. / "
                "Cannot promote this supervisor to manager because their kindergarten "
                "would be left without an active supervisor. Assign a replacement first."
            ),
            code="supervisor_coverage_violation",
        ) from exc


def strip_supervisor_role(db: Session, user: models.User, *, actor_id: Optional[int]) -> dict:
    """Remove every SUPERVISOR artifact from *user* (FRD C3.2 / C4 / C5).

    - deletes the user's SupervisorProfile (the "one supervisor role"),
    - soft-deletes all active SupervisorAssignment rows (class-level).

    Returns a summary dict. Does not commit.
    """
    now = datetime.now(_JORDAN_TZ)

    assignments_removed = (
        db.query(models.SupervisorAssignment)
        .filter(
            models.SupervisorAssignment.supervisor_id == user.id,
            models.SupervisorAssignment.deleted_at.is_(None),
        )
        .update(
            {"deleted_at": now, "end_date": now.date(), "deleted_by": actor_id},
            synchronize_session=False,
        )
    )

    # The legacy Class.supervisor_id pointer is no longer maintained (D1/B5);
    # soft-deleting the SupervisorAssignment rows above is the whole job now.
    classes_cleared = 0

    profile_removed = (
        db.query(models.SupervisorProfile)
        .filter(models.SupervisorProfile.user_id == user.id)
        .delete(synchronize_session=False)
    )

    if assignments_removed or classes_cleared or profile_removed:
        _audit(
            db, actor_id, "SUPERVISOR_ROLE_REMOVED", "user", user.id,
            f"Stripped supervisor role from user {user.id} "
            f"(assignments={assignments_removed}, classes_cleared={classes_cleared}, "
            f"profile_removed={profile_removed})",
        )

    return {
        "assignments_removed": assignments_removed,
        "classes_cleared": classes_cleared,
        "profile_removed": bool(profile_removed),
    }


# ---------------------------------------------------------------------------
# Manager assignment cascade (C1 / C2 / C3)
# ---------------------------------------------------------------------------

def assign_user_as_manager(
    db: Session,
    user: models.User,
    target_kindergarten_id: int,
    *,
    actor_id: Optional[int],
    allow_replace: bool = False,
) -> dict:
    """Atomically make *user* the ACTIVE manager of *target_kindergarten_id*.

    Enforces C1–C5. Does not commit.

    Args:
        allow_replace: when True and the target KG already has a *different*
            active manager, that manager is vacated (status → INACTIVE) so the
            new manager can take over ("Replace manager" flow, FRD §3.3).
            When False, an occupied target KG raises 409.
    """
    # Target kindergarten must exist.
    target_kg = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id == target_kindergarten_id)
        .first()
    )
    if target_kg is None:
        raise ManagerAssignmentError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Target kindergarten not found.",
            code="kindergarten_not_found",
        )

    previous_kg_id = user.kindergarten_id
    was_manager = user.role == models.UserRole.MANAGER
    was_supervisor = user.role == models.UserRole.SUPERVISOR

    # No-op: user is already the active manager of this exact KG.
    if was_manager and previous_kg_id == target_kindergarten_id \
            and user.status == models.UserStatus.ACTIVE:
        return {"changed": False, "reason": "already_active_manager"}

    # C3.5 — do not strand a KG without a supervisor.
    guard_supervisor_coverage(db, user)

    # C2 — resolve an existing active manager on the target KG.
    existing_manager = (
        db.query(models.User)
        .filter(
            models.User.kindergarten_id == target_kindergarten_id,
            models.User.role == models.UserRole.MANAGER,
            models.User.status == models.UserStatus.ACTIVE,
            models.User.id != user.id,
        )
        .first()
    )
    replaced_manager_id = None
    if existing_manager is not None:
        if not allow_replace:
            raise ManagerAssignmentError(
                status_code=status.HTTP_409_CONFLICT,
                message=(
                    f"الحضانة رقم {target_kindergarten_id} لديها مدير نشط بالفعل "
                    f"(معرّف {existing_manager.id}). / "
                    f"Kindergarten {target_kindergarten_id} already has an active manager "
                    f"(ID {existing_manager.id}). Use replace to take over."
                ),
                code="kindergarten_has_active_manager",
            )
        # Vacate the outgoing manager (reversible deactivation).
        existing_manager.status = models.UserStatus.INACTIVE
        replaced_manager_id = existing_manager.id
        _audit(
            db, actor_id, "MANAGER_DETACHED", "user", existing_manager.id,
            f"Manager {existing_manager.id} vacated from kindergarten "
            f"{target_kindergarten_id} to allow replacement by user {user.id}",
        )

    # C3.1 — detach from previous kindergarten (log the transition).
    if was_manager and previous_kg_id and previous_kg_id != target_kindergarten_id:
        _audit(
            db, actor_id, "MANAGER_DETACHED", "user", user.id,
            f"User {user.id} detached from previous kindergarten {previous_kg_id} "
            f"before reassignment to {target_kindergarten_id}",
        )

    # C3.2 / C4 / C5 — strip any supervisor artifacts the user holds.
    strip_summary = strip_supervisor_role(db, user, actor_id=actor_id)

    # Bind the user to the target KG as an active manager.
    user.role = models.UserRole.MANAGER
    user.kindergarten_id = target_kindergarten_id
    user.status = models.UserStatus.ACTIVE

    action = "MANAGER_REASSIGNED" if (was_manager or was_supervisor) else "MANAGER_ASSIGNED"
    _audit(
        db, actor_id, action, "user", user.id,
        f"User {user.id} assigned as manager of kindergarten {target_kindergarten_id} "
        f"(previous_kg={previous_kg_id}, was_manager={was_manager}, "
        f"was_supervisor={was_supervisor}, replaced_manager={replaced_manager_id})",
    )

    return {
        "changed": True,
        "user_id": user.id,
        "target_kindergarten_id": target_kindergarten_id,
        "previous_kindergarten_id": previous_kg_id,
        "replaced_manager_id": replaced_manager_id,
        "supervisor_artifacts_removed": strip_summary,
    }


__all__ = [
    "ManagerAssignmentError",
    "assign_user_as_manager",
    "strip_supervisor_role",
    "guard_supervisor_coverage",
]
