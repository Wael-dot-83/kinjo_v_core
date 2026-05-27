"""
Supervisor-scoped API endpoints.

All routes enforce that the caller is SUPERVISOR and that every
child/class referenced belongs to the caller's assigned classes.

Redis caching (TTL=300s) is used for the KPI endpoint.
Cache keys include supervisor_id + date range to prevent cross-user leaks.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, and_, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from mfa_service import (
    decrypt_secret,
    encrypt_secret,
    generate_totp_secret,
    provisioning_uri,
    qr_code_data_url,
    verify_code,
)
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
    MessageUserState,
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

_UPLOAD_TYPE_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
_ALLOWED_UPLOAD_TYPES = set(_UPLOAD_TYPE_TO_EXT)

# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _require_supervisor(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor access only.")
    return current_user


def _require_supervisor_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.SUPERVISOR, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor/Admin access only.")
    return current_user


def _default_notification_preferences() -> dict:
    return {
        "in_app": True,
        "email": True,
        "new_messages": {"in_app": True, "email": True},
        "report_approved": {"in_app": True, "email": True},
        "incident_update": {"in_app": True, "email": True},
    }


def _read_notification_preferences(user: User) -> dict:
    raw = user.notification_preferences if isinstance(user.notification_preferences, dict) else {}
    prefs = {**_default_notification_preferences()}
    for key in ("in_app", "email"):
        if isinstance(raw.get(key), bool):
            prefs[key] = raw[key]
    for key in ("new_messages", "report_approved", "incident_update"):
        raw_event = raw.get(key) if isinstance(raw.get(key), dict) else {}
        prefs[key] = {
            "in_app": raw_event.get("in_app", prefs[key]["in_app"]),
            "email": raw_event.get("email", prefs[key]["email"]),
        }
    security = raw.get("_security") if isinstance(raw.get("_security"), dict) else {}
    if security:
        prefs["_security"] = security
    return prefs


def _write_notification_preferences(user: User, prefs: dict) -> None:
    user.notification_preferences = prefs


def _backup_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_backup_codes() -> list[str]:
    return [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(6)]


def _sync_totp_secret(user: User, encrypted_secret: Optional[str]) -> None:
    user.mfa_secret = encrypted_secret
    if hasattr(user, "totp_secret"):
        user.totp_secret = encrypted_secret


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
    enrollments = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id.in_(child_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
        )
        .all()
    )
    enrollments_by_child_id = {enrollment.child_id: enrollment for enrollment in enrollments}
    today = _ksa_now().date()
    attendance_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.child_id.in_(child_ids),
            AttendanceLog.date == today,
        )
        .all()
    )
    attendance_by_child_id = {log.child_id: log for log in attendance_logs}

    return {
        "children": [
            {
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "name": f"{c.first_name} {c.last_name}".strip(),
                "gender": c.gender.value if c.gender else None,
                "photo_url": c.photo_url,
                "class_id": enrollments_by_child_id.get(c.id).class_id if enrollments_by_child_id.get(c.id) else None,
                "class_name": (
                    enrollments_by_child_id.get(c.id).class_.name_ar
                    if enrollments_by_child_id.get(c.id) and enrollments_by_child_id.get(c.id).class_
                    else None
                ),
                "kindergarten_id": enrollments_by_child_id.get(c.id).kindergarten_id if enrollments_by_child_id.get(c.id) else None,
                "kindergarten_name": (
                    enrollments_by_child_id.get(c.id).kindergarten.name_ar
                    if enrollments_by_child_id.get(c.id) and enrollments_by_child_id.get(c.id).kindergarten
                    else None
                ),
                "status": (
                    "not_arrived"
                    if _attendance_status_from_log(attendance_by_child_id.get(c.id)) == "not_marked"
                    else _attendance_status_from_log(attendance_by_child_id.get(c.id))
                ),
                "attendance_status": (
                    "not_arrived"
                    if _attendance_status_from_log(attendance_by_child_id.get(c.id)) == "not_marked"
                    else _attendance_status_from_log(attendance_by_child_id.get(c.id))
                ),
                "check_in_time": (
                    attendance_by_child_id.get(c.id).check_in_at.strftime("%H:%M")
                    if attendance_by_child_id.get(c.id) and attendance_by_child_id.get(c.id).check_in_at
                    else None
                ),
                "check_out_time": (
                    attendance_by_child_id.get(c.id).check_out_at.strftime("%H:%M")
                    if attendance_by_child_id.get(c.id) and attendance_by_child_id.get(c.id).check_out_at
                    else None
                ),
            }
            for c in children
        ]
    }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------


KSA_TZ = timezone(timedelta(hours=3))


def _ksa_now() -> datetime:
    return datetime.now(KSA_TZ)


def _attendance_status_from_log(log: Optional[AttendanceLog], *, include_checkout: bool = True) -> str:
    if not log:
        return "not_arrived"
    if include_checkout and log.check_out_at:
        return "checked_out"
    status_value = (log.status.value if getattr(log, "status", None) else "").upper()
    if status_value == "ABSENT":
        return "absent"
    if status_value == "LATE":
        return "late"
    return "present"


def _attendance_summary_status(log: Optional[AttendanceLog]) -> str:
    if not log:
        return "not_marked"
    return _attendance_status_from_log(log, include_checkout=False)


def _parse_attendance_date(value: Optional[str], default_date: date) -> date:
    if not value:
        return default_date
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attendance date")


def _attendance_lock_state(target_date: date, server_today: date) -> dict:
    if target_date.weekday() == 4:
        return {
            "locked": True,
            "lock_reason": "FRIDAY_LOCK",
            "lock_message": "Cannot mark attendance on Friday (weekend)",
        }
    if target_date != server_today:
        return {
            "locked": True,
            "lock_reason": "DATE_LOCK",
            "lock_message": "Attendance can only be marked for today",
        }
    return {"locked": False, "lock_reason": None, "lock_message": None}


def _empty_attendance_payload(target_date: date, server_today: date, lock: Optional[dict] = None) -> dict:
    lock = lock or {"locked": False, "lock_reason": None, "lock_message": None}
    return {
        "date": str(target_date),
        "server_date": str(server_today),
        "locked": lock["locked"],
        "lock_reason": lock.get("lock_reason"),
        "lock_message": lock.get("lock_message"),
        "children": [],
        "present": 0,
        "absent": 0,
        "late": 0,
        "not_marked": 0,
        "total": 0,
    }


def _attendance_payload(
    date_str: str = Query(None, alias="date"),
    override: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor_or_admin),
):
    server_today = _ksa_now().date()
    target_date = _parse_attendance_date(date_str, server_today)
    lock = _attendance_lock_state(target_date, server_today)

    if lock["locked"]:
        if not override:
            return _empty_attendance_payload(target_date, server_today, lock)
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can override attendance date lock.")

    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return _empty_attendance_payload(target_date, server_today)

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
        att_status = _attendance_status_from_log(log)
        result.append(
            {
                "id": cid,
                "name": f"{child.first_name} {child.last_name}",
                "class_name": class_name_map.get(cid, ""),
                "status": att_status,
                "attendance_status": att_status,
                "check_in_time": check_in_at.strftime("%H:%M") if check_in_at else None,
                "check_out_time": check_out_at.strftime("%H:%M") if check_out_at else None,
                "late_reason": getattr(log, "late_reason", None) if log else None,
            }
        )

    result.sort(key=lambda row: row["name"].lower())
    summary_statuses = [_attendance_summary_status(logged.get(cid)) for cid in children]
    present = sum(1 for status_value in summary_statuses if status_value == "present")
    absent = sum(1 for status_value in summary_statuses if status_value == "absent")
    late = sum(1 for status_value in summary_statuses if status_value == "late")
    not_marked = sum(1 for status_value in summary_statuses if status_value == "not_marked")

    return {
        "date": str(target_date),
        "server_date": str(server_today),
        "locked": False,
        "children": result,
        "present": present,
        "absent": absent,
        "late": late,
        "not_marked": not_marked,
        "total": len(result),
    }


@router.get("/attendance")
def get_attendance(
    date_str: str = Query(None, alias="date"),
    override: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor_or_admin),
):
    return _attendance_payload(date_str=date_str, override=override, db=db, current_user=current_user)


@router.get("/attendance/summary")
def get_attendance_summary(
    date_str: str = Query(None, alias="date"),
    override: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor_or_admin),
):
    payload = _attendance_payload(date_str=date_str, override=override, db=db, current_user=current_user)
    return {
        "date": payload["date"],
        "server_date": payload["server_date"],
        "locked": payload["locked"],
        "lock_reason": payload.get("lock_reason"),
        "lock_message": payload.get("lock_message"),
        "present": payload["present"],
        "absent": payload["absent"],
        "late": payload["late"],
        "not_marked": payload["not_marked"],
        "total": payload["total"],
    }


@router.get("/attendance/status")
def get_attendance_status(
    date_str: str = Query(None, alias="date"),
    override: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor_or_admin),
):
    payload = _attendance_payload(date_str=date_str, override=override, db=db, current_user=current_user)
    return {
        "date": payload["date"],
        "server_date": payload["server_date"],
        "locked": payload["locked"],
        "lock_reason": payload.get("lock_reason"),
        "lock_message": payload.get("lock_message"),
        "children": payload["children"],
    }


class AttendanceIn(BaseModel):
    child_id: int
    status: Optional[str] = None  # "present" | "absent" | "late"
    action: Optional[str] = None  # Backward compatible: "check_in" | "check_out" | "mark_absent"
    date: Optional[str] = None
    late_reason: Optional[str] = None


@router.post("/attendance")
def record_attendance(
    body: AttendanceIn,
    override: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor_or_admin),
):
    if current_user.role == UserRole.SUPERVISOR:
        assert_supervisor_owns_child(current_user.id, body.child_id, db)
    server_now = _ksa_now()
    server_today = server_now.date()
    target_date = _parse_attendance_date(body.date, server_today)
    lock = _attendance_lock_state(target_date, server_today)
    override_bypassed_lock = False

    if lock["locked"]:
        if not override:
            raise HTTPException(status_code=400, detail=lock["lock_message"])
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can override attendance date lock.")
        override_bypassed_lock = True

    now = server_now

    log = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.child_id == body.child_id, AttendanceLog.date == target_date)
        .first()
    )

    # Find the child's actual enrolled class (within supervisor's scope)
    from models import EnrollmentApplication, EnrollmentStatus
    class_ids = get_supervisor_class_ids(current_user.id, db)
    enrollment_query = db.query(EnrollmentApplication).filter(
        EnrollmentApplication.child_id == body.child_id,
        EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
    )
    if current_user.role == UserRole.SUPERVISOR:
        enrollment_query = enrollment_query.filter(EnrollmentApplication.class_id.in_(class_ids))
    enrollment = enrollment_query.first()
    class_id = enrollment.class_id if enrollment else None
    if class_id is None:
        raise HTTPException(status_code=400, detail="Child has no active class enrollment.")

    from models import AttendanceStatus
    requested_status = (body.status or "").strip().lower()
    if not requested_status and body.action:
        action = body.action.strip().lower()
        if action in ("check_in", "present"):
            requested_status = "present"
        elif action in ("mark_absent", "absent"):
            requested_status = "absent"
        elif action in ("late", "mark_late"):
            requested_status = "late"
        elif action == "check_out":
            requested_status = "checked_out"

    if requested_status in ("present", "late"):
        clean_late_reason = (body.late_reason or "").strip() or None
        if not log:
            log = AttendanceLog(
                child_id=body.child_id,
                class_id=class_id,
                date=target_date,
                status=AttendanceStatus.LATE if requested_status == "late" else AttendanceStatus.PRESENT,
                check_in_at=now,
                recorded_by=current_user.id,
            )
            db.add(log)
        else:
            if not log.check_in_at:
                log.check_in_at = now
            log.status = AttendanceStatus.LATE if requested_status == "late" else AttendanceStatus.PRESENT
        log.late_reason = clean_late_reason if requested_status == "late" else None
    elif requested_status == "checked_out":
        if not log:
            raise HTTPException(status_code=400, detail="No check-in found.")
        log.check_out_at = now
    elif requested_status == "absent":
        if not log:
            log = AttendanceLog(
                child_id=body.child_id,
                class_id=class_id,
                date=target_date,
                status=AttendanceStatus.ABSENT,
                check_in_at=None,
                check_out_at=None,
                recorded_by=current_user.id,
            )
            db.add(log)
        else:
            log.status = AttendanceStatus.ABSENT
            log.check_in_at = None
            log.check_out_at = None
            log.late_reason = None
    else:
        raise HTTPException(status_code=400, detail="Invalid status/action.")

    if override_bypassed_lock and current_user.role == UserRole.ADMIN:
        db.add(
            AuditLog(
                user_id=current_user.id,
                action="attendance_override",
                entity_type="attendance",
                entity_id=body.child_id,
                details=(
                    f"Override attendance for {target_date} ({requested_status}); "
                    f"reason={lock.get('lock_reason')}"
                ),
                actor_role=current_user.role.value,
                sensitivity_level=3,
            )
        )

    db.commit()
    db.refresh(log)
    updated_status = _attendance_status_from_log(log)
    return {
        "status": "ok",
        "log_id": log.id,
        "child_id": log.child_id,
        "class_id": log.class_id,
        "attendance_status": updated_status,
        "check_in_time": log.check_in_at.strftime("%H:%M") if log.check_in_at else None,
        "check_out_time": log.check_out_at.strftime("%H:%M") if log.check_out_at else None,
        "late_reason": log.late_reason,
        "date": str(target_date),
        "server_date": str(server_today),
    }


# ---------------------------------------------------------------------------
# Daily Reports
# ---------------------------------------------------------------------------


@router.get("/daily-reports")
def get_daily_reports(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    status_filter: Optional[str] = Query(None, alias="status"),
    child_id: Optional[int] = Query(None),
    exact_date: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    child_ids = get_supervisor_child_ids(current_user.id, db)
    if not child_ids:
        return {"reports": [], "stats": {"submitted": 0, "pending": 0, "draft": 0, "sent_to_parent": 0}}

    q = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids))
    if child_id:
        q = q.filter(DailyReport.child_id == child_id)
    if exact_date:
        try:
            q = q.filter(DailyReport.date == date.fromisoformat(exact_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format.")
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
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    assert_supervisor_owns_child(current_user.id, body.child_id, db)
    target_date = date.fromisoformat(body.date)

    # Reject duplicate report for same child + date unless caller explicitly
    # requests an overwrite. Overwrite updates the existing row rather than
    # creating a second report for the same child/day.
    existing = db.query(DailyReport).filter(
        DailyReport.child_id == body.child_id,
        DailyReport.date == target_date,
    ).first()
    if existing:
        if not force:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"A report for this child on {body.date} already exists.",
                    "existing_id": existing.id,
                    "can_force": True,
                },
            )

    # Only DRAFT or SUBMITTED allowed from supervisor
    if body.status not in ("DRAFT", "SUBMITTED"):
        raise HTTPException(status_code=400, detail="Supervisor can only save as DRAFT or SUBMITTED.")

    target_status = DailyReportStatus.DRAFT if body.status == "DRAFT" else DailyReportStatus.SUBMITTED
    now = datetime.now(timezone.utc)
    provided_fields = getattr(body, "model_fields_set", set())

    if existing and force:
        report = existing
        report.status = target_status
        report.submitted_by = current_user.id
        report.submitted_at = now if target_status == DailyReportStatus.SUBMITTED else None
        if "arrival_time" in provided_fields:
            report.arrival_time = body.arrival_time
        if "leave_time" in provided_fields:
            report.leave_time = body.leave_time
        if "breakfast" in provided_fields:
            report.breakfast = body.breakfast
        if "snack" in provided_fields:
            report.snack = body.snack
        if "milk" in provided_fields:
            report.milk = body.milk
        if "lunch" in provided_fields:
            report.lunch = body.lunch
        if "nap_start" in provided_fields:
            report.nap_start = body.nap_start
        if "nap_end" in provided_fields:
            report.nap_end = body.nap_end
        if "activities" in provided_fields:
            report.activities = body.activities
        if "notes" in provided_fields:
            report.notes = body.notes
        report.kindergarten_id = current_user.kindergarten_id
        db.add(AuditLog(
            user_id=current_user.id,
            action="force_update",
            entity_type="daily_report",
            entity_id=report.id,
            details=f"Supervisor overwrote daily report for child {body.child_id} dated {body.date} as {target_status.value}",
        ))
    else:
        report = DailyReport(
            child_id=body.child_id,
            date=target_date,
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
    return {"id": report.id, "status": report.status.value, "forced": bool(existing and force)}


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
        reported_by=current_user.id,
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
            "resolution_notes": i.resolution_notes,
            "attachment_url": i.attachment_url,
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


@router.put("/safety-incidents/{incident_id}/resolve")
@router.post("/safety-incidents/{incident_id}/resolve")
def resolve_safety_incident(
    incident_id: int,
    resolution_notes: Optional[str] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    child_ids = get_supervisor_child_ids(current_user.id, db)
    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.child_id.in_(child_ids),
            Incident.deleted_at.is_(None),
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")

    attachment_url = None
    if attachment and attachment.filename:
        ct = (attachment.content_type or "").lower()
        if ct not in _ALLOWED_UPLOAD_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported attachment type")
        ext = _UPLOAD_TYPE_TO_EXT[ct]
        upload_dir = os.path.join("static", "uploads", "incidents")
        os.makedirs(upload_dir, exist_ok=True)
        file_name = f"incident_{incident_id}_{uuid.uuid4().hex}{ext}"
        out_path = os.path.join(upload_dir, file_name)
        with open(out_path, "wb") as f:
            f.write(attachment.file.read())
        attachment_url = f"/{out_path.replace(os.sep, '/')}"

    incident.closed_at = datetime.now(timezone.utc)
    incident.closed_by = current_user.id
    if resolution_notes:
        incident.resolution_notes = resolution_notes
    if attachment_url:
        incident.attachment_url = attachment_url

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="resolve",
            entity_type="incident",
            entity_id=incident.id,
            details="Supervisor resolved safety incident",
        )
    )
    db.commit()
    return {"status": "resolved", "id": incident.id, "attachment_url": attachment_url}


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
    try:
        deleted_state_subq = (
            db.query(MessageUserState.message_id)
            .filter(
                MessageUserState.user_id == current_user.id,
                MessageUserState.deleted_at.isnot(None),
            )
            .subquery()
        )
        messages = (
            db.query(Message)
            .filter(
                or_(
                    Message.sender_id == current_user.id,
                    Message.recipient_id == current_user.id,
                ),
                ~Message.id.in_(deleted_state_subq),
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )
    except OperationalError:
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


@router.get("/messages/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    deleted_state_subq = db.query(MessageUserState.message_id).filter(
        MessageUserState.user_id == current_user.id,
        MessageUserState.deleted_at.isnot(None),
    )
    unread_count = (
        db.query(func.count(Message.id))
        .filter(
            Message.recipient_id == current_user.id,
            Message.message_status != "deleted",
            ~Message.id.in_(deleted_state_subq),
            Message.id.notin_(
                db.query(MessageRecipient.message_id).filter(
                    MessageRecipient.recipient_user_id == current_user.id,
                    MessageRecipient.read_at.isnot(None),
                )
            ),
        )
        .scalar()
        or 0
    )
    return {"unread": unread_count, "unread_count": unread_count}


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
    body: Optional[MessageIn] = None,
    subject: Optional[str] = Form(None),
    body_text: Optional[str] = Form(None, alias="body"),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    resolved_subject = body.subject if body else subject
    resolved_body = body.body if body else body_text
    if not resolved_body:
        raise HTTPException(status_code=400, detail="Message body is required.")

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
        subject=resolved_subject,
        message_body=resolved_body,
    )
    db.add(msg)
    db.flush()

    if attachment and attachment.filename:
        ct = (attachment.content_type or "").lower()
        if ct not in _ALLOWED_UPLOAD_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported attachment type")
        ext = _UPLOAD_TYPE_TO_EXT[ct]
        uploads_dir = os.path.join("static", "uploads", "messages")
        os.makedirs(uploads_dir, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(uploads_dir, safe_name)
        with open(file_path, "wb") as f:
            f.write(attachment.file.read())
        from models import MessageAttachment

        db.add(
            MessageAttachment(
                message_id=msg.id,
                uploaded_by_id=current_user.id,
                file_name=attachment.filename,
                content_type=attachment.content_type or "application/octet-stream",
                file_size=os.path.getsize(file_path),
                storage_provider="local",
                storage_key=file_path,
                url=f"/{file_path.replace(os.sep, '/')}",
            )
        )

    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "recipient": manager.username}


@router.delete("/messages/{message_id}")
def delete_message_for_supervisor(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    msg = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            or_(Message.sender_id == current_user.id, Message.recipient_id == current_user.id),
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    try:
        state = db.query(MessageUserState).filter(
            MessageUserState.message_id == message_id,
            MessageUserState.user_id == current_user.id,
        ).first()
        if not state:
            state = MessageUserState(message_id=message_id, user_id=current_user.id)
            db.add(state)
        state.deleted_at = datetime.now(timezone.utc)
    except OperationalError:
        msg.message_status = "deleted"
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="delete",
            entity_type="message",
            entity_id=message_id,
            details="Supervisor soft-deleted message",
        )
    )
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# KPI — scoped + Redis-cached (TTL=300s)
# ---------------------------------------------------------------------------


@router.get("/kpi")
def get_supervisor_kpi(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    compare: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    today = date.today()
    date_from = date.fromisoformat(from_date) if from_date else today - timedelta(days=6)
    date_to = date.fromisoformat(to_date) if to_date else today

    lang = current_user.preferred_language or "ar"
    cache_key = f"supervisor_kpi:{current_user.id}:{date_from}:{date_to}:{lang}:{int(compare)}"

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

    final_statuses = (
        DailyReportStatus.SUBMITTED,
        DailyReportStatus.APPROVED,
        DailyReportStatus.SENT_TO_PARENT,
    )

    per_child = []
    for c in children:
        child_reports = [r for r in reports if r.child_id == c.id]
        submitted = len([r for r in child_reports if r.status in final_statuses])
        missing = max(0, expected_per_child - len(child_reports))
        trend = "up" if submitted >= max(1, expected_per_child * 0.8) else ("down" if submitted == 0 else "flat")
        per_child.append(
            {
                "child_id": c.id,
                "name": f"{c.first_name} {c.last_name}",
                "reports_submitted": submitted,
                "reports_this_week": submitted,
                "missing_reports": missing,
                "trend": trend,
            }
        )

    total_expected = len(children) * num_days
    submitted_reports = [r for r in reports if r.status in final_statuses]
    total_submitted = len(submitted_reports)
    completion_rate = round(total_submitted / total_expected * 100, 1) if total_expected else 0
    on_time_reports = [
        report
        for report in submitted_reports
        if report.submitted_at and report.submitted_at.date() <= report.date
    ]
    on_time_rate = round(len(on_time_reports) / total_submitted * 100, 1) if total_submitted else 0
    report_lengths = [
        len((report.activities or "").strip()) + len((report.notes or "").strip())
        for report in submitted_reports
    ]
    avg_report_length = round(sum(report_lengths) / len(report_lengths), 1) if report_lengths else 0

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

    heatmap_start = date_to - timedelta(days=27)
    heatmap_counts = defaultdict(int)
    for report in reports:
        if heatmap_start <= report.date <= date_to:
            heatmap_counts[str(report.date)] += 1
    heatmap = []
    for offset in range(28):
        day = heatmap_start + timedelta(days=offset)
        count = heatmap_counts.get(str(day), 0)
        level = 3 if count >= 3 else 2 if count == 2 else 1 if count == 1 else 0
        heatmap.append({"date": str(day), "level": level})

    previous_completion_rate = None
    previous_on_time_rate = None
    if compare and num_days > 0:
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=num_days - 1)
        previous_reports = (
            db.query(DailyReport)
            .filter(
                DailyReport.child_id.in_(child_ids),
                DailyReport.date >= previous_from,
                DailyReport.date <= previous_to,
            )
            .all()
            if child_ids
            else []
        )
        previous_submitted = [report for report in previous_reports if report.status in final_statuses]
        previous_expected = len(children) * num_days
        previous_completion_rate = round(len(previous_submitted) / previous_expected * 100, 1) if previous_expected else 0
        previous_on_time = [
            report
            for report in previous_submitted
            if report.submitted_at and report.submitted_at.date() <= report.date
        ]
        previous_on_time_rate = round(len(previous_on_time) / len(previous_submitted) * 100, 1) if previous_submitted else 0

    result = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "completion_rate": completion_rate,
        "on_time_rate": on_time_rate,
        "avg_report_length": avg_report_length,
        "previous_completion_rate": previous_completion_rate,
        "previous_on_time_rate": previous_on_time_rate,
        "per_child": per_child,
        "trend_labels": trend_labels,
        "trend_values": trend_values,
        "last_login": last_login.isoformat() if last_login else None,
        "total_children": len(children),
        "days_active_this_month": days_active,
        "heatmap": heatmap,
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
        "mfa_enabled": current_user.mfa_enabled,
        "notification_preferences": _read_notification_preferences(current_user),
        "picture_url": (current_user.address or "").replace("profile_image:", "") if (current_user.address or "").startswith("profile_image:") else None,
    }


@router.get("/notification-preferences")
def get_notification_preferences(
    current_user: User = Depends(_require_supervisor),
):
    return _read_notification_preferences(current_user)


class NotificationPreferencesIn(BaseModel):
    in_app: bool = True
    email: bool = True
    new_messages: Optional[dict] = None
    report_approved: Optional[dict] = None
    incident_update: Optional[dict] = None


@router.put("/notification-preferences")
def update_notification_preferences(
    body: NotificationPreferencesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    prefs = _read_notification_preferences(current_user)
    prefs["in_app"] = bool(body.in_app)
    prefs["email"] = bool(body.email)
    for key in ("new_messages", "report_approved", "incident_update"):
        raw_value = getattr(body, key)
        if isinstance(raw_value, dict):
            prefs[key] = {
                "in_app": bool(raw_value.get("in_app", prefs[key]["in_app"])),
                "email": bool(raw_value.get("email", prefs[key]["email"])),
            }
    _write_notification_preferences(current_user, prefs)
    db.commit()
    return prefs


class SettingsIn(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    preferred_language: Optional[str] = None
    mfa_enabled: Optional[bool] = None


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
    if body.mfa_enabled is not None:
        current_user.mfa_enabled = bool(body.mfa_enabled)
    db.commit()
    return {"status": "ok", "mfa_enabled": current_user.mfa_enabled}


@router.post("/2fa/enable")
def enable_supervisor_2fa(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    if current_user.mfa_enabled and current_user.mfa_secret:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already enabled.")

    secret = generate_totp_secret()
    encrypted_secret = encrypt_secret(secret)
    backup_codes = _generate_backup_codes()
    prefs = _read_notification_preferences(current_user)
    prefs["_security"] = {
        "backup_code_hashes": [_backup_code_hash(code) for code in backup_codes],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _sync_totp_secret(current_user, encrypted_secret)
    current_user.mfa_enabled = True
    current_user.mfa_enrolled_at = datetime.now(timezone.utc)
    _write_notification_preferences(current_user, prefs)

    otpauth_uri = provisioning_uri(secret, current_user.email or current_user.username)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="enable_2fa",
            entity_type="user",
            entity_id=current_user.id,
            details="Supervisor enabled 2FA",
        )
    )
    db.commit()
    return {
        "status": "enabled",
        "manual_key": secret,
        "otpauth_uri": otpauth_uri,
        "qr_code_data_url": qr_code_data_url(otpauth_uri),
        "backup_codes": backup_codes,
    }


class DisableTwoFactorIn(BaseModel):
    code: str


@router.post("/2fa/disable")
def disable_supervisor_2fa(
    body: DisableTwoFactorIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    encrypted_secret = current_user.totp_secret or current_user.mfa_secret
    secret = decrypt_secret(encrypted_secret)
    if not current_user.mfa_enabled or not secret:
        raise HTTPException(status_code=409, detail="Two-factor authentication is not enabled.")
    if not verify_code(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid two-factor authentication code.")

    _sync_totp_secret(current_user, None)
    current_user.mfa_enabled = False
    prefs = _read_notification_preferences(current_user)
    prefs.pop("_security", None)
    _write_notification_preferences(current_user, prefs)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="disable_2fa",
            entity_type="user",
            entity_id=current_user.id,
            details="Supervisor disabled 2FA",
        )
    )
    db.commit()
    return {"status": "disabled"}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    confirm_password: Optional[str] = None


@router.post("/change-password")
def change_supervisor_password(
    body: ChangePasswordIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    from auth import get_password_hash, verify_password

    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    if body.confirm_password is not None and body.new_password != body.confirm_password:
        raise HTTPException(status_code=400, detail="New password confirmation does not match.")

    current_user.hashed_password = get_password_hash(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.post("/profile/picture")
def upload_supervisor_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    ct = (file.content_type or "").lower()
    _IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
    _IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
                  "image/gif": ".gif", "image/webp": ".webp"}
    if ct not in _IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only image uploads are allowed (png, jpeg, gif, webp)")

    uploads_dir = os.path.join("static", "uploads", "profiles")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = _IMAGE_EXT[ct]
    file_name = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    out_path = os.path.join(uploads_dir, file_name)
    with open(out_path, "wb") as f:
        f.write(file.file.read())

    current_user.address = f"profile_image:{out_path.replace(os.sep, '/')}"
    db.commit()
    return {"status": "ok", "picture_url": f"/{out_path.replace(os.sep, '/')}"}


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
