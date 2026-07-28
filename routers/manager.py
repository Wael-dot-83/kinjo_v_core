"""
Manager-scoped API endpoints.

All routes enforce MANAGER role and that every resource belongs to
the manager's own kindergarten(s).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# One clock for the whole module. This file previously carried its own
# `_JORDAN_TZ = timezone(timedelta(hours=3))` *and* imported today_amman, so two
# independent notions of "now" ran side by side in the same request. They agree
# today only because Jordan dropped DST in 2022; time_utils resolves the real
# Asia/Amman zone and falls back to UTC if the zoneinfo database is missing,
# at which point the fixed offset would have silently disagreed by three hours.
from utils.time_utils import now_amman as _now, today_amman as _today

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from dependencies import require_manager as _require_manager
import models
from models import (
    Class,
    Child,
    DailyReport,
    DailyReportStatus,
    EnrollmentApplication,
    EnrollmentStatus,
    Message,
    MessageThreadType,
    SupervisorAssignment,
    User,
    UserRole,
)
from rbac import assert_manager_owns_kindergarten
from admin_security import log_audit_event
from audit_actions import AuditAction
from i18n import gettext as _api
import validators

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _ulang(user) -> str:
    """The caller's preferred UI language, defaulting to Arabic.

    Same helper as api/children.py / api/enrollment.py / api/parent.py — the
    manager module was the odd one out, answering every error in English inside
    an Arabic-primary product while the templates render `err.detail` verbatim.
    """
    return getattr(user, "preferred_language", None) or "ar"



def _audit(
    db: Session,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    summary: str,
    *,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    sensitivity: int = 1,
):
    """Record a manager mutation in the audit trail.

    Every write in this module used to construct ``models.AuditLog(...)`` by hand,
    which can only populate user_id / action / entity_type / entity_id / details.
    The five forensic columns — ip_address, request_id, actor_role, old_data and
    new_data — have no model default, so every manager action landed in the audit
    table with them NULL, while the admin module (which calls log_audit_event)
    recorded all of them. For a childcare regulator that is the difference between
    being able and unable to answer "from where, by whom, and what changed".

    log_audit_event add()s and flush()es but deliberately does not commit, which
    matches the callers here: each owns its own db.commit().
    """
    return log_audit_event(
        db,
        action=action,
        actor=actor,
        target_type=entity_type,
        target_ids=entity_id,
        before_state=before,
        after_state=after,
        metadata={"summary": summary},
        sensitivity_level=sensitivity,
    )


def _get_class_or_403(
    class_id: int,
    manager: User,
    db: Session,
    *,
    require_active: bool = False,
) -> Class:
    query = db.query(Class).filter(Class.id == class_id, Class.deleted_at.is_(None))
    if require_active:
        query = query.filter(Class.is_active.is_(True))
    cls = query.first()
    if not cls:
        raise HTTPException(status_code=404, detail=_api("Class not found.", _ulang(manager)))
    assert_manager_owns_kindergarten(manager, cls.kindergarten_id)
    return cls


def _get_daily_report_for_manager_or_404(report_id: int, manager: User, db: Session) -> DailyReport:
    """Fetch a daily report enforcing the manager's kindergarten scope.

    Scope is anchored to the report's OWN ``kindergarten_id`` column (the
    authoritative context stored on the report), not to the child's current
    enrollment — a report belongs to the kindergarten it was filed in. A report
    in another kindergarten returns 404 (never 403) so we don't leak that it
    exists (#6/#14).
    """
    report = db.query(DailyReport).filter(DailyReport.id == report_id).with_for_update().first()
    if not report or report.kindergarten_id != manager.kindergarten_id:
        raise HTTPException(status_code=404, detail=_api("Report not found.", _ulang(manager)))
    return report


# ---------------------------------------------------------------------------
# Classes CRUD
# ---------------------------------------------------------------------------


@router.get("/classes")
def list_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    classes = (
        db.query(Class)
        .options(selectinload(Class.supervisor_assignments))
        .filter(Class.kindergarten_id == current_user.kindergarten_id, Class.deleted_at.is_(None))
        .order_by(Class.name_ar)
        .all()
    )
    result = []
    for c in classes:
        active_sups = [a for a in c.supervisor_assignments if a.deleted_at is None]
        result.append(
            {
                "id": c.id,
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "capacity_total": c.capacity_total,
                "min_age_months": c.min_age_months,
                "max_age_months": c.max_age_months,
                "is_active": c.is_active,
                "supervisor_count": len(active_sups),
            }
        )
    return {"classes": result}


# NOTE: class create/update/delete intentionally live in api/classes.py
# (validate_manager_role + validate_kindergarten_scope + log_audit_action).
# This router only adds the manager-specific workflows that the shared
# classes API does not cover.


# ---------------------------------------------------------------------------
# Supervisor assignment to class
# ---------------------------------------------------------------------------


class SupervisorAssignIn(BaseModel):
    supervisor_id: int
    class_id: int
    is_primary: bool = False


class SupervisorSwapIn(BaseModel):
    supervisor_id: int


def _available_supervisor_for_assignment(
    db: Session,
    supervisor_id: int,
    kindergarten_id: int,
    *,
    manager: User,
    exclude_class_id: Optional[int] = None,
) -> User:
    """Resolve an assignable supervisor, or raise in the *manager's* language.

    `manager` is here only so the two failures below can be localized; every
    other helper in this module already had the caller in scope.
    """
    supervisor = (
        db.query(User)
        .filter(
            User.id == supervisor_id,
            User.role == UserRole.SUPERVISOR,
            User.status == models.UserStatus.ACTIVE,
            User.kindergarten_id == kindergarten_id,
            User.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not supervisor:
        raise HTTPException(status_code=404, detail=_api("Supervisor not found.", _ulang(manager)))

    today = _today()
    overlap = db.query(SupervisorAssignment).filter(
        SupervisorAssignment.supervisor_id == supervisor_id,
        SupervisorAssignment.deleted_at.is_(None),
        or_(SupervisorAssignment.end_date.is_(None), SupervisorAssignment.end_date >= today),
    )
    if exclude_class_id is not None:
        overlap = overlap.filter(SupervisorAssignment.class_id != exclude_class_id)
    if overlap.first():
        raise HTTPException(status_code=409, detail=_api("Supervisor is already assigned to another class.", _ulang(manager)))
    return supervisor


@router.post("/classes/assign-supervisor", status_code=201)
def assign_supervisor_to_class(
    body: SupervisorAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    cls = _get_class_or_403(body.class_id, current_user, db, require_active=True)

    _available_supervisor_for_assignment(
        db,
        body.supervisor_id,
        current_user.kindergarten_id,
        manager=current_user,
        exclude_class_id=body.class_id,
    )

    existing = (
        db.query(SupervisorAssignment)
        .filter(
            SupervisorAssignment.supervisor_id == body.supervisor_id,
            SupervisorAssignment.class_id == body.class_id,
            SupervisorAssignment.deleted_at.is_(None),
        )
        .first()
    )
    if existing:
        return {"id": existing.id, "already_exists": True}

    # A class has at most one primary -- retire the current one first so
    # this insert doesn't create two simultaneously-active primaries.
    if body.is_primary:
        validators.retire_active_primary_assignment(db, body.class_id)

    assignment = SupervisorAssignment(
        class_id=body.class_id,
        supervisor_id=body.supervisor_id,
        is_primary=body.is_primary,
        start_date=_today(),
    )
    db.add(assignment)
    _audit(
        db,
        current_user,
        AuditAction.SUPERVISOR_ASSIGNED,
        "class",
        body.class_id,
        f"Manager assigned supervisor {body.supervisor_id} to class {body.class_id} (primary={body.is_primary})",
    )
    db.commit()
    db.refresh(assignment)

    # The primary supervisor is recorded solely by this SupervisorAssignment row
    # now; the legacy Class.supervisor_id column is no longer written (D1/B5).

    return {"id": assignment.id}


@router.delete("/classes/{class_id}/supervisors/{supervisor_id}", status_code=204)
def unassign_supervisor_from_class(
    class_id: int,
    supervisor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    # Authorization side effect only (raises 404/403 if the class is out of scope).
    _get_class_or_403(class_id, current_user, db)
    assignment = (
        db.query(SupervisorAssignment)
        .filter(
            SupervisorAssignment.class_id == class_id,
            SupervisorAssignment.supervisor_id == supervisor_id,
            SupervisorAssignment.deleted_at.is_(None),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail=_api("Assignment not found.", _ulang(current_user)))
    now = _now()
    assignment.deleted_at = now
    assignment.end_date = now.date()
    # Soft-deleting the assignment above is sufficient; the retired legacy
    # Class.supervisor_id column is no longer maintained (D1/B5).

    _audit(
        db,
        current_user,
        AuditAction.SUPERVISOR_UNASSIGNED,
        "class",
        class_id,
        f"Manager removed supervisor {supervisor_id} from class {class_id}",
    )
    db.commit()


@router.put("/classes/{class_id}/swap-supervisor")
def swap_supervisor(
    class_id: int,
    body: SupervisorSwapIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    """Remove all current supervisors from a class and assign a new primary one."""
    _get_class_or_403(class_id, current_user, db, require_active=True)
    now = _now()
    # Soft-delete existing assignments
    db.query(SupervisorAssignment).filter(
        SupervisorAssignment.class_id == class_id,
        SupervisorAssignment.deleted_at.is_(None),
    ).update({"deleted_at": now, "end_date": now.date()})

    _available_supervisor_for_assignment(
        db,
        body.supervisor_id,
        current_user.kindergarten_id,
        manager=current_user,
        exclude_class_id=class_id,
    )

    a = SupervisorAssignment(class_id=class_id, supervisor_id=body.supervisor_id, is_primary=True, start_date=_today())
    db.add(a)
    _audit(
        db,
        current_user,
        AuditAction.REPLACEMENT_SUPERVISOR_ASSIGNED,
        "class",
        class_id,
        f"Manager swapped class {class_id} supervisors to new primary {body.supervisor_id}",
    )
    db.commit()
    return {"class_id": class_id, "new_supervisor_id": body.supervisor_id}


# ---------------------------------------------------------------------------
# Move child between classes (same kindergarten)
# ---------------------------------------------------------------------------


class MoveChildIn(BaseModel):
    child_id: int
    from_class_id: int
    to_class_id: int


@router.post("/children/move-class")
def move_child_between_classes(
    body: MoveChildIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    from_cls = _get_class_or_403(body.from_class_id, current_user, db)
    _get_class_or_403(body.to_class_id, current_user, db, require_active=True)
    # Serialize capacity allocation on the destination class. PostgreSQL locks
    # this row until commit; SQLite safely ignores FOR UPDATE in local/test use.
    to_cls = db.query(Class).filter(Class.id == body.to_class_id, Class.deleted_at.is_(None)).with_for_update().one()

    enrollment = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id == body.child_id,
            EnrollmentApplication.class_id == body.from_class_id,
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail=_api("Active enrollment for child in source class not found.", _ulang(current_user)))

    # Respect the target class capacity.
    occupied = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.class_id == body.to_class_id,
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .count()
    )
    if to_cls.capacity_total is not None and occupied >= to_cls.capacity_total:
        raise HTTPException(
            status_code=409,
            detail=_api(f"Target class is full ({occupied}/{to_cls.capacity_total}).", _ulang(current_user)),
        )

    enrollment.class_id = body.to_class_id
    _audit(
        db,
        current_user,
        AuditAction.CHILD_MOVED_CLASS,
        "enrollment",
        enrollment.id,
        f"Manager moved child {body.child_id} from class {body.from_class_id} to class {body.to_class_id}",
    )
    db.commit()
    return {"child_id": body.child_id, "new_class_id": body.to_class_id}


# ---------------------------------------------------------------------------
# Daily reports review — manager sees SUBMITTED, can send to parents
# ---------------------------------------------------------------------------


@router.get("/daily-reports")
def list_daily_reports_for_review(
    class_id: Optional[int] = Query(None),
    supervisor_id: Optional[int] = Query(None),
    # Typed date params: FastAPI returns 422 for malformed dates instead of a 500 (#8).
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    report_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail=_api("from_date must be on or before to_date", _ulang(current_user)))
    # Get child IDs in manager's kindergarten
    kg_id = current_user.kindergarten_id
    classes = db.query(Class).filter(Class.kindergarten_id == kg_id, Class.deleted_at.is_(None)).all()
    class_ids = {c.id for c in classes}

    if class_id:
        # A class outside the manager's kindergarten is reported as not found (#14),
        # so we don't reveal that it exists in another tenant.
        if class_id not in class_ids:
            raise HTTPException(status_code=404, detail=_api("Class not found.", _ulang(current_user)))
        class_ids = {class_id}

    child_class_map = {
        e.child_id: e.class_id
        for e in db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.class_id.in_(class_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .all()
    }
    child_ids = set(child_class_map.keys())
    class_name_by_id = {c.id: c.name_ar for c in classes}

    # The report's own kindergarten_id is the authoritative tenant context.
    # Do not infer report ownership from the child's current enrollment: a
    # transfer must neither leak the previous KG's reports nor hide this KG's
    # historical reports.
    q = db.query(DailyReport).filter(DailyReport.kindergarten_id == kg_id)
    if class_id:
        q = q.filter(DailyReport.child_id.in_(child_ids))

    if report_status:
        # An unrecognized status is a client error, not silently ignored (#9).
        try:
            status_enum = DailyReportStatus[report_status.upper()]
        except KeyError:
            allowed = ", ".join(s.name for s in DailyReportStatus)
            raise HTTPException(
                status_code=400,
                detail=_api(f"Invalid report_status '{report_status}'. Allowed: {allowed}.", _ulang(current_user)),
            )
        q = q.filter(DailyReport.status == status_enum)
    else:
        # Default: show SUBMITTED only
        q = q.filter(DailyReport.status == DailyReportStatus.SUBMITTED)

    if from_date:
        q = q.filter(DailyReport.date >= from_date)
    if to_date:
        q = q.filter(DailyReport.date <= to_date)

    if supervisor_id:
        supervisor = (
            db.query(User.id)
            .filter(
                User.id == supervisor_id,
                User.role == UserRole.SUPERVISOR,
                User.kindergarten_id == kg_id,
                User.deleted_at.is_(None),
            )
            .first()
        )
        if not supervisor:
            raise HTTPException(status_code=404, detail=_api("Supervisor not found.", _ulang(current_user)))
        q = q.filter(DailyReport.submitted_by == supervisor_id)

    reports = q.order_by(DailyReport.date.desc()).limit(200).all()
    report_child_ids = {r.child_id for r in reports}
    child_map = {c.id: c for c in db.query(Child).filter(Child.id.in_(report_child_ids)).all()}

    submitter_ids = {r.submitted_by for r in reports if r.submitted_by is not None}
    supervisor_name_by_id = {}
    if submitter_ids:
        for u in db.query(User).filter(User.id.in_(submitter_ids)).all():
            supervisor_name_by_id[u.id] = u.full_name or u.username

    # Compute stats from the full KG context (not filtered) so the stat cards
    # remain accurate even when filters are active.
    stats_q = db.query(DailyReport).filter(DailyReport.kindergarten_id == kg_id)
    stats_total = stats_q.count()
    stats_pending = stats_q.filter(DailyReport.status == DailyReportStatus.SUBMITTED).count()
    stats_sent = stats_q.filter(DailyReport.status == DailyReportStatus.SENT_TO_PARENT).count()
    today_date = _today()
    week_ago_date = today_date - timedelta(days=6)
    stats_today = stats_q.filter(DailyReport.date == today_date).count()
    stats_week = stats_q.filter(DailyReport.date >= week_ago_date).count()

    return {
        "reports": [
            {
                "id": r.id,
                "child_id": r.child_id,
                "child_name": f"{child_map[r.child_id].first_name} {child_map[r.child_id].last_name}"
                if r.child_id in child_map
                else "",
                "date": str(r.date),
                "status": r.status.value,
                "submitted_by": r.submitted_by,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "supervisor_name": supervisor_name_by_id.get(r.submitted_by, ""),
                "class_name": class_name_by_id.get(child_class_map.get(r.child_id), ""),
                "notes": r.notes,
                "activities": r.activities,
                "arrival_time": r.arrival_time,
                "leave_time": r.leave_time,
                "breakfast": r.breakfast,
                "snack": r.snack,
                "milk": r.milk,
                "lunch": r.lunch,
            }
            for r in reports
        ],
        "stats": {
            "total": stats_total,
            "pending": stats_pending,
            "sent": stats_sent,
            "today": stats_today,
            "week": stats_week,
        },
    }


class DailyReportManagerPatch(BaseModel):
    notes: Optional[str] = None
    activities: Optional[str] = None
    arrival_time: Optional[str] = None
    leave_time: Optional[str] = None
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None


@router.put("/daily-reports/{report_id}")
def edit_daily_report(
    report_id: int,
    body: DailyReportManagerPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    """Manager can edit a submitted report's content before sending to parents."""
    report = _get_daily_report_for_manager_or_404(report_id, current_user, db)

    if report.status != DailyReportStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail=_api("Only submitted reports can be edited during manager review.", _ulang(current_user)),
        )

    for field in ("notes", "activities", "arrival_time", "leave_time", "breakfast", "snack", "milk", "lunch"):
        val = getattr(body, field)
        if val is not None:
            setattr(report, field, val)

    _audit(
        db,
        current_user,
        AuditAction.DAILY_REPORT_EDITED,
        "daily_report",
        report.id,
        f"Manager edited daily report for child {report.child_id}",
    )
    db.commit()
    return {"id": report.id, "status": report.status.value}


@router.put("/daily-reports/{report_id}/send-to-parents")
def send_report_to_parents(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    report = _get_daily_report_for_manager_or_404(report_id, current_user, db)
    child = db.query(Child).filter(Child.id == report.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail=_api("Report not found.", _ulang(current_user)))

    if report.status not in (DailyReportStatus.SUBMITTED, DailyReportStatus.APPROVED):
        # The message used to say "must be in SUBMITTED state" while the guard also
        # accepts APPROVED, so a manager sending an approved report saw a reason that
        # contradicted the code that let it through.
        raise HTTPException(
            status_code=400,
            detail=_api("Report must be SUBMITTED or APPROVED to send to parents.", _ulang(current_user)),
        )

    # Atomic: status change, approval fields, parent notification, and both audit
    # rows commit together (#7). If anything fails, roll the whole thing back so
    # we never leave a report marked SENT_TO_PARENT without its parent message.
    try:
        report.status = DailyReportStatus.SENT_TO_PARENT
        report.approved_by = current_user.id
        report.approved_at = _now()
        report.sent_to_parent_at = report.approved_at
        _audit(
            db,
            current_user,
            AuditAction.DAILY_REPORT_SENT_TO_PARENT,
            "daily_report",
            report.id,
            f"Manager sent daily report for child {report.child_id} to parent",
        )

        parent_user_id = child.parent.user_id if child.parent else None
        if parent_user_id:
            # Written in the PARENT's language, not the manager's and not
            # hardcoded Arabic. This message is delivered to the parent's inbox,
            # so the recipient's preference is the only one that matters here.
            parent_user = db.query(User).filter(User.id == parent_user_id).first()
            plang = _ulang(parent_user)
            notification = Message(
                thread_type=MessageThreadType.DIRECT,
                sender_id=current_user.id,
                recipient_id=parent_user_id,
                kindergarten_id=current_user.kindergarten_id,
                subject=_api(
                    "New daily report — {name} — {date}", plang,
                    name=child.first_name, date=report.date,
                ),
                message_body=_api(
                    "A new daily report for your child {name} was sent on {date}.",
                    plang, name=child.first_name, date=report.date,
                ),
            )
            db.add(notification)
            db.flush()  # assign notification.id before the audit row references it
            _audit(
                db,
                current_user,
                AuditAction.MESSAGE_SENT,
                "message",
                notification.id,
                f"Manager sent daily-report notification to parent {parent_user_id} for child {report.child_id}",
            )

        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_api("Failed to send report to parent; no changes were applied.", _ulang(current_user)),
        )

    return {"id": report.id, "status": report.status.value}


@router.delete("/daily-reports/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    report = _get_daily_report_for_manager_or_404(report_id, current_user, db)

    if report.status == DailyReportStatus.SENT_TO_PARENT:
        raise HTTPException(status_code=409, detail=_api("Cannot delete a report that has been sent to parents.", _ulang(current_user)))

    _audit(
        db,
        current_user,
        AuditAction.DAILY_REPORT_DELETED,
        "daily_report",
        report.id,
        f"Manager deleted daily report for child {report.child_id} dated {report.date}",
    )
    db.delete(report)
    db.commit()


# ---------------------------------------------------------------------------
# Manager KPI
# ---------------------------------------------------------------------------


class ManagerSupervisorCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    phone_number: Optional[str] = Field(default=None, max_length=20)


class ManagerSupervisorUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = None


def _manager_supervisor_or_404(db: Session, supervisor_id: int, manager: User) -> User:
    supervisor = (
        db.query(User)
        .filter(
            User.id == supervisor_id,
            User.role == UserRole.SUPERVISOR,
            User.kindergarten_id == manager.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .first()
    )
    if not supervisor:
        raise HTTPException(status_code=404, detail=_api("Supervisor not found.", _ulang(manager)))
    return supervisor


@router.post("/supervisors", status_code=201)
def create_supervisor(
    body: ManagerSupervisorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    from auth import get_password_hash

    try:
        validators.validate_password_policy(body.password)
    except validators.ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    duplicate = (
        db.query(User.id)
        .filter(
            or_(
                User.username == body.username.strip(),
                User.email == str(body.email) if body.email else False,
            )
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail=_api("Username or email already exists.", _ulang(current_user)))

    supervisor = User(
        username=body.username.strip(),
        email=str(body.email) if body.email else None,
        hashed_password=get_password_hash(body.password),
        role=UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=current_user.kindergarten_id,
        full_name=body.full_name.strip(),
        phone_number=body.phone_number.strip() if body.phone_number else None,
        must_change_password=True,
    )
    db.add(supervisor)
    try:
        db.flush()
        validators.ensure_supervisor_profile(db, supervisor, current_user.kindergarten_id)
        _audit(
            db,
            current_user,
            AuditAction.STAFF_CREATED,
            "user",
            supervisor.id,
            f"Manager created supervisor {supervisor.id}",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=_api("Username or email already exists.", _ulang(current_user)))
    db.refresh(supervisor)
    return {"id": supervisor.id, "username": supervisor.username, "status": supervisor.status.value}


@router.put("/supervisors/{supervisor_id}")
def update_supervisor(
    supervisor_id: int,
    body: ManagerSupervisorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    supervisor = _manager_supervisor_or_404(db, supervisor_id, current_user)
    if body.email is not None:
        email = str(body.email)
        duplicate = db.query(User.id).filter(User.email == email, User.id != supervisor.id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail=_api("Email already exists.", _ulang(current_user)))
        supervisor.email = email
    if body.full_name is not None:
        supervisor.full_name = body.full_name.strip()
    if body.phone_number is not None:
        supervisor.phone_number = body.phone_number.strip() or None
    if body.status is not None:
        try:
            new_status = models.UserStatus(body.status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=_api("Invalid supervisor status.", _ulang(current_user)))
        if new_status != models.UserStatus.ACTIVE and supervisor.status == models.UserStatus.ACTIVE:
            try:
                validators.validate_kg_has_supervisor(db, current_user.kindergarten_id, exclude_user_id=supervisor.id)
            except validators.ValidationError as exc:
                raise HTTPException(status_code=409, detail=exc.message)
            now = _now()
            db.query(SupervisorAssignment).filter(
                SupervisorAssignment.supervisor_id == supervisor.id,
                SupervisorAssignment.deleted_at.is_(None),
            ).update({"deleted_at": now, "end_date": now.date(), "deleted_by": current_user.id})
        supervisor.status = new_status
    _audit(
        db,
        current_user,
        AuditAction.USER_UPDATED,
        "user",
        supervisor.id,
        f"Manager updated supervisor {supervisor.id}",
    )
    db.commit()
    return {"id": supervisor.id, "status": supervisor.status.value}


@router.delete("/supervisors/{supervisor_id}", status_code=204)
def delete_supervisor(
    supervisor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    supervisor = _manager_supervisor_or_404(db, supervisor_id, current_user)
    if supervisor.status == models.UserStatus.ACTIVE:
        try:
            validators.validate_kg_has_supervisor(db, current_user.kindergarten_id, exclude_user_id=supervisor.id)
        except validators.ValidationError as exc:
            raise HTTPException(status_code=409, detail=exc.message)
    now = _now()
    db.query(SupervisorAssignment).filter(
        SupervisorAssignment.supervisor_id == supervisor.id,
        SupervisorAssignment.deleted_at.is_(None),
    ).update({"deleted_at": now, "end_date": now.date(), "deleted_by": current_user.id})
    supervisor.status = models.UserStatus.INACTIVE
    supervisor.deleted_at = now
    supervisor.deleted_by = current_user.id
    _audit(
        db,
        current_user,
        AuditAction.USER_DELETED,
        "user",
        supervisor.id,
        f"Manager removed supervisor {supervisor.id}",
    )
    db.commit()


@router.get("/supervisors")
def list_supervisors(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    supervisors = (
        db.query(User)
        .options(selectinload(User.supervisor_assignments).selectinload(SupervisorAssignment.class_))
        .filter(
            User.role == UserRole.SUPERVISOR,
            User.kindergarten_id == current_user.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .order_by(User.full_name, User.username)
        .all()
    )
    result = []
    for sup in supervisors:
        assignments = [a for a in sup.supervisor_assignments if a.deleted_at is None]
        classes = [
            {"id": a.class_.id, "name_ar": a.class_.name_ar, "is_primary": a.is_primary}
            for a in assignments
            if a.class_
        ]
        result.append(
            {
                "id": sup.id,
                "username": sup.username,
                "full_name": sup.full_name or sup.username,
                "email": sup.email or "",
                "phone_number": sup.phone_number or "",
                "status": sup.status.value,
                "classes": classes,
                "last_login_at": sup.last_login_at.isoformat() if sup.last_login_at else None,
            }
        )
    return {"supervisors": result}


@router.get("/children")
def list_children(
    class_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    kg_id = current_user.kindergarten_id
    classes = db.query(Class).filter(Class.kindergarten_id == kg_id, Class.deleted_at.is_(None)).all()
    class_ids = {c.id: c for c in classes}

    if class_id:
        if class_id not in class_ids:
            raise HTTPException(status_code=404, detail=_api("Class not found.", _ulang(current_user)))
        filter_class_ids = {class_id}
    else:
        filter_class_ids = set(class_ids.keys())

    enrollments = (
        (
            db.query(EnrollmentApplication)
            .filter(
                EnrollmentApplication.class_id.in_(filter_class_ids),
                EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
            )
            .all()
        )
        if filter_class_ids
        else []
    )

    child_ids = [e.child_id for e in enrollments]
    enrollment_map = {e.child_id: e for e in enrollments}

    children = db.query(Child).filter(Child.id.in_(child_ids)).all() if child_ids else []

    result = []
    for c in children:
        enrollment = enrollment_map.get(c.id)
        class_obj = class_ids.get(enrollment.class_id) if enrollment else None
        result.append(
            {
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "gender": c.gender.value if c.gender else None,
                "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
                "class_id": enrollment.class_id if enrollment else None,
                "class_name_ar": class_obj.name_ar if class_obj else "",
            }
        )
    return {"children": result, "total": len(result)}


# NOTE: the manager dashboard endpoint lives in api/manager.py
# (GET /api/manager/dashboard) -- do not add a second one here.
