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
import logging
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional

_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today

import logging

logger = logging.getLogger(__name__)

_ALLOWED_OBSERVATION_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
_OBSERVATION_IMAGE_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, and_, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from audit_actions import AuditAction
from config import settings
import validators
import models
import schemas
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
    ACTIVE_ENROLLMENT_STATUSES,
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

def _get_supervisor_active_class_ids(db: Session, supervisor_id: int, on_date: date) -> set[int]:
    rows = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == supervisor_id,
        models.SupervisorAssignment.deleted_at.is_(None),
        models.SupervisorAssignment.start_date <= on_date,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= on_date,
        ),
    ).all()
    # Class membership comes solely from SupervisorAssignment now; the legacy
    # Class.supervisor_id read was removed (D1/B5). The primary assignment is a
    # SupervisorAssignment row, so it is already included above.
    class_ids = {row.class_id for row in rows}
    return class_ids


def _get_supervisor_child_enrollment(db: Session, supervisor_id: int, child_id: int):
    class_ids = _get_supervisor_active_class_ids(db, supervisor_id, datetime.now(_JORDAN_TZ).date())
    if not class_ids:
        return None
    return db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
        models.EnrollmentApplication.deleted_at.is_(None),
    ).first()

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


def _require_staff(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.SUPERVISOR, UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access only.")
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
            SupervisorAssignment.start_date <= datetime.now(_JORDAN_TZ).date(),
            or_(SupervisorAssignment.end_date.is_(None), SupervisorAssignment.end_date >= datetime.now(_JORDAN_TZ).date()),
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
    children = db.query(Child).filter(
        Child.id.in_(child_ids), Child.deleted_at.is_(None)
    ).all()
    enrollments = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id.in_(child_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
            EnrollmentApplication.deleted_at.is_(None),
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
                # Required by every client that lists these children: the daily
                # report picker and the class roster both run the list through
                # ChildAgeValidator.isEligible(child.date_of_birth). Without the
                # field that predicate is falsy for every row and the list comes
                # back empty, which is exactly what stopped supervisors filing
                # any daily report at all.
                "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None,
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
            EnrollmentApplication.deleted_at.is_(None),
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
        EnrollmentApplication.deleted_at.is_(None),
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
                action=AuditAction.ATTENDANCE_OVERRIDE,
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
    current_user: User = Depends(_require_staff),
):
    # Managers and admins see all children in their KG; supervisors see their assigned children
    if current_user.role == UserRole.SUPERVISOR:
        child_ids = get_supervisor_child_ids(current_user.id, db)
    else:
        from models import Child, EnrollmentApplication, EnrollmentStatus
        child_ids = [
            e.child_id for e in db.query(EnrollmentApplication).filter(
                EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
                EnrollmentApplication.deleted_at.is_(None),
                *([] if current_user.role == UserRole.ADMIN else
                  [EnrollmentApplication.kindergarten_id == current_user.kindergarten_id])
            ).all()
        ]
    if not child_ids:
        return {"reports": [], "stats": {"submitted": 0, "pending": 0, "draft": 0, "sent_to_parent": 0}}

    q = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids))
    if current_user.role == UserRole.SUPERVISOR:
        q = q.filter(DailyReport.kindergarten_id == current_user.kindergarten_id)
    if child_id:
        q = q.filter(DailyReport.child_id == child_id)
    if exact_date:
        try:
            q = q.filter(DailyReport.date == date.fromisoformat(exact_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format.")
    if from_date:
        try:
            q = q.filter(DailyReport.date >= date.fromisoformat(from_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from date format.")
    if to_date:
        try:
            q = q.filter(DailyReport.date <= date.fromisoformat(to_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to date format.")
    if status_filter:
        try:
            q = q.filter(DailyReport.status == DailyReportStatus(status_filter.upper()))
        except ValueError:
            allowed = ", ".join(item.value for item in DailyReportStatus)
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {allowed}.")

    reports = q.order_by(DailyReport.date.desc()).all()
    if current_user.role == UserRole.SUPERVISOR:
        from api.daily_reports_routes import _authorize_supervisor_report_access
        scoped_reports = []
        for report in reports:
            try:
                _authorize_supervisor_report_access(db, current_user, report)
            except HTTPException:
                continue
            scoped_reports.append(report)
        reports = scoped_reports
    from models import Child, Class, EnrollmentApplication, EnrollmentStatus
    child_map = {c.id: c for c in db.query(Child).filter(
        Child.id.in_(child_ids), Child.deleted_at.is_(None)
    ).all()}

    # Build class_name map for all children
    enrollments = (
        db.query(EnrollmentApplication)
        .filter(
            EnrollmentApplication.child_id.in_(child_ids),
            EnrollmentApplication.status == EnrollmentStatus.ACTIVE,
            EnrollmentApplication.deleted_at.is_(None),
        )
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
    all_reports_q = db.query(DailyReport).filter(DailyReport.child_id.in_(child_ids))
    if current_user.role == UserRole.SUPERVISOR:
        all_reports_q = all_reports_q.filter(DailyReport.kindergarten_id == current_user.kindergarten_id)
    all_reports = all_reports_q.all()
    if current_user.role == UserRole.SUPERVISOR:
        from api.daily_reports_routes import _authorize_supervisor_report_access
        scoped_all_reports = []
        for report in all_reports:
            try:
                _authorize_supervisor_report_access(db, current_user, report)
            except HTTPException:
                continue
            scoped_all_reports.append(report)
        all_reports = scoped_all_reports
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
    mood: Optional[str] = None
    health_notes: Optional[str] = None
    breakfast: bool = False
    snack: bool = False
    milk: bool = False
    lunch: bool = False
    breakfast_time: Optional[str] = None
    snack_time: Optional[str] = None
    milk_time: Optional[str] = None
    lunch_time: Optional[str] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    nap_duration_minutes: Optional[int] = Field(default=None, ge=0)
    bathroom_count: Optional[int] = Field(default=None, ge=0)
    diaper_wet: Optional[bool] = None
    diaper_soiled: Optional[bool] = None
    activities: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("arrival_time", "leave_time", "nap_start", "nap_end", "breakfast_time", "snack_time", "milk_time", "lunch_time")
    @classmethod
    def validate_time_format(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("time must use HH:MM format (24-hour)")
        return value


@router.get("/daily-reports/{report_id}")
def get_daily_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    from api.daily_reports_routes import _authorize_supervisor_report_access
    _authorize_supervisor_report_access(db, current_user, report)
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
    from api.daily_reports_routes import _authorize_supervisor_report_access
    _authorize_supervisor_report_access(db, current_user, report)
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
    try:
        target_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must use ISO format (YYYY-MM-DD)")

    # Reuse the canonical report gate so this compatibility route cannot bypass
    # profile completeness, workday, active-enrollment, or dated assignment rules.
    from api.daily_reports_routes import _authorize_report_for_child
    enrollment = _authorize_report_for_child(
        db,
        current_user,
        body.child_id,
        target_date,
        require_no_existing_report=False,
    )

    if target_date > _today():
        raise HTTPException(status_code=400, detail="Cannot create reports for future dates")

    # Reject duplicate report for same child + date unless caller explicitly
    # requests an overwrite. Overwrite updates the existing row rather than
    # creating a second report for the same child/day.
    existing = db.query(DailyReport).filter(
        DailyReport.child_id == body.child_id,
        DailyReport.date == target_date,
    ).first()
    if existing:
        from api.daily_reports_routes import _authorize_supervisor_report_access
        _authorize_supervisor_report_access(db, current_user, existing)
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
    now = datetime.now(_JORDAN_TZ)
    provided_fields = getattr(body, "model_fields_set", set())

    if existing and force:
        # Prevent overwriting reports that have already been approved or shared with parent
        if existing.status not in (DailyReportStatus.DRAFT, DailyReportStatus.REJECTED, DailyReportStatus.RETURNED):
            raise HTTPException(
                status_code=403,
                detail="Only draft or returned reports can be edited"
            )
        report = existing
        report.status = target_status
        report.submitted_by = current_user.id
        report.submitted_at = now if target_status == DailyReportStatus.SUBMITTED else None
        if "arrival_time" in provided_fields and body.arrival_time is not None:
            report.arrival_time = body.arrival_time
        if "leave_time" in provided_fields:
            report.leave_time = body.leave_time
        if "mood" in provided_fields:
            report.mood = body.mood
        if "health_notes" in provided_fields:
            report.health_notes = body.health_notes
        if "breakfast" in provided_fields:
            report.breakfast = body.breakfast
        if "snack" in provided_fields:
            report.snack = body.snack
        if "milk" in provided_fields:
            report.milk = body.milk
        if "lunch" in provided_fields:
            report.lunch = body.lunch
        if "breakfast_time" in provided_fields:
            report.breakfast_time = body.breakfast_time
        if "snack_time" in provided_fields:
            report.snack_time = body.snack_time
        if "milk_time" in provided_fields:
            report.milk_time = body.milk_time
        if "lunch_time" in provided_fields:
            report.lunch_time = body.lunch_time
        if "nap_start" in provided_fields:
            report.nap_start = body.nap_start
        if "nap_end" in provided_fields:
            report.nap_end = body.nap_end
        if "nap_duration_minutes" in provided_fields:
            report.nap_duration_minutes = body.nap_duration_minutes
        if "bathroom_count" in provided_fields:
            report.bathroom_count = body.bathroom_count
        if "diaper_wet" in provided_fields:
            report.diaper_wet = body.diaper_wet
        if "diaper_soiled" in provided_fields:
            report.diaper_soiled = body.diaper_soiled
        if "activities" in provided_fields:
            report.activities = body.activities
        if "notes" in provided_fields:
            report.notes = body.notes
        db.add(AuditLog(
            user_id=current_user.id,
            action=AuditAction.DAILY_REPORT_FORCE_UPDATED,
            entity_type="daily_report",
            entity_id=report.id,
            details=f"Supervisor overwrote daily report for child {body.child_id} dated {body.date} as {target_status.value}",
        ))
    else:
        if not body.arrival_time:
            raise HTTPException(status_code=422, detail="arrival_time is required when creating a daily report")
        report = DailyReport(
            child_id=body.child_id,
            class_id=enrollment.class_id,
            date=target_date,
            status=target_status,
            submitted_by=current_user.id,
            submitted_at=now if target_status == DailyReportStatus.SUBMITTED else None,
            arrival_time=body.arrival_time,
            leave_time=body.leave_time,
            mood=body.mood,
            health_notes=body.health_notes,
            breakfast=body.breakfast,
            snack=body.snack,
            milk=body.milk,
            lunch=body.lunch,
            breakfast_time=body.breakfast_time,
            snack_time=body.snack_time,
            milk_time=body.milk_time,
            lunch_time=body.lunch_time,
            nap_start=body.nap_start,
            nap_end=body.nap_end,
            nap_duration_minutes=body.nap_duration_minutes,
            bathroom_count=body.bathroom_count,
            diaper_wet=body.diaper_wet,
            diaper_soiled=body.diaper_soiled,
            activities=body.activities,
            notes=body.notes,
            kindergarten_id=enrollment.kindergarten_id,
            created_at=now,
        )
        db.add(report)
        db.flush()
        db.add(AuditLog(
            user_id=current_user.id,
            action=AuditAction.DAILY_REPORT_CREATED,
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
    mood: Optional[str] = None
    health_notes: Optional[str] = None
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    breakfast_time: Optional[str] = None
    snack_time: Optional[str] = None
    milk_time: Optional[str] = None
    lunch_time: Optional[str] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    nap_duration_minutes: Optional[int] = Field(default=None, ge=0)
    bathroom_count: Optional[int] = Field(default=None, ge=0)
    diaper_wet: Optional[bool] = None
    diaper_soiled: Optional[bool] = None
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
    from api.daily_reports_routes import _authorize_supervisor_report_access
    _authorize_supervisor_report_access(db, current_user, report)

    if not report.is_editable_by_supervisor():
        raise HTTPException(status_code=403, detail="Only draft or returned reports can be edited.")

    now = datetime.now(_JORDAN_TZ)
    for field in ("arrival_time", "leave_time", "mood", "health_notes", "breakfast", "snack", "milk",
                  "lunch", "breakfast_time", "snack_time", "milk_time", "lunch_time", "nap_start", "nap_end",
                  "nap_duration_minutes", "bathroom_count", "diaper_wet", "diaper_soiled", "activities", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(report, field, val)

    if body.status:
        if body.status not in ("DRAFT", "SUBMITTED"):
            raise HTTPException(status_code=400, detail="Supervisor can only save as DRAFT or SUBMITTED.")
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
    from api.daily_reports_routes import _authorize_supervisor_report_access
    _authorize_supervisor_report_access(db, current_user, report)
    if not report.can_submit_to_manager():
        raise HTTPException(status_code=403, detail="Only draft or returned reports can be submitted.")
    report.status = DailyReportStatus.SUBMITTED
    report.submitted_at = datetime.now(_JORDAN_TZ)
    db.add(AuditLog(
        user_id=current_user.id,
        action=AuditAction.DAILY_REPORT_SUBMITTED,
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
    parent_informed: bool = True
    parent_not_informed_reason: Optional[str] = None
    followup_required_flag: bool = False


@router.post("/safety-incidents", status_code=201)
def create_safety_incident(
    body: IncidentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_supervisor),
):
    enrollment = _get_supervisor_child_enrollment(db, current_user.id, body.child_id)
    if not enrollment:
        raise HTTPException(status_code=403, detail="Child is not in your assigned class.")

    try:
        inc_type = IncidentType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid incident type: {body.type}")
    try:
        severity = SeverityLevel(body.severity_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid severity level: {body.severity_level}")

    if body.occurred_at:
        try:
            occurred_at = datetime.fromisoformat(body.occurred_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="occurred_at must use ISO-8601 format")
    else:
        occurred_at = datetime.now(_JORDAN_TZ)
    if occurred_at > datetime.now(_JORDAN_TZ):
        raise HTTPException(status_code=422, detail="occurred_at cannot be in the future")
    if not body.parent_informed and not (body.parent_not_informed_reason or "").strip():
        raise HTTPException(status_code=422, detail="Reason required when parent is not informed")

    incident = Incident(
        child_id=body.child_id,
        kindergarten_id=enrollment.kindergarten_id,
        class_id=enrollment.class_id,
        reported_by=current_user.id,
        type=inc_type,
        severity_level=severity,
        description=body.description,
        occurred_at=occurred_at,
        parent_informed=body.parent_informed,
        parent_not_informed_reason=body.parent_not_informed_reason,
        followup_required_flag=body.followup_required_flag,
    )
    if incident.followup_required_flag:
        incident.followup_sla_deadline = datetime.now(_JORDAN_TZ) + timedelta(hours=48)
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return {"id": incident.id, "status": "created"}


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
        upload_dir = os.path.join(settings.BASE_DIR, settings.STATIC_DIR, "uploads", "incidents")
        os.makedirs(upload_dir, exist_ok=True)
        file_name = f"incident_{incident_id}_{uuid.uuid4().hex}{ext}"
        out_path = os.path.join(upload_dir, file_name)
        raw = attachment.file.read()
        if len(raw) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Attachment too large. Max {settings.MAX_UPLOAD_SIZE_MB} MB.")
        with open(out_path, "wb") as f:
            f.write(raw)
        attachment_url = f"/{settings.STATIC_DIR}/uploads/incidents/{file_name}"

    incident.closed_at = datetime.now(_JORDAN_TZ)
    incident.closed_by = current_user.id
    if resolution_notes:
        incident.resolution_notes = resolution_notes
    if attachment_url:
        incident.attachment_url = attachment_url

    db.add(
        AuditLog(
            user_id=current_user.id,
            action=AuditAction.INCIDENT_RESOLVED,
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

    sender_ids = {m.sender_id for m in messages}
    sender_by_id = {}
    if sender_ids:
        sender_by_id = {
            u.id: u for u in db.query(User).filter(User.id.in_(sender_ids)).all()
        }

    result = []
    for m in messages:
        sender = sender_by_id.get(m.sender_id)
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
    try:
        deleted_state_subq = db.query(MessageUserState.message_id).filter(
            MessageUserState.user_id == current_user.id,
            MessageUserState.deleted_at.isnot(None),
        )
        unread_count = (
            db.query(func.count(Message.id))
            .filter(
                Message.recipient_id == current_user.id,
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
    except OperationalError:
        unread_count = (
            db.query(func.count(Message.id))
            .filter(
                Message.recipient_id == current_user.id,
                Message.is_read.is_(False),
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
    now = datetime.now(_JORDAN_TZ)
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
        uploads_dir = os.path.join(settings.BASE_DIR, settings.STATIC_DIR, "uploads", "messages")
        os.makedirs(uploads_dir, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(uploads_dir, safe_name)
        web_url = f"/{settings.STATIC_DIR}/uploads/messages/{safe_name}"
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
                url=web_url,
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
        state.deleted_at = datetime.now(_JORDAN_TZ)
    except OperationalError:
        msg.is_read = True  # fallback: mark as read when soft-delete table is unavailable
    db.add(
        AuditLog(
            user_id=current_user.id,
            action=AuditAction.MESSAGE_DELETED,
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
    today = _today()
    try:
        date_from = date.fromisoformat(from_date) if from_date else today - timedelta(days=6)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid from_date format.")
    try:
        date_to = date.fromisoformat(to_date) if to_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid to_date format.")

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
        if report.submitted_at and report.submitted_at.astimezone(KSA_TZ).date() <= report.date
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
            if report.submitted_at and report.submitted_at.astimezone(KSA_TZ).date() <= report.date
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
            SupervisorAssignment.start_date <= _today(),
            or_(SupervisorAssignment.end_date.is_(None), SupervisorAssignment.end_date >= _today()),
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
        "generated_at": datetime.now(_JORDAN_TZ).isoformat(),
    }

    _sync_totp_secret(current_user, encrypted_secret)
    current_user.mfa_enabled = True
    current_user.mfa_enrolled_at = datetime.now(_JORDAN_TZ)
    _write_notification_preferences(current_user, prefs)

    otpauth_uri = provisioning_uri(secret, current_user.email or current_user.username)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action=AuditAction.MFA_ENABLED,
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
            action=AuditAction.MFA_DISABLED,
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
    # UTC on purpose — see the note in me_endpoints.change_my_password. Read
    # only as a duration anchor by auth.requires_password_change, which treats
    # naive values (every SQLite read) as UTC.
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

    uploads_dir = os.path.join(settings.BASE_DIR, settings.STATIC_DIR, "uploads", "profiles")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = _IMAGE_EXT[ct]
    file_name = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    out_path = os.path.join(uploads_dir, file_name)
    web_url = f"/{settings.STATIC_DIR}/uploads/profiles/{file_name}"
    with open(out_path, "wb") as f:
        f.write(file.file.read())

    current_user.address = f"profile_image:{web_url}"
    db.commit()
    return {"status": "ok", "picture_url": web_url}


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


# --- Migrated from api/supervisor.py ---
from typing import List, Optional
from fastapi import Body
from pydantic import BaseModel
class ObservationRecordRequest(BaseModel):
    child_id: int
    domain: str
    observation_text: str
    mastery_level: Optional[str] = None
    observed_at: Optional[str] = None

class SupervisorAssignmentRequest(BaseModel):
    supervisor_id: int
    class_id: int
    start_date: date
    is_primary: bool = False

@router.post("/assign", status_code=status.HTTP_201_CREATED)
def assign_supervisor(
    assignment_data: Optional[SupervisorAssignmentRequest] = Body(None),
    supervisor_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    is_primary: bool = Query(False),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign supervisor to class (Manager only). Accepts either JSON body or query params for compatibility."""
    validators.validate_manager_role(current_user)

    # Build assignment_data from query params if body not provided
    if assignment_data is None:
        if supervisor_id is None or class_id is None or start_date is None:
            raise HTTPException(status_code=422, detail="Missing required assignment parameters")
        assignment_data = SupervisorAssignmentRequest(
            supervisor_id=supervisor_id,
            class_id=class_id,
            start_date=start_date,
            is_primary=is_primary
        )

    # Verify class exists
    class_obj = db.query(models.Class).filter(
        models.Class.id == assignment_data.class_id,
        models.Class.deleted_at.is_(None),
        models.Class.is_active.is_(True),
    ).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")
    
    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)
    
    # Verify supervisor exists and has correct role
    supervisor = db.query(models.User).filter(
        models.User.id == assignment_data.supervisor_id,
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.kindergarten_id == current_user.kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE,
        models.User.deleted_at.is_(None),
    ).with_for_update().first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    # Check if supervisor is already assigned to any class on this date
    new_start = assignment_data.start_date
    existing = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == assignment_data.supervisor_id,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= new_start),
        models.SupervisorAssignment.deleted_at.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Supervisor already assigned to a class on this date")
    
    assignment = models.SupervisorAssignment(
        class_id=assignment_data.class_id,
        supervisor_id=assignment_data.supervisor_id,
        start_date=new_start,
        is_primary=assignment_data.is_primary
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return {
        "id": assignment.id,
        "supervisor_id": assignment.supervisor_id,
        "class_id": assignment.class_id,
        "is_primary": assignment.is_primary,
        "start_date": assignment.start_date.isoformat()
    }

@router.post("/assign-replacement", status_code=status.HTTP_201_CREATED)
def assign_replacement_supervisor(
    class_id: int = Query(...),
    replacement_supervisor_id: int = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    reason: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a replacement supervisor for a class (Manager only)"""
    validators.validate_manager_role(current_user)

    # Verify class exists
    class_obj = db.query(models.Class).filter(
        models.Class.id == class_id,
        models.Class.deleted_at.is_(None),
        models.Class.is_active.is_(True),
    ).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    validators.validate_kindergarten_scope(current_user, class_obj.kindergarten_id)

    # Verify replacement supervisor exists and has correct role
    supervisor = db.query(models.User).filter(
        models.User.id == replacement_supervisor_id,
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.kindergarten_id == current_user.kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE,
        models.User.deleted_at.is_(None),
    ).with_for_update().first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Replacement supervisor not found")

    replacement_start = start_date
    replacement_end = end_date
    if replacement_end < replacement_start:
        raise HTTPException(status_code=400, detail="Replacement end date must be on or after start date")
    overlap = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == replacement_supervisor_id,
        models.SupervisorAssignment.deleted_at.is_(None),
        models.SupervisorAssignment.start_date <= replacement_end,
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= replacement_start,
        ),
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="Supervisor already assigned during this date range")

    assignment = models.SupervisorAssignment(
        class_id=class_id,
        supervisor_id=replacement_supervisor_id,
        start_date=replacement_start,
        end_date=replacement_end
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "id": assignment.id,
        "replacement_supervisor_id": assignment.supervisor_id,
        "class_id": assignment.class_id,
        "start_date": assignment.start_date.isoformat(),
        "end_date": assignment.end_date.isoformat() if assignment.end_date else None
    }

@router.post("/observations", status_code=status.HTTP_201_CREATED)
def create_observation(
    observation_data: ObservationRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new observation (Supervisor/Manager/Admin only)"""
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can create observations")
    
    # Verify child exists
    child = db.query(models.Child).filter(
        models.Child.id == observation_data.child_id,
        models.Child.deleted_at.is_(None),
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    enrollment = (
        db.query(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status.in_(tuple(models.ACTIVE_ENROLLMENT_STATUSES)),
            models.EnrollmentApplication.deleted_at.is_(None),
        )
        .order_by(models.EnrollmentApplication.updated_at.desc(), models.EnrollmentApplication.id.desc())
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=400, detail="Child has no active enrollment")

    validators.validate_kindergarten_scope(current_user, enrollment.kindergarten_id)
    if current_user.role == models.UserRole.SUPERVISOR and not _get_supervisor_child_enrollment(
        db, current_user.id, child.id
    ):
        raise HTTPException(status_code=403, detail="Not assigned to child's class")
    
    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    # Parse observed_at from ISO string if provided
    observed_at = datetime.now(_JORDAN_TZ)
    if hasattr(observation_data, 'observed_at') and observation_data.observed_at:
        try:
            observed_at = datetime.fromisoformat(observation_data.observed_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            logger.warning("INVALID_DATETIME observed_at=%r ignored — defaulting to now()", observation_data.observed_at)
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=observed_at
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value,
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }


@router.post("/observations/{observation_id}/photo")
def upload_observation_photo(
    observation_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in [models.UserRole.SUPERVISOR, models.UserRole.MANAGER, models.UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only staff can upload observation photo")

    observation = db.query(models.Observation).filter(models.Observation.id == observation_id).first()
    if not observation:
        raise HTTPException(status_code=404, detail="Observation not found")

    if current_user.role == models.UserRole.SUPERVISOR:
        enrollment = _get_supervisor_child_enrollment(db, current_user.id, observation.child_id)
        if not enrollment:
            raise HTTPException(status_code=403, detail="Not assigned to child's class")
    elif current_user.role == models.UserRole.MANAGER:
        # Managers are scoped to their own kindergarten
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == observation.child_id,
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
            models.EnrollmentApplication.deleted_at.is_(None),
        ).first()
        if not enrollment:
            raise HTTPException(status_code=403, detail="Observation not in your kindergarten scope")

    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_OBSERVATION_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only image uploads are allowed (png, jpeg, gif, webp)")

    upload_dir = os.path.join(settings.BASE_DIR, settings.STATIC_DIR, "uploads", "observations")
    os.makedirs(upload_dir, exist_ok=True)
    ext = _OBSERVATION_IMAGE_TYPE_TO_EXT[content_type]
    file_name = f"obs_{observation_id}_{uuid.uuid4().hex}{ext}"
    out_path = os.path.join(upload_dir, file_name)
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB} MB.")
    with open(out_path, "wb") as out:
        out.write(content)

    photo_url = f"/{settings.STATIC_DIR}/uploads/observations/{file_name}"
    observation.photo_url = photo_url
    db.commit()
    return {"status": "ok", "photo_url": photo_url}

@router.post("/observations/record", status_code=status.HTTP_201_CREATED)
def record_observation(
    observation_data: Optional[ObservationRecordRequest] = Body(None),
    child_id: Optional[int] = Query(None),
    domain: Optional[str] = Query(None),
    observation_text: Optional[str] = Query(None),
    mastery_level: Optional[str] = Query(None),
    observed_at: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record child observation (Supervisor only). Accepts either JSON body or query params for compatibility."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can record observations")

    # Build observation_data from query params if body not provided
    if observation_data is None:
        if child_id is None or domain is None or observation_text is None:
            raise HTTPException(status_code=422, detail="Missing required observation parameters")
        observation_data = ObservationRecordRequest(
            child_id=child_id,
            domain=domain,
            observation_text=observation_text,
            mastery_level=mastery_level,
            observed_at=observed_at
        )
    
    # Verify child exists
    child = db.query(models.Child).filter(
        models.Child.id == observation_data.child_id,
        models.Child.deleted_at.is_(None),
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify active enrollment and supervisor scope
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child.id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
    ).first()
    if not active_enrollment:
        raise HTTPException(status_code=400, detail="Child not active in any class")

    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)

    # Verify supervisor is assigned to the child's class
    today = datetime.now(_JORDAN_TZ).date()
    assignment = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        models.SupervisorAssignment.class_id == active_enrollment.class_id,
        models.SupervisorAssignment.deleted_at.is_(None),
        models.SupervisorAssignment.start_date <= today,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= today)
    ).first()
    if not assignment:
        raise HTTPException(status_code=403, detail="Not assigned to child's class")

    # Map domain string to enum (case-insensitive)
    domain_str = observation_data.domain.upper().replace("-", "_")
    domain_map = {
        "SOCIAL_EMOTIONAL": models.LearningDomain.SOCIAL_EMOTIONAL,
        "COGNITIVE": models.LearningDomain.COGNITIVE,
        "PHYSICAL": models.LearningDomain.PHYSICAL,
        "LANGUAGE": models.LearningDomain.LANGUAGE,
    }
    domain = domain_map.get(domain_str)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid domain")
    
    # Map mastery level if provided (case-insensitive)
    mastery = None
    if observation_data.mastery_level:
        mastery_str = observation_data.mastery_level.upper().replace("-", "_")
        mastery_map = {
            "NEEDS_SUPPORT": models.MasteryLevel.NEEDS_SUPPORT,
            "ON_TRACK": models.MasteryLevel.ON_TRACK,
            "EXCEEDS": models.MasteryLevel.EXCEEDS,
        }
        mastery = mastery_map.get(mastery_str)
    
    observation = models.Observation(
        child_id=observation_data.child_id,
        observed_by=current_user.id,
        domain=domain,
        observation_text=observation_data.observation_text,
        mastery_level=mastery,
        observed_at=datetime.now(_JORDAN_TZ)
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    
    return {
        "id": observation.id,
        "child_id": observation.child_id,
        "domain": observation.domain.value.lower(),
        "mastery_level": observation.mastery_level.value if observation.mastery_level else None,
        "observed_at": observation.observed_at.isoformat()
    }

@router.get("/children/detailed")
def get_supervisor_children(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Legacy detailed supervisor children listing retained on a non-canonical path."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")

    from supervisor_service import SupervisorService
    children = SupervisorService.get_supervisor_children(db, current_user)

    if not children:
        return {"children": []}

    today = datetime.now(_JORDAN_TZ).date()
    child_ids = [c.id for c in children]

    # Batch-fetch enrollments and attendance records — avoids 2N per-child queries
    enrollments_by_child = {
        e.child_id: e
        for e in db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id.in_(child_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
        ).all()
    }
    attendance_by_child = {
        a.child_id: a
        for a in db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date == today,
        ).all()
    }

    results = []
    for child in children:
        enrollment = enrollments_by_child.get(child.id)
        attendance = attendance_by_child.get(child.id)

        status = "absent"
        check_in_time = None
        check_out_time = None

        if attendance:
            status = "present" if not attendance.check_out_at else "checked_out"
            check_in_time = attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None
            check_out_time = attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None

        results.append({
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value,
            # date_of_birth is load-bearing, not decorative. Every client that
            # lists children for a supervisor filters the list through
            # ChildAgeValidator.isEligible(child.date_of_birth) as an age-policy
            # safety net; omitting the field made that predicate falsy for every
            # row, so the daily-report form's child picker rendered "no children
            # available" and a supervisor could not file a report at all.
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "photo_url": child.photo_url,
            "class_id": enrollment.class_id if enrollment else None,
            "class_name": (enrollment.class_.name_ar if enrollment and enrollment.class_ else None),
            "kindergarten_id": enrollment.kindergarten_id if enrollment else None,
            "kindergarten_name": (
                enrollment.kindergarten.name_ar if enrollment and enrollment.kindergarten else None
            ),
            "parent": {
                "id": child.parent.id if child.parent else None,
                "first_name": child.parent.first_name if child.parent else None,
                "last_name": child.parent.last_name if child.parent else None,
                "phone_number": child.parent.phone_number if child.parent else None,
            },
            "attendance_status": status,
            "check_in_time": check_in_time,
            "check_out_time": check_out_time,
            "name": f"{child.first_name} {child.last_name}",
        })

    return {"children": results}

@router.get("/children/{child_id}")
def get_supervisor_child_details(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access this endpoint")

    enrollment = _get_supervisor_child_enrollment(db, current_user.id, child_id)
    if not enrollment:
        raise HTTPException(status_code=403, detail="Forbidden")

    child = db.query(models.Child).filter(
        models.Child.id == child_id,
        models.Child.deleted_at.is_(None),
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    reports = db.query(models.DailyReport).filter(
        models.DailyReport.child_id == child_id
    ).order_by(models.DailyReport.date.desc()).limit(30).all()

    return {
        "child": {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "full_name": f"{child.first_name} {child.last_name}".strip(),
            "date_of_birth": child.date_of_birth.isoformat() if child.date_of_birth else None,
            "gender": child.gender.value if child.gender else None,
            "medical_notes": child.medical_notes or child.health_notes,
            "class": {
                "id": enrollment.class_id,
                "name": enrollment.class_.name_ar if enrollment.class_ else None,
            },
            "kindergarten": {
                "id": enrollment.kindergarten_id,
                "name": enrollment.kindergarten.name_ar if enrollment.kindergarten else None,
            },
            "parent": {
                "id": child.parent.id if child.parent else None,
                "first_name": child.parent.first_name if child.parent else None,
                "last_name": child.parent.last_name if child.parent else None,
                "phone_number": child.parent.phone_number if child.parent else None,
            },
        },
        # Serialised from the columns DailyReport actually has. This block used
        # to read report.meals / .sleep / .behavior / .general_notes, none of
        # which exist on the model, so every call to this endpoint raised
        # AttributeError and answered 500 — for the supervisor's own children,
        # not just out-of-scope ones. Meals are four separate booleans and sleep
        # is a start/end pair, so both are reported the way they are stored
        # rather than invented as single fields.
        "daily_reports": [
            {
                "id": report.id,
                "reportDate": report.date.isoformat(),
                "arrivalTime": report.arrival_time,
                "leaveTime": report.leave_time,
                "mood": report.mood,
                "meals": {
                    "breakfast": report.breakfast,
                    "snack": report.snack,
                    "milk": report.milk,
                    "lunch": report.lunch,
                },
                "sleep": {
                    "start": report.nap_start,
                    "end": report.nap_end,
                    "minutes": report.nap_duration_minutes,
                },
                "activities": report.activities,
                "healthNotes": report.health_notes,
                "generalNotes": report.notes,
                "status": report.status.value,
            }
            for report in reports
        ],
    }

# NOTE: POST /api/supervisor/children/{child_id}/daily-reports was removed.
#
# It was a second, hand-written report-creation path that had never worked:
# it constructed DailyReport with class_id, supervisor_id, meals, sleep,
# behavior and general_notes, none of which are columns on the model, so
# every call raised TypeError and answered 500. Its request schema assumed a
# different shape too (meals and sleep as free text, where the model stores
# four meal booleans and a nap start/end pair), so there is no faithful way
# to "fix" it without inventing data.
#
# Nothing referenced it — no template, no JS, no test — and it could never
# have been used successfully. The supported paths are
# POST /api/daily-reports/create (one child) and POST /api/daily-reports/batch
# (a whole class), which share one set of authorisation gates in
# api/daily_reports_routes.py::_authorize_report_for_child.

@router.get("/children/{child_id}/daily-reports")
def list_supervisor_child_daily_reports(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can view daily reports")

    enrollment = _get_supervisor_child_enrollment(db, current_user.id, child_id)
    if not enrollment:
        raise HTTPException(status_code=403, detail="Forbidden")

    reports = db.query(models.DailyReport).filter(
        models.DailyReport.child_id == child_id
    ).order_by(models.DailyReport.date.desc()).all()
    from api.daily_reports_routes import _authorize_supervisor_report_access
    authorized_reports = []
    for report in reports:
        try:
            _authorize_supervisor_report_access(db, current_user, report)
        except HTTPException:
            continue
        authorized_reports.append(report)

    return {
        "reports": [
            {
                "id": report.id,
                "reportDate": report.date.isoformat(),
                "kindergartenId": report.kindergarten_id,
                "breakfast": report.breakfast,
                "snack": report.snack,
                "milk": report.milk,
                "lunch": report.lunch,
                "nap_start": report.nap_start,
                "nap_end": report.nap_end,
                "nap_duration_minutes": report.nap_duration_minutes,
                "activities": report.activities,
                "mood": report.mood,
                "healthNotes": report.health_notes,
                "generalNotes": report.notes,
                "status": report.status.value,
            }
            for report in authorized_reports
        ]
    }

@router.get("/dashboard")
def get_supervisor_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get supervisor dashboard data"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can access dashboard")
    
    # Get supervisor's classes
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == current_user.id,
        models.SupervisorAssignment.deleted_at.is_(None),
        models.SupervisorAssignment.start_date <= datetime.now(_JORDAN_TZ).date(),
        or_(
            models.SupervisorAssignment.end_date.is_(None),
            models.SupervisorAssignment.end_date >= datetime.now(_JORDAN_TZ).date()
        )
    ).all()
    
    class_ids = [a.class_id for a in assignments]
    
    # Count children in assigned classes
    total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
    ).scalar() or 0
    
    # Count today's attendance
    today = datetime.now(_JORDAN_TZ).date()
    today_attendance = db.query(func.count(models.AttendanceLog.id)).join(
        models.EnrollmentApplication,
        models.AttendanceLog.child_id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
        models.AttendanceLog.date == today
    ).scalar() or 0
    
    # Pending daily reports — drafts this supervisor has started but not submitted.
    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.submitted_by == current_user.id,
        models.DailyReport.status == models.DailyReportStatus.DRAFT
    ).scalar() or 0

    # How much of today's class is actually reported.
    #
    # pending_reports counts DRAFTS, so it reads 0 both when the day's work is
    # finished and when it has not been started — and the dashboard rendered the
    # second case as "all reports are complete" while nobody had filed anything.
    # This counts children in the assigned classes who have a report for today,
    # which is the number a supervisor is actually asking about.
    reports_today = db.query(func.count(func.distinct(models.DailyReport.child_id))).join(
        models.EnrollmentApplication,
        models.DailyReport.child_id == models.EnrollmentApplication.child_id,
    ).filter(
        models.EnrollmentApplication.class_id.in_(class_ids),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
        models.DailyReport.date == today,
    ).scalar() or 0
    
    # Build class details list — batch fetch to avoid N+1
    classes_by_id = {
        c.id: c
        for c in db.query(models.Class).filter(models.Class.id.in_(class_ids)).all()
    } if class_ids else {}
    classes_detail = []
    for a in assignments:
        class_obj = classes_by_id.get(a.class_id)
        if class_obj:
            classes_detail.append({
                "id": class_obj.id,
                "name_ar": class_obj.name_ar,
                "name_en": class_obj.name_en,
                "kindergarten_id": class_obj.kindergarten_id,
                "is_primary": a.is_primary,
            })

    return {
        "supervisor_id": current_user.id,
        "classes": classes_detail,
        "attendance_summary": {"today": today_attendance},
        "total_children": total_children,
        "pending_reports": pending_reports,
        "reports_today": reports_today,
        "reports_remaining_today": max(total_children - reports_today, 0),
        "date": today.isoformat()
    }
