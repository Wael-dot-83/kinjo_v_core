"""
Absence Request endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timedelta, timezone, UTC

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Optional
from pydantic import BaseModel, field_validator

import models
from database import get_db
from dependencies import get_current_user
from audit_actions import AuditAction

router = APIRouter(tags=["Absence Requests"])

# Approving an absence writes one attendance row per day in the span, so the span is
# not just a validation nicety — it is the loop bound of a write path a parent gets to
# choose. Unbounded, `end_date=9999-12-31` is accepted (2,912,246 days) and the
# manager who approves it detonates ~2.9M SELECT+INSERT pairs on a sync worker.
# 366 matches MAX_CUSTOM_PERIOD_DAYS (admin_endpoints.py), which already bounds the
# read windows; a kindergarten absence longer than a year is not a real request.
MAX_ABSENCE_SPAN_DAYS = 366


def _require_scoped_manager(current_user: models.User) -> None:
    """Absence decisions are a manager-only operation on their own KG.

    Admins are deliberately excluded: RBAC policy blocks Admin from
    operational entry (approving creates attendance records). A manager
    without a kindergarten has no scope and must not fall through to an
    unscoped query.
    """
    if current_user.role != models.UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Only managers can decide absence requests")
    if current_user.kindergarten_id is None:
        raise HTTPException(status_code=403, detail="No kindergarten is associated with this manager account")


class CreateAbsenceRequest(BaseModel):
    child_id: int
    start_date: date
    end_date: date
    reason: str

    @field_validator("start_date")
    @classmethod
    def start_must_be_future(cls, v):
        if v <= datetime.now(_JORDAN_TZ).date():
            raise ValueError("start_date must be in the future")
        return v

    @field_validator("end_date")
    @classmethod
    def end_not_before_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must not be before start_date")
        if start and (v - start).days + 1 > MAX_ABSENCE_SPAN_DAYS:
            raise ValueError(
                f"absence span must not exceed {MAX_ABSENCE_SPAN_DAYS} days "
                f"(requested {(v - start).days + 1})"
            )
        return v


class DecisionRequest(BaseModel):
    decision_note: Optional[str] = None


class CorrectionRequest(BaseModel):
    new_status: str
    notes: Optional[str] = None


def _serialize_request(req: models.AbsenceRequest, include_child_name: bool = False):
    data = {
        "id": req.id,
        "child_id": req.child_id,
        "start_date": req.start_date.isoformat(),
        "end_date": req.end_date.isoformat(),
        "reason": req.reason,
        "status": req.status.value if req.status else None,
        "decision_note": req.decision_note,
    }
    if include_child_name and req.child:
        data["child_name"] = f"{req.child.first_name} {req.child.last_name}"
    return data


# ── POST /absence-requests (Parent only) ─────────────────────────────

@router.post("/absence-requests", status_code=201)
def create_absence_request(
    payload: CreateAbsenceRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only parents can create absence requests")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile:
        raise HTTPException(status_code=400, detail="Parent profile not found")

    child = db.query(models.Child).filter(
        models.Child.id == payload.child_id,
        models.Child.parent_id == parent_profile.id,
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child.id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=400, detail="No active enrollment for this child")

    # Overlap check
    overlap = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.child_id == child.id,
        models.AbsenceRequest.status.in_([
            models.AbsenceRequestStatus.SUBMITTED,
            models.AbsenceRequestStatus.APPROVED,
        ]),
        models.AbsenceRequest.start_date <= payload.end_date,
        models.AbsenceRequest.end_date >= payload.start_date,
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="Overlapping absence request exists")

    absence = models.AbsenceRequest(
        parent_id=parent_profile.id,
        child_id=child.id,
        kindergarten_id=enrollment.kindergarten_id,
        class_id=enrollment.class_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status=models.AbsenceRequestStatus.SUBMITTED,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)

    return {"id": absence.id, "status": absence.status.value}


# ── GET /absence-requests ────────────────────────────────────────────

@router.get("/absence-requests")
def list_absence_requests(
    # Aliased: a bare `status` parameter would shadow the imported `fastapi.status`
    # module inside this function.
    status_filter: Optional[models.AbsenceRequestStatus] = Query(
        None, alias="status", description="Filter by request status; omit for all requests"
    ),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return []
        query = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.parent_id == parent_profile.id
        )
        if status_filter is not None:
            query = query.filter(models.AbsenceRequest.status == status_filter)
        requests = query.order_by(models.AbsenceRequest.created_at.desc()).all()
        return [_serialize_request(r) for r in requests]
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id is None:
            raise HTTPException(status_code=403, detail="No kindergarten is associated with this manager account")
        query = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.kindergarten_id == current_user.kindergarten_id
        )
    elif current_user.role == models.UserRole.ADMIN:
        query = db.query(models.AbsenceRequest)
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view absence requests")

    if status_filter is not None:
        query = query.filter(models.AbsenceRequest.status == status_filter)
    requests = query.order_by(models.AbsenceRequest.created_at.desc()).all()
    return [_serialize_request(r, include_child_name=True) for r in requests]


# ── GET /absence-requests/{id} ──────────────────────────────────────

@router.get("/absence-requests/{request_id}")
def get_absence_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        absence = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.id == request_id
        ).first()
        if not absence:
            raise HTTPException(status_code=404, detail="Absence request not found")
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile or absence.parent_id != parent_profile.id:
            raise HTTPException(status_code=404, detail="Absence request not found")
    elif current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id is None:
            raise HTTPException(status_code=403, detail="No kindergarten is associated with this manager account")
        absence = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.id == request_id,
            models.AbsenceRequest.kindergarten_id == current_user.kindergarten_id,
        ).first()
        if not absence:
            raise HTTPException(status_code=404, detail="Absence request not found")
    elif current_user.role == models.UserRole.ADMIN:
        absence = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.id == request_id
        ).first()
        if not absence:
            raise HTTPException(status_code=404, detail="Absence request not found")
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view absence requests")

    data = _serialize_request(absence, include_child_name=True)
    return data


# ── POST /absence-requests/{id}/cancel (Parent) ─────────────────────

@router.post("/absence-requests/{request_id}/cancel")
def cancel_absence_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only parents can cancel")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if parent_profile is None:
        raise HTTPException(status_code=404, detail="Not found")

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
        models.AbsenceRequest.parent_id == parent_profile.id,
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Not found")
    if absence.status != models.AbsenceRequestStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail="Only submitted requests can be cancelled",
        )

    transitioned = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == absence.id,
        models.AbsenceRequest.parent_id == parent_profile.id,
        models.AbsenceRequest.status == models.AbsenceRequestStatus.SUBMITTED,
    ).update(
        {models.AbsenceRequest.status: models.AbsenceRequestStatus.CANCELLED},
        synchronize_session=False,
    )
    if transitioned != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request was already decided")
    db.commit()
    db.refresh(absence)
    return {"id": absence.id, "status": absence.status.value}


# ── POST /absence-requests/{id}/approve (Manager) ───────────────────

@router.post("/absence-requests/{request_id}/approve")
def approve_absence_request(
    request_id: int,
    payload: DecisionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_scoped_manager(current_user)

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Not found")

    # Cross-KG check
    if absence.kindergarten_id != current_user.kindergarten_id:
        raise HTTPException(status_code=403, detail="Not in your kindergarten scope")

    if absence.status == models.AbsenceRequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Already approved")
    if absence.status != models.AbsenceRequestStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted requests can be approved")

    conflicting_attendance = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == absence.child_id,
        models.AttendanceLog.date >= absence.start_date,
        models.AttendanceLog.date <= absence.end_date,
        models.AttendanceLog.status != models.AttendanceStatus.ABSENT,
    ).first()
    if conflicting_attendance is not None:
        raise HTTPException(
            status_code=409,
            detail="Existing attendance conflicts with this absence request",
        )

    decided_at = datetime.now(_JORDAN_TZ)
    transitioned = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == absence.id,
        models.AbsenceRequest.kindergarten_id == current_user.kindergarten_id,
        models.AbsenceRequest.status == models.AbsenceRequestStatus.SUBMITTED,
    ).update(
        {
            models.AbsenceRequest.status: models.AbsenceRequestStatus.APPROVED,
            models.AbsenceRequest.manager_id: current_user.id,
            models.AbsenceRequest.decision_note: payload.decision_note,
            models.AbsenceRequest.decided_at: decided_at,
        },
        synchronize_session=False,
    )
    if transitioned != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request was already decided")
    db.add(models.AuditLog(
        user_id=current_user.id,
        action=AuditAction.ABSENCE_REQUEST_APPROVED,
        entity_type="absence_request",
        entity_id=absence.id,
        details=f"Manager approved absence request {absence.id} for child {absence.child_id} ({absence.start_date}..{absence.end_date})",
    ))
    db.flush()

    # Create attendance records for each day in range
    # The loop below is the thing the span bound exists to protect, so check it here
    # too, against the STORED row. Both creation routes are bounded now, but a row
    # persisted before that bound shipped — or written by a migration or a fixture —
    # would still walk ~2.9M days one SELECT+INSERT at a time. Guarding only the doors
    # protects only rows created after the doors were fitted.
    stored_span = (absence.end_date - absence.start_date).days + 1
    if stored_span > MAX_ABSENCE_SPAN_DAYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"absence spans {stored_span} days, which exceeds the "
                f"{MAX_ABSENCE_SPAN_DAYS}-day limit; it cannot be approved. Reject it "
                "and ask for a shorter request."
            ),
        )

    records_created = 0
    current_date = absence.start_date
    while current_date <= absence.end_date:
        existing = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.child_id == absence.child_id,
            models.AttendanceLog.date == current_date,
        ).first()
        if not existing:
            att = models.AttendanceLog(
                child_id=absence.child_id,
                class_id=absence.class_id,
                date=current_date,
                status=models.AttendanceStatus.ABSENT,
                recorded_by=current_user.id,
            )
            db.add(att)
            records_created += 1
        current_date += timedelta(days=1)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Attendance changed while the request was being approved",
        ) from exc
    db.refresh(absence)

    return {
        "id": absence.id,
        "status": absence.status.value,
        "attendance_records_created": records_created,
    }


# ── POST /absence-requests/{id}/reject (Manager) ────────────────────

@router.post("/absence-requests/{request_id}/reject")
def reject_absence_request(
    request_id: int,
    payload: DecisionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_scoped_manager(current_user)

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Not found")

    # Cross-KG check
    if absence.kindergarten_id != current_user.kindergarten_id:
        raise HTTPException(status_code=403, detail="Not in your kindergarten scope")

    if absence.status != models.AbsenceRequestStatus.SUBMITTED:
        # Rejecting an APPROVED request would strand the attendance
        # records approval created; only pending requests are decidable.
        raise HTTPException(status_code=400, detail="Only submitted requests can be rejected")

    transitioned = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == absence.id,
        models.AbsenceRequest.kindergarten_id == current_user.kindergarten_id,
        models.AbsenceRequest.status == models.AbsenceRequestStatus.SUBMITTED,
    ).update(
        {
            models.AbsenceRequest.status: models.AbsenceRequestStatus.REJECTED,
            models.AbsenceRequest.manager_id: current_user.id,
            models.AbsenceRequest.decision_note: payload.decision_note,
            models.AbsenceRequest.decided_at: datetime.now(_JORDAN_TZ),
        },
        synchronize_session=False,
    )
    if transitioned != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request was already decided")
    db.add(models.AuditLog(
        user_id=current_user.id,
        action=AuditAction.ABSENCE_REQUEST_REJECTED,
        entity_type="absence_request",
        entity_id=absence.id,
        details=f"Manager rejected absence request {absence.id} for child {absence.child_id}",
    ))
    db.commit()
    db.refresh(absence)

    return {"id": absence.id, "status": absence.status.value}
