"""
Supervisor-scoped API endpoints.

All routes enforce that the caller is SUPERVISOR and that every
child/class referenced belongs to the caller's assigned classes.

Redis caching (TTL=300s) is used for the KPI endpoint.
Cache keys include supervisor_id + date range to prevent cross-user leaks.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import (
    AttendanceLog,
    AuditLog,
    DailyReport,
    DailyReportStatus,
    Incident,
    IncidentType,
    SeverityLevel,
    Message,
    MessageRecipient,
    MessageThreadType,
    SupervisorAssignment,
    User,
    UserRole,
)
from rbac import (
    assert_supervisor_owns_child,
    assert_supervisor_owns_class,
    get_supervisor_child_ids,
    get_supervisor_class_ids,
)

router = APIRouter(prefix="/api/supervisor", tags=["supervisor"])

# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _require_supervisor(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor access only.")
    return current_user


# ---------------------------------------------------------------------------
# Classes & children
# ---------------------------------------------------------------------------


@router.get("/my-classes")
def get_my_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    from models import Class, SupervisorAssignment
    rows = (
        db.query(SupervisorAssignment)
        .filter(
            SupervisorAssignment.supervisor_id == current_user.id,
            SupervisorAssignment.deleted_at.is_(None),
        )
        .all()
    )
    result = []
    for r in rows:
        c = r.class_
        if c:
            result.append({"id": c.id, "name_ar": c.name_ar, "name_en": c.name_en, "is_primary": r.is_primary})
    return {"classes": result}


@router.get("/children")
def get_my_children(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    from models import Child, EnrollmentApplication, EnrollmentStatus
    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return {"children": []}
    children = db.query(Child).filter(Child.id.in_(child_ids)).all()
    return {
        "children": [
            {
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "gender": c.gender.value if c.gender else None,
            }
            for c in children
        ]
    }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------


@router.get("/attendance")
def get_attendance(
    date_str: str = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    target_date = date.fromisoformat(date_str) if date_str else date.today()
    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return {"date": str(target_date), "children": [], "present": 0, "absent": 0, "total": 0}

    from models import Child, Class, EnrollmentApplication, EnrollmentStatus
    children = {c.id: c for c in db.query(Child).filter(Child.id.in_(child_ids)).all()}

    # Build class_name map via active enrollment
    enrollments = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id.in_(child_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .all()
    )
    class_ids_for_children = {e.child_id: e.class_id for e in enrollments}
    classes = {c.id: c for c in db.query(Class).filter(Class.id.in_(class_ids_for_children.values())).all()}
    class_name_map = {
        child_id: (classes[cid].name_ar or classes[cid].name_en or "")
        for child_id, cid in class_ids_for_children.items()
        if cid in classes
    }

    logs = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.child_id.in_(child_ids), AttendanceLog.date == target_date)
        .all()
    )
    logged = {log.child_id: log for log in logs}

    result = []
    for cid, child in children.items():
        log = logged.get(cid)
        check_in_at = log.check_in_at if log else None
        check_out_at = log.check_out_at if log else None
        if check_in_at and check_out_at:
            att_status = "checked_out"
        elif check_in_at:
            att_status = "present"
        else:
            att_status = "not_arrived"
        result.append(
            {
                "id": cid,
                "name": f"{child.first_name} {child.last_name}",
                "class_name": class_name_map.get(cid, ""),
                "status": att_status,
                "check_in_time": check_in_at.strftime("%H:%M") if check_in_at else None,
                "check_out_time": check_out_at.strftime("%H:%M") if check_out_at else None,
            }
        )

    present = sum(1 for r in result if r["status"] == "present")
    checked_out = sum(1 for r in result if r["status"] == "checked_out")
    return {
        "date": str(target_date),
        "children": result,
        "present": present + checked_out,
        "absent": len(result) - present - checked_out,
        "total": len(result),
    }


class AttendanceIn(BaseModel):
    child_id: int
    action: str  # "check_in" | "check_out" | "mark_absent"
    date: Optional[str] = None


@router.post("/attendance")
def record_attendance(
    body: AttendanceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    assert_supervisor_owns_child(current_user.id, body.child_id, db)
    target_date = date.fromisoformat(body.date) if body.date else date.today()
    now = datetime.now(timezone.utc)

    log = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.child_id == body.child_id, AttendanceLog.date == target_date)
        .first()
    )

    # Find the child's actual enrolled class (within supervisor's scope)
    from models import EnrollmentApplication, EnrollmentStatus
    class_ids = get_supervisor_class_ids(current_user.id, db)
    enrollment = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id == body.child_id,
            EnrollmentApplication.class_id.in_(class_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .first()
    )
    class_id = enrollment.class_id if enrollment else None

    from models import AttendanceStatus
    if body.action == "check_in":
        if not log:
            log = AttendanceLog(
                child_id=body.child_id, class_id=class_id, date=target_date,
                status=AttendanceStatus.PRESENT,
                check_in_at=now,
                recorded_by=current_user.id,
            )
            db.add(log)
        else:
            log.check_in_at = now
    elif body.action == "check_out":
        if not log:
            raise HTTPException(status_code=400, detail="No check-in found.")
        log.check_out_at = now
    elif body.action == "mark_absent":
        if log:
            db.delete(log)
        db.commit()
        return {"status": "absent"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action.")

    db.commit()
    return {"status": "ok", "log_id": log.id}


# ---------------------------------------------------------------------------
# Daily Reports
# ---------------------------------------------------------------------------


@router.get("/daily-reports")
def get_daily_reports(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return {"reports": [], "stats": {"submitted": 0, "pending": 0, "draft": 0, "sent_to_parent": 0}}

    q = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids))
    if from_date:
        q = q.filter(DailyReport.date >= date.fromisoformat(from_date))
    if to_date:
        q = q.filter(DailyReport.date <= date.fromisoformat(to_date))
    if status_filter:
        try:
            q = q.filter(DailyReport.status == DailyReportStatus(status_filter.upper()))
        except ValueError:
            pass

    reports = q.order_by(DailyReport.date.desc()).all()
    from models import Child, Class, EnrollmentApplication, EnrollmentStatus
    child_map = {c.id: c for c in db.query(Child).filter(Child.id.in_(child_ids)).all()}

    # Build class_name map for all children
    enrollments = (
        db.query(EnrollmentApplication)
        .filter(EnrollmentApplication.child_id.in_(child_ids), EnrollmentApplication.status == EnrollmentStatus.ACTIVE)
        .all()
    )
    class_ids = {e.child_id: e.class_id for e in enrollments}
    classes = {c.id: c for c in db.query(Class).filter(Class.id.in_(class_ids.values())).all()}
    class_name_map = {
        cid: (classes[class_ids[cid]].name_ar or classes[class_ids[cid]].name_en or "")
        for cid in class_ids if class_ids[cid] in classes
    }

    report_list = [
        {
            "id": r.id,
            "child_id": r.child_id,
            "child_name": f"{child_map[r.child_id].first_name} {child_map[r.child_id].last_name}" if r.child_id in child_map else "",
            "class_name": class_name_map.get(r.child_id, ""),
            "date": str(r.date),
            "status": r.status.value if r.status else None,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "notes": r.notes,
        }
        for r in reports
    ]

    # Stats over ALL reports for this supervisor (not just the filtered set)
    all_reports = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids)).all()
    stats = {
        "submitted": sum(1 for r in all_reports if r.status == DailyReportStatus.SUBMITTED),
        "pending": sum(1 for r in all_reports if r.status in (DailyReportStatus.SUBMITTED, DailyReportStatus.DRAFT)),
        "draft": sum(1 for r in all_reports if r.status == DailyReportStatus.DRAFT),
        "sent_to_parent": sum(1 for r in all_reports if r.status == DailyReportStatus.SENT_TO_PARENT),
    }

    return {"reports": report_list, "stats": stats}


class DailyReportIn(BaseModel):
    child_id: int
    date: str
    status: str = "DRAFT"  # DRAFT | SUBMITTED
    arrival_time: Optional[str] = None
    leave_time: Optional[str] = None
    breakfast: bool = False
    snack: bool = False
    milk: bool = False
    lunch: bool = False
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    activities: Optional[str] = None
    notes: Optional[str] = None


@router.get("/daily-reports/{report_id}")
def get_daily_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_supervisor_owns_child(current_user.id, report.child_id, db)
    from models import Child
    child = db.query(Child).filter(Child.id == report.child_id).first()
    return {
        "id": report.id,
        "child_id": report.child_id,
        "child_name": f"{child.first_name} {child.last_name}" if child else "",
        "date": str(report.date),
        "status": report.status.value if report.status else None,
        "arrival_time": report.arrival_time,
        "leave_time": report.leave_time,
        "breakfast": report.breakfast,
        "snack": report.snack,
        "milk": report.milk,
        "lunch": report.lunch,
        "nap_start": report.nap_start,
        "nap_end": report.nap_end,
        "activities": report.activities,
        "notes": report.notes,
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
    }


@router.delete("/daily-reports/{report_id}", status_code=204)
def delete_daily_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_supervisor_owns_child(current_user.id, report.child_id, db)
    if report.status != DailyReportStatus.DRAFT:
        raise HTTPException(status_code=403, detail="Only DRAFT reports can be deleted.")
    db.delete(report)
    db.commit()


@router.post("/daily-reports")
def create_daily_report(
    body: DailyReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    assert_supervisor_owns_child(current_user.id, body.child_id, db)

    # Reject duplicate report for same child + date
    existing = db.query(DailyReport).filter(
        DailyReport.child_id == body.child_id,
        DailyReport.date == date.fromisoformat(body.date),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A report for this child on {body.date} already exists (id={existing.id}).")

    # Only DRAFT or SUBMITTED allowed from supervisor
    if body.status not in ("DRAFT", "SUBMITTED"):
        raise HTTPException(status_code=400, detail="Supervisor can only save as DRAFT or SUBMITTED.")

    target_status = DailyReportStatus.DRAFT if body.status == "DRAFT" else DailyReportStatus.SUBMITTED
    now = datetime.now(timezone.utc)

    report = DailyReport(
        child_id=body.child_id,
        date=date.fromisoformat(body.date),
        status=target_status,
        submitted_by=current_user.id,
        submitted_at=now if target_status == DailyReportStatus.SUBMITTED else None,
        arrival_time=body.arrival_time,
        leave_time=body.leave_time,
        breakfast=body.breakfast,
        snack=body.snack,
        milk=body.milk,
        lunch=body.lunch,
        nap_start=body.nap_start,
        nap_end=body.nap_end,
        activities=body.activities,
        notes=body.notes,
        kindergarten_id=current_user.kindergarten_id,
        created_at=now,
    )
    db.add(report)
    db.flush()
    db.add(AuditLog(
        user_id=current_user.id,
        action=target_status.value.lower(),
        entity_type="daily_report",
        entity_id=report.id,
        details=f"Supervisor created daily report for child {body.child_id} dated {body.date} as {target_status.value}",
    ))
    db.commit()
    db.refresh(report)
    return {"id": report.id, "status": report.status.value}


class DailyReportPatch(BaseModel):
    """Partial update schema — all fields optional for PATCH-style PUT."""
    status: Optional[str] = None
    arrival_time: Optional[str] = None
    leave_time: Optional[str] = None
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    activities: Optional[str] = None
    notes: Optional[str] = None


@router.put("/daily-reports/{report_id}")
def update_daily_report(
    report_id: int,
    body: DailyReportPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_supervisor_owns_child(current_user.id, report.child_id, db)

    # Supervisor can only edit while DRAFT
    if report.status != DailyReportStatus.DRAFT:
        raise HTTPException(status_code=403, detail="Report is already submitted and cannot be edited.")

    now = datetime.now(timezone.utc)
    for field in ("arrival_time", "leave_time", "breakfast", "snack", "milk",
                  "lunch", "nap_start", "nap_end", "activities", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(report, field, val)

    if body.status:
        target_status = DailyReportStatus.DRAFT if body.status == "DRAFT" else DailyReportStatus.SUBMITTED
        report.status = target_status
        if target_status == DailyReportStatus.SUBMITTED:
            report.submitted_at = now

    db.commit()
    return {"id": report.id, "status": report.status.value}


@router.put("/daily-reports/{report_id}/submit")
def submit_daily_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    """Convenience endpoint: transition report from DRAFT → SUBMITTED."""
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_supervisor_owns_child(current_user.id, report.child_id, db)
    if report.status != DailyReportStatus.DRAFT:
        raise HTTPException(status_code=403, detail="Only DRAFT reports can be submitted.")
    report.status = DailyReportStatus.SUBMITTED
    report.submitted_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=current_user.id,
        action="submit",
        entity_type="daily_report",
        entity_id=report.id,
        details=f"Supervisor submitted daily report for child {report.child_id}",
    ))
    db.commit()
    return {"id": report.id, "status": report.status.value}


# ---------------------------------------------------------------------------
# Safety Incidents (scoped)
# ---------------------------------------------------------------------------


class IncidentIn(BaseModel):
    child_id: int
    type: str
    severity_level: str
    description: str
    occurred_at: Optional[str] = None
    parent_informed: bool = False


@router.post("/safety-incidents", status_code=201)
def create_safety_incident(
    body: IncidentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    assert_supervisor_owns_child(current_user.id, body.child_id, db)

    try:
        inc_type = IncidentType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid incident type: {body.type}")
    try:
        severity = SeverityLevel(body.severity_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid severity level: {body.severity_level}")

    occurred_at = (
        datetime.fromisoformat(body.occurred_at) if body.occurred_at
        else datetime.now(timezone.utc)
    )

    incident = Incident(
        child_id=body.child_id,
        kindergarten_id=current_user.kindergarten_id,
        supervisor_id=current_user.id,
        type=inc_type,
        severity_level=severity,
        description=body.description,
        occurred_at=occurred_at,
        parent_informed=body.parent_informed,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return {"id": incident.id, "status": "created"}


@router.get("/safety-incidents")
def get_safety_incidents(
    severity: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return {"incidents": [], "stats": {"open": 0, "high_severity": 0, "closed": 0}}

    q = db.query(Incident).filter(Incident.child_id.in_(child_ids), Incident.deleted_at.is_(None))
    if severity:
        try:
            q = q.filter(Incident.severity_level == SeverityLevel(severity.upper()))
        except ValueError:
            pass
    if type_filter:
        try:
            q = q.filter(Incident.type == IncidentType(type_filter.upper()))
        except ValueError:
            pass

    incidents = q.order_by(Incident.occurred_at.desc()).all()
    from models import Child
    child_map = {c.id: c for c in db.query(Child).filter(Child.id.in_(child_ids)).all()}

    def _incident_status(i: Incident) -> str:
        return "CLOSED" if i.closed_at else "OPEN"

    if status_filter:
        incidents = [i for i in incidents if _incident_status(i) == status_filter.upper()]

    result = [
        {
            "id": i.id,
            "child_name": f"{child_map[i.child_id].first_name} {child_map[i.child_id].last_name}" if i.child_id in child_map else "",
            "type": i.type.value if i.type else None,
            "severity_level": i.severity_level.value if i.severity_level else None,
            "status": _incident_status(i),
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
            "description": i.description,
            "parent_informed": i.parent_informed,
        }
        for i in incidents
    ]

    # Stats use all incidents for this supervisor (pre-type/severity filter for stats accuracy)
    all_incidents = db.query(Incident).filter(Incident.child_id.in_(child_ids), Incident.deleted_at.is_(None)).all()
    stats = {
        "open": sum(1 for i in all_incidents if not i.closed_at),
        "high_severity": sum(1 for i in all_incidents if i.severity_level in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)),
        "closed": sum(1 for i in all_incidents if i.closed_at),
    }

    return {"incidents": result, "stats": stats}


# ---------------------------------------------------------------------------
# Messages — auto-route to supervisor's kindergarten manager
# ---------------------------------------------------------------------------


def _message_list(messages, current_user_id: int, db: Session):
    # Batch-fetch read receipts for all messages in this list
    msg_ids = [m.id for m in messages]
    read_set = set()
    if msg_ids:
        read_rows = (
            db.query(MessageRecipient.message_id)
            .filter(
                MessageRecipient.message_id.in_(msg_ids),
                MessageRecipient.recipient_user_id == current_user_id,
                MessageRecipient.read_at.isnot(None),
            )
            .all()
        )
        read_set = {r.message_id for r in read_rows}

    result = []
    for m in messages:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        result.append({
            "id": m.id,
            "direction": "sent" if m.sender_id == current_user_id else "received",
            "subject": m.subject,
            "body": m.message_body or "",
            "preview": (m.message_body or "")[:100],
            "sender_name": sender.full_name or sender.username if sender else "",
            "is_read": m.id in read_set or m.sender_id == current_user_id,
            "attachment_url": None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return result


@router.get("/messages/inbox")
@router.get("/messages")
def get_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    messages = (
        db.query(Message)
        .filter(
            or_(
                Message.sender_id == current_user.id,
                Message.recipient_id == current_user.id,
            )
        )
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )
    return _message_list(messages, current_user.id, db)


@router.put("/messages/{message_id}/read")
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    msg = db.query(Message).filter(Message.id == message_id, Message.recipient_id == current_user.id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    now = datetime.now(timezone.utc)
    recipient_row = db.query(MessageRecipient).filter(
        MessageRecipient.message_id == message_id,
        MessageRecipient.recipient_user_id == current_user.id,
    ).first()
    if recipient_row:
        if recipient_row.read_at is None:
            recipient_row.read_at = now
    else:
        db.add(MessageRecipient(
            message_id=message_id,
            recipient_user_id=current_user.id,
            read_at=now,
        ))
    db.commit()
    return {"status": "ok"}


class MessageIn(BaseModel):
    subject: Optional[str] = None
    body: str


@router.post("/messages")
def send_message_to_manager(
    body: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    # Auto-resolve recipient = manager of supervisor's kindergarten
    if not current_user.kindergarten_id:
        raise HTTPException(status_code=400, detail="Supervisor is not assigned to a kindergarten.")

    manager = (
        db.query(User)
        .filter(
            User.role == UserRole.MANAGER,
            User.kindergarten_id == current_user.kindergarten_id,
            User.deleted_at.is_(None),
        )
        .first()
    )
    if not manager:
        raise HTTPException(status_code=404, detail="No manager found for your kindergarten.")

    msg = Message(
        thread_type=MessageThreadType.DIRECT,
        sender_id=current_user.id,
        recipient_id=manager.id,
        kindergarten_id=current_user.kindergarten_id,
        subject=body.subject,
        message_body=body.body,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "recipient": manager.username}


# ---------------------------------------------------------------------------
# KPI — scoped + Redis-cached (TTL=300s)
# ---------------------------------------------------------------------------


@router.get("/kpi")
def get_supervisor_kpi(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    today = date.today()
    date_from = date.fromisoformat(from_date) if from_date else today - timedelta(days=6)
    date_to = date.fromisoformat(to_date) if to_date else today

    lang = current_user.preferred_language or "ar"
    cache_key = f"supervisor_kpi:{current_user.id}:{date_from}:{date_to}:{lang}"

    # Try Redis cache
    try:
        from cache_service import get_cache, set_cache
        cached = get_cache(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        cached = None

    child_ids = list(get_supervisor_child_ids(current_user.id, db))
    from models import Child
    children = db.query(Child).filter(Child.id.in_(child_ids)).all() if child_ids else []

    # Reports in range
    reports = (
        db.query(DailyReport)
        .filter(
            DailyReport.child_id.in_(child_ids),
            DailyReport.date >= date_from,
            DailyReport.date <= date_to,
        )
        .all()
        if child_ids
        else []
    )

    # Days in range
    num_days = (date_to - date_from).days + 1
    expected_per_child = num_days

    per_child = []
    for c in children:
        child_reports = [r for r in reports if r.child_id == c.id]
        submitted = len([r for r in child_reports if r.status in (DailyReportStatus.SUBMITTED, DailyReportStatus.APPROVED, DailyReportStatus.SENT_TO_PARENT)])
        missing = max(0, expected_per_child - len(child_reports))
        trend = "up" if submitted >= max(1, expected_per_child * 0.8) else ("down" if submitted == 0 else "flat")
        per_child.append(
            {
                "child_id": c.id,
                "name": f"{c.first_name} {c.last_name}",
                "reports_submitted": submitted,
                "missing_reports": missing,
                "trend": trend,
            }
        )

    total_expected = len(children) * num_days
    total_submitted = len([r for r in reports if r.status in (DailyReportStatus.SUBMITTED, DailyReportStatus.APPROVED, DailyReportStatus.SENT_TO_PARENT)])
    completion_rate = round(total_submitted / total_expected * 100, 1) if total_expected else 0

    # Daily trend (reports per day)
    from collections import defaultdict
    daily_counts: dict = defaultdict(int)
    for r in reports:
        daily_counts[str(r.date)] += 1
    trend_labels = [str(date_from + timedelta(days=i)) for i in range(num_days)]
    trend_values = [daily_counts.get(d, 0) for d in trend_labels]

    # Activity (last login, days active this month)
    last_login = current_user.last_login_at
    days_active = 0
    try:
        from models import AuditLog
        month_start = today.replace(day=1)
        days_active = (
            db.query(func.count(func.distinct(func.date(AuditLog.created_at))))
            .filter(
                AuditLog.user_id == current_user.id,
                AuditLog.created_at >= month_start,
            )
            .scalar() or 0
        )
    except Exception:
        days_active = 0

    result = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "completion_rate": completion_rate,
        "per_child": per_child,
        "trend_labels": trend_labels,
        "trend_values": trend_values,
        "last_login": last_login.isoformat() if last_login else None,
        "total_children": len(children),
        "days_active_this_month": days_active,
    }

    try:
        from cache_service import set_cache
        set_cache(cache_key, json.dumps(result), ttl=300)
    except Exception:
        pass

    return result




# ---------------------------------------------------------------------------
# Profile & Settings
# ---------------------------------------------------------------------------


@router.get("/profile")
def get_supervisor_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    from models import Class, Kindergarten
    # Assigned classes
    assignments = (
        db.query(SupervisorAssignment)
        .filter(
            SupervisorAssignment.supervisor_id == current_user.id,
            SupervisorAssignment.deleted_at.is_(None),
        )
        .all()
    )
    classes = []
    for a in assignments:
        c = a.class_
        if c:
            classes.append({
                "id": c.id,
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "is_primary": a.is_primary,
            })

    # Kindergarten name
    kg = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).first() if current_user.kindergarten_id else None

    # Children count
    child_ids = list(get_supervisor_child_ids(current_user.id, db))

    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name or "",
        "email": current_user.email or "",
        "phone_number": current_user.phone_number or "",
        "role": current_user.role.value,
        "preferred_language": current_user.preferred_language or "ar",
        "kindergarten_id": current_user.kindergarten_id,
        "kindergarten_name_ar": kg.name_ar if kg else "",
        "kindergarten_name_en": kg.name_en if kg else "",
        "classes": classes,
        "total_children": len(child_ids),
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }


class SettingsIn(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    preferred_language: Optional[str] = None


@router.put("/settings")
def update_supervisor_settings(
    body: SettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    if body.phone_number is not None:
        current_user.phone_number = body.phone_number.strip() or None
    if body.email is not None:
        current_user.email = body.email.strip() or None
    if body.preferred_language is not None:
        if body.preferred_language not in ("ar", "en"):
            raise HTTPException(status_code=400, detail="preferred_language must be 'ar' or 'en'.")
        current_user.preferred_language = body.preferred_language
    db.commit()
    return {"status": "ok"}


@router.get("/kpi/export")
def export_supervisor_kpi(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    """HTML-to-print export (returns HTML page with print-ready KPI summary)."""
    from fastapi.responses import HTMLResponse
    kpi = get_supervisor_kpi(from_date=from_date, to_date=to_date, db=db, current_user=current_user)

    rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r['reports_submitted']}</td><td>{r['missing_reports']}</td><td>{r['trend']}</td></tr>"
        for r in kpi["per_child"]
    )
    html = f"""<!DOCTYPE html><html dir="rtl" lang="ar"><head>
<meta charset="UTF-8"><title>KPI Export</title>
<style>body{{font-family:sans-serif;padding:20px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px 10px}}@media print{{.no-print{{display:none}}}}</style>
</head><body>
<button class="no-print" onclick="window.print()">طباعة</button>
<h2>مؤشرات أداء المشرف: {current_user.full_name or current_user.username}</h2>
<p>الفترة: {kpi['date_from']} — {kpi['date_to']}</p>
<p>معدل الإكمال: <strong>{kpi['completion_rate']}%</strong></p>
<table><thead><tr><th>الطفل</th><th>تقارير مُقدَّمة</th><th>مفقودة</th><th>الاتجاه</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    return HTMLResponse(content=html)
