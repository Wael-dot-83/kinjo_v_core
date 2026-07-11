"""
Manager-scoped API endpoints.

All routes enforce MANAGER role and that every resource belongs to
the manager's own kindergarten(s).
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import get_db
from dependencies import get_current_user, require_manager as _require_manager
from models import (
    AuditLog,
    Class,
    Child,
    DailyReport,
    DailyReportStatus,
    EnrollmentApplication,
    EnrollmentStatus,
    Message,
    MessageRecipient,
    MessageThreadType,
    SupervisorAssignment,
    User,
    UserRole,
)
from rbac import assert_manager_owns_kindergarten
from audit_actions import AuditAction
import validators

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _get_class_or_403(class_id: int, manager: User, db: Session) -> Class:
    cls = db.query(Class).filter(Class.id == class_id, Class.deleted_at.is_(None)).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")
    assert_manager_owns_kindergarten(manager, cls.kindergarten_id)
    return cls


def _get_report_or_404(report_id: int, manager: User, db: Session) -> DailyReport:
    """Fetch a DailyReport and verify it belongs to the manager's kindergarten.

    Returns 404 (not 403) when the report is absent or belongs to another
    kindergarten, so cross-tenant existence is never leaked.
    """
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    enrollment = (
        db.query(EnrollmentApplication)
        .join(Class, EnrollmentApplication.class_id == Class.id)
        .filter(
            EnrollmentApplication.child_id == report.child_id,
            Class.kindergarten_id == manager.kindergarten_id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Report not found.")
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
        active_sups = [
            a for a in c.supervisor_assignments if a.deleted_at is None
        ]
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


@router.post("/classes/assign-supervisor", status_code=201)
def assign_supervisor_to_class(
    body: SupervisorAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    cls = _get_class_or_403(body.class_id, current_user, db)

    # Supervisor must be in same kindergarten
    sup = db.query(User).filter(User.id == body.supervisor_id, User.deleted_at.is_(None)).first()
    if not sup or sup.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=404, detail="Supervisor not found.")
    if sup.kindergarten_id != current_user.kindergarten_id:
        raise HTTPException(status_code=403, detail="Supervisor is not in your kindergarten.")

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
    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.SUPERVISOR_ASSIGNED,
        entity_type="class",
        entity_id=body.class_id,
        details=f"Manager assigned supervisor {body.supervisor_id} to class {body.class_id} (primary={body.is_primary})",
    ))
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
        raise HTTPException(status_code=404, detail="Assignment not found.")
    now = datetime.now(_JORDAN_TZ)
    assignment.deleted_at = now
    assignment.end_date = now.date()
    # Soft-deleting the assignment above is sufficient; the retired legacy
    # Class.supervisor_id column is no longer maintained (D1/B5).

    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.SUPERVISOR_UNASSIGNED,
        entity_type="class",
        entity_id=class_id,
        details=f"Manager removed supervisor {supervisor_id} from class {class_id}",
    ))
    db.commit()


@router.put("/classes/{class_id}/swap-supervisor")
def swap_supervisor(
    class_id: int,
    body: SupervisorSwapIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    """Remove all current supervisors from a class and assign a new primary one."""
    _get_class_or_403(class_id, current_user, db)
    now = datetime.now(_JORDAN_TZ)
    # Soft-delete existing assignments
    db.query(SupervisorAssignment).filter(
        SupervisorAssignment.class_id == class_id,
        SupervisorAssignment.deleted_at.is_(None),
    ).update({"deleted_at": now, "end_date": now.date()})

    new_sup = db.query(User).filter(User.id == body.supervisor_id, User.deleted_at.is_(None)).first()
    if not new_sup or new_sup.role != UserRole.SUPERVISOR or new_sup.kindergarten_id != current_user.kindergarten_id:
        raise HTTPException(status_code=403, detail="Invalid supervisor for this kindergarten.")

    a = SupervisorAssignment(class_id=class_id, supervisor_id=body.supervisor_id, is_primary=True, start_date=_today())
    db.add(a)
    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.REPLACEMENT_SUPERVISOR_ASSIGNED,
        entity_type="class",
        entity_id=class_id,
        details=f"Manager swapped class {class_id} supervisors to new primary {body.supervisor_id}",
    ))
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
    to_cls = _get_class_or_403(body.to_class_id, current_user, db)

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
        raise HTTPException(status_code=404, detail="Active enrollment for child in source class not found.")

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
            detail=f"Target class is full ({occupied}/{to_cls.capacity_total}).",
        )

    enrollment.class_id = body.to_class_id
    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.CHILD_MOVED_CLASS,
        entity_type="enrollment",
        entity_id=enrollment.id,
        details=f"Manager moved child {body.child_id} from class {body.from_class_id} to class {body.to_class_id}",
    ))
    db.commit()
    return {"child_id": body.child_id, "new_class_id": body.to_class_id}


# ---------------------------------------------------------------------------
# Daily reports review — manager sees SUBMITTED, can send to parents
# ---------------------------------------------------------------------------


@router.get("/daily-reports")
def list_daily_reports_for_review(
    class_id: Optional[int] = Query(None),
    supervisor_id: Optional[int] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    report_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    # Get child IDs in manager's kindergarten
    kg_id = current_user.kindergarten_id
    classes = db.query(Class).filter(Class.kindergarten_id == kg_id, Class.deleted_at.is_(None)).all()
    class_ids = {c.id for c in classes}

    if class_id:
        if class_id not in class_ids:
            raise HTTPException(status_code=404, detail="Class not found.")
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

    q = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids))

    if report_status:
        try:
            q = q.filter(DailyReport.status == DailyReportStatus[report_status.upper()])
        except KeyError:
            pass
    else:
        # Default: show SUBMITTED only
        q = q.filter(DailyReport.status == DailyReportStatus.SUBMITTED)

    if from_date:
        try:
            q = q.filter(DailyReport.date >= date.fromisoformat(from_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD.")
    if to_date:
        try:
            q = q.filter(DailyReport.date <= date.fromisoformat(to_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD.")

    if supervisor_id:
        q = q.filter(DailyReport.submitted_by == supervisor_id)

    reports = q.order_by(DailyReport.date.desc()).limit(200).all()
    child_map = {c.id: c for c in db.query(Child).filter(Child.id.in_(child_ids)).all()}

    submitter_ids = {r.submitted_by for r in reports if r.submitted_by is not None}
    supervisor_name_by_id = {}
    if submitter_ids:
        for u in db.query(User).filter(User.id.in_(submitter_ids)).all():
            supervisor_name_by_id[u.id] = u.full_name or u.username

    return [
        {
            "id": r.id,
            "child_id": r.child_id,
            "child_name": f"{child_map[r.child_id].first_name} {child_map[r.child_id].last_name}" if r.child_id in child_map else "",
            "date": str(r.date),
            "status": r.status.value,
            "submitted_by": r.submitted_by,
            "supervisor_name": supervisor_name_by_id.get(r.submitted_by, ""),
            "class_name": class_name_by_id.get(child_class_map.get(r.child_id), ""),
            "notes": r.notes,
        }
        for r in reports
    ]


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
    report = _get_report_or_404(report_id, current_user, db)

    if report.status == DailyReportStatus.SENT_TO_PARENT:
        raise HTTPException(status_code=403, detail="Cannot edit a report that has already been sent to parents.")

    for field in ("notes", "activities", "arrival_time", "leave_time",
                  "breakfast", "snack", "milk", "lunch"):
        val = getattr(body, field)
        if val is not None:
            setattr(report, field, val)

    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.DAILY_REPORT_EDITED,
        entity_type="daily_report",
        entity_id=report.id,
        details=f"Manager edited daily report for child {report.child_id}",
    ))
    db.commit()
    return {"id": report.id, "status": report.status.value}


@router.put("/daily-reports/{report_id}/send-to-parents")
def send_report_to_parents(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    report = _get_report_or_404(report_id, current_user, db)
    child = db.query(Child).filter(Child.id == report.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Report not found.")

    if report.status not in (DailyReportStatus.SUBMITTED, DailyReportStatus.APPROVED):
        raise HTTPException(status_code=400, detail="Report must be in SUBMITTED state to send to parents.")

    report.status = DailyReportStatus.SENT_TO_PARENT
    report.approved_by = current_user.id
    report.approved_at = datetime.now(_JORDAN_TZ)
    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.DAILY_REPORT_SENT_TO_PARENT,
        entity_type="daily_report",
        entity_id=report.id,
        details=f"Manager sent daily report for child {report.child_id} to parent",
    ))
    db.commit()

    # Create notification message for parent
    parent_user_id = child.parent.user_id if child.parent else None
    if parent_user_id:
        notification = Message(
            thread_type=MessageThreadType.DIRECT,
            sender_id=current_user.id,
            recipient_id=parent_user_id,
            kindergarten_id=current_user.kindergarten_id,
            subject=f"تقرير يومي جديد — {child.first_name} — {report.date}",
            message_body=f"تم إرسال تقرير يومي جديد لطفلك {child.first_name} بتاريخ {report.date}.",
        )
        db.add(notification)
        db.flush()  # assign notification.id before the audit row references it
        db.add(AuditLog(
            user_id=current_user.id,
            action=AuditAction.MESSAGE_SENT,
            entity_type="message",
            entity_id=notification.id,
            details=f"Manager sent daily-report notification to parent {parent_user_id} for child {report.child_id}",
        ))
        db.commit()

    return {"id": report.id, "status": report.status.value}


@router.delete("/daily-reports/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_manager),
):
    report = _get_report_or_404(report_id, current_user, db)

    if report.status == DailyReportStatus.SENT_TO_PARENT:
        raise HTTPException(status_code=409, detail="Cannot delete a report that has been sent to parents.")

    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.DAILY_REPORT_DELETED,
        entity_type="daily_report",
        entity_id=report.id,
        details=f"Manager deleted daily report for child {report.child_id} dated {report.date}",
    ))
    db.delete(report)
    db.commit()


# ---------------------------------------------------------------------------
# Manager KPI
# ---------------------------------------------------------------------------


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
        assignments = [
            a for a in sup.supervisor_assignments if a.deleted_at is None
        ]
        classes = [
            {"id": a.class_.id, "name_ar": a.class_.name_ar, "is_primary": a.is_primary}
            for a in assignments if a.class_
        ]
        result.append({
            "id": sup.id,
            "username": sup.username,
            "full_name": sup.full_name or sup.username,
            "email": sup.email or "",
            "phone_number": sup.phone_number or "",
            "status": sup.status.value,
            "classes": classes,
            "last_login_at": sup.last_login_at.isoformat() if sup.last_login_at else None,
        })
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
            raise HTTPException(status_code=404, detail="Class not found.")
        filter_class_ids = {class_id}
    else:
        filter_class_ids = set(class_ids.keys())

    enrollments = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.class_id.in_(filter_class_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .all()
    ) if filter_class_ids else []

    child_ids = [e.child_id for e in enrollments]
    enrollment_map = {e.child_id: e for e in enrollments}

    children = db.query(Child).filter(Child.id.in_(child_ids)).all() if child_ids else []

    result = []
    for c in children:
        enrollment = enrollment_map.get(c.id)
        class_obj = class_ids.get(enrollment.class_id) if enrollment else None
        result.append({
            "id": c.id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "gender": c.gender.value if c.gender else None,
            "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
            "class_id": enrollment.class_id if enrollment else None,
            "class_name_ar": class_obj.name_ar if class_obj else "",
        })
    return {"children": result, "total": len(result)}


# NOTE: the manager dashboard endpoint lives in api/manager.py
# (GET /api/manager/dashboard) -- do not add a second one here.
