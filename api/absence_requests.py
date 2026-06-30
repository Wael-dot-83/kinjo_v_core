"""
Absence Request endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import date, datetime, timedelta, timezone, UTC

_JORDAN_TZ = timezone(timedelta(hours=3))
from typing import Optional
from pydantic import BaseModel, field_validator

import models
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Absence Requests"])


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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile:
            return []
        requests = db.query(models.AbsenceRequest).filter(
            models.AbsenceRequest.parent_id == parent_profile.id
        ).order_by(models.AbsenceRequest.created_at.desc()).all()
        return [_serialize_request(r) for r in requests]
    else:
        # Manager / admin: see requests for their kindergarten
        query = db.query(models.AbsenceRequest)
        if current_user.kindergarten_id:
            query = query.filter(
                models.AbsenceRequest.kindergarten_id == current_user.kindergarten_id
            )
        requests = query.order_by(models.AbsenceRequest.created_at.desc()).all()
        return [_serialize_request(r, include_child_name=True) for r in requests]


# ── GET /absence-requests/{id} ──────────────────────────────────────

@router.get("/absence-requests/{request_id}")
def get_absence_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence request not found")

    # Scope check
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile or absence.parent_id != parent_profile.id:
            raise HTTPException(status_code=404, detail="Absence request not found")

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

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
    ).first()
    if not absence or (parent_profile and absence.parent_id != parent_profile.id):
        raise HTTPException(status_code=404, detail="Not found")

    absence.status = models.AbsenceRequestStatus.CANCELLED
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
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only managers can approve")

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Not found")

    # Cross-KG check
    if current_user.kindergarten_id and absence.kindergarten_id != current_user.kindergarten_id:
        raise HTTPException(status_code=403, detail="Not in your kindergarten scope")

    if absence.status == models.AbsenceRequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Already approved")

    absence.status = models.AbsenceRequestStatus.APPROVED
    absence.manager_id = current_user.id
    absence.decision_note = payload.decision_note
    absence.decided_at = datetime.now(UTC)
    db.flush()

    # Create attendance records for each day in range
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

    db.commit()
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
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only managers can reject")

    absence = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.id == request_id,
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Not found")

    absence.status = models.AbsenceRequestStatus.REJECTED
    absence.manager_id = current_user.id
    absence.decision_note = payload.decision_note
    absence.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(absence)

    return {"id": absence.id, "status": absence.status.value}
