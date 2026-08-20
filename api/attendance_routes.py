"""
Attendance domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman, now_amman as _now_amman
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
from audit_actions import AuditAction
import validators
from config import settings
from database import get_db
from dependencies import get_current_user, Permission, has_global_scope, has_permission
from rbac import assert_supervisor_owns_child, assert_supervisor_owns_class, get_supervisor_child_ids
from services.jordan_locations import governorate_filter

router = APIRouter(tags=["Attendance"])

@router.post("/attendance/check-in")
def check_in_child(
    child_id: int,
    method: str = Query(..., description="pin, qr, or manual"),
    dropped_by_name: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check in a child for attendance"""
    validators.validate_supervisor_role(current_user)
    if current_user.role == models.UserRole.SUPERVISOR:
        assert_supervisor_owns_child(current_user.id, child_id, db)
    
    # Verify child has active enrollment
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
    ).first()
    
    if not active_enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")

    if not active_enrollment.class_id:
        raise HTTPException(status_code=400, detail="Child must be assigned to a class before attendance can be recorded")

    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)

    # Check if already checked in today (any record, even if checked out)
    from utils.time_utils import today_amman
    today = today_amman()
    existing_checkin = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today
    ).first()

    if existing_checkin:
        raise HTTPException(status_code=409, detail="Child already checked in today (one record per day allowed)")

    # Create attendance log
    attendance = models.AttendanceLog(
        child_id=child_id,
        class_id=active_enrollment.class_id,
        date=today,
        status=models.AttendanceStatus.PRESENT,
        check_in_at=_now_amman(),
        recorded_by=current_user.id
    )
    db.add(attendance)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Child already checked in today (concurrent request)")
    db.refresh(attendance)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.ATTENDANCE_CHECK_IN,
        entity_type="AttendanceLog",
        entity_id=attendance.id,
        details=f"Child {child_id} checked in",
        sensitivity_level=1
    )

    return {
        "id": attendance.id,
        "child_id": attendance.child_id,
        "date": attendance.date.isoformat(),
        "check_in_at": attendance.check_in_at.isoformat() if attendance.check_in_at else None,
        "check_out_at": None
    }


@router.post("/attendance/check-out")
def check_out_child(
    child_id: int,
    picked_by_name: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check out a child from attendance"""
    validators.validate_supervisor_role(current_user)
    if current_user.role == models.UserRole.SUPERVISOR:
        assert_supervisor_owns_child(current_user.id, child_id, db)
    
    # Find today's check-in without check-out
    from utils.time_utils import today_amman
    today = today_amman()
    attendance = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today,
        models.AttendanceLog.check_out_at.is_(None)
    ).first()
    
    if not attendance:
        raise HTTPException(status_code=400, detail="Child is not checked in today")
    if current_user.role == models.UserRole.SUPERVISOR:
        assert_supervisor_owns_class(current_user.id, attendance.class_id, db)
    
    attendance.check_out_at = _now_amman()
    attendance.picked_by_name = picked_by_name
    db.commit()
    db.refresh(attendance)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.ATTENDANCE_CHECK_OUT,
        entity_type="AttendanceLog",
        entity_id=attendance.id,
        details=f"Child {child_id} checked out",
        sensitivity_level=1
    )

    return {
        "id": attendance.id,
        "child_id": attendance.child_id,
        "date": attendance.date.isoformat(),
        "check_in_at": attendance.check_in_at.isoformat() if attendance.check_in_at else None,
        "check_out_at": attendance.check_out_at.isoformat() if attendance.check_out_at else None,
        "picked_by_name": attendance.picked_by_name
    }


# ============================================================================
# Attendance Report Endpoint
# ============================================================================

class AttendanceReportRequest(BaseModel):
    kindergarten_id: int
    class_ids: Optional[List[int]] = None
    child_ids: Optional[List[int]] = None
    period_type: str = Field(..., pattern="^(day|week|month|range)$")
    date: Optional[str] = None  # For day/week/month
    start_date: Optional[str] = None  # For range
    end_date: Optional[str] = None  # For range

    @field_validator("period_type", "date", "start_date", "end_date")
    def validate_dates(cls, v, info):
        if info.field_name == "period_type":
            period_type = v
        else:
            period_type = info.data.get("period_type")

        if period_type == "range":
            if not info.data.get("start_date") or not info.data.get("end_date"):
                raise ValueError("start_date and end_date required for range period")
        elif period_type in ["day", "week", "month"]:
            if not info.data.get("date"):
                raise ValueError("date required for day/week/month period")
        return v


class AttendanceReportResponse(BaseModel):
    meta: dict
    dates: List[str]
    children: List[dict]
    matrix: dict
    totals: dict
    chart_data: dict


@router.get("/attendance/report", response_model=AttendanceReportResponse)
def get_attendance_report(
    request: AttendanceReportRequest = Depends(),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attendance report matrix for specified period"""
    if current_user.role == models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Supervisors must use the scoped attendance endpoint")
    # Authorization: Admin can see all, others only their kindergarten
    if not has_permission(current_user, Permission.ADMIN_PANEL):
        validators.validate_supervisor_role(current_user)

    # Validate kindergarten exists and user has access
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == request.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    if not has_permission(current_user, Permission.ADMIN_PANEL):
        validators.validate_kindergarten_scope(current_user, request.kindergarten_id)

    # Determine date range
    if request.period_type == "range":
        try:
            start_date = date.fromisoformat(request.start_date)
            end_date = date.fromisoformat(request.end_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format")
    else:
        try:
            anchor_date = date.fromisoformat(request.date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format")

        if request.period_type == "day":
            start_date = end_date = anchor_date
        elif request.period_type == "week":
            start_date = anchor_date - timedelta(days=anchor_date.weekday())
            end_date = start_date + timedelta(days=6)
        elif request.period_type == "month":
            start_date = anchor_date.replace(day=1)
            if anchor_date.month == 12:
                end_date = anchor_date.replace(year=anchor_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = anchor_date.replace(month=anchor_date.month + 1, day=1) - timedelta(days=1)

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 62:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 62 days")

    # Get target children
    children_query = db.query(models.Child).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    ).filter(
        models.EnrollmentApplication.kindergarten_id == request.kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )

    if request.class_ids:
        # Validate classes belong to kindergarten
        valid_classes = db.query(models.Class.id).filter(
            models.Class.kindergarten_id == request.kindergarten_id,
            models.Class.id.in_(request.class_ids)
        ).all()
        valid_class_ids = [c[0] for c in valid_classes]
        if len(valid_class_ids) != len(request.class_ids):
            raise HTTPException(status_code=422, detail="Some class_ids do not belong to this kindergarten")

        children_query = children_query.filter(
            models.EnrollmentApplication.class_id.in_(valid_class_ids)
        )

    if request.child_ids:
        children_query = children_query.filter(models.Child.id.in_(request.child_ids))

    children = children_query.all()
    child_ids = [child.id for child in children]

    # Get attendance data efficiently
    attendance_data = []
    if child_ids:
        attendance_data = db.query(
            models.AttendanceLog.child_id,
            models.AttendanceLog.date,
            models.AttendanceLog.check_in_at,
            models.AttendanceLog.check_out_at
        ).filter(
            models.AttendanceLog.child_id.in_(child_ids),
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date
        ).all()

    # Build matrix
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    matrix = {}
    totals = {"per_child": {}, "per_day": {}, "overall": {"present": 0, "absent": 0}}

    for child in children:
        child_id = child.id
        matrix[child_id] = {}
        totals["per_child"][child_id] = {"present": 0, "absent": 0}

        for date_str in dates:
            # Check if child was present on this date
            present = any(a.child_id == child_id and a.date.isoformat() == date_str for a in attendance_data)
            status = "present" if present else "absent"
            matrix[child_id][date_str] = {"status": status, "label": "حاضر" if present else "غائب"}

            if present:
                totals["per_child"][child_id]["present"] += 1
                totals["overall"]["present"] += 1
            else:
                totals["per_child"][child_id]["absent"] += 1
                totals["overall"]["absent"] += 1

    # Per day totals
    for date_str in dates:
        present_count = sum(1 for child_id in matrix if matrix[child_id][date_str]["status"] == "present")
        totals["per_day"][date_str] = present_count

    # Children info — batch-fetch enrollments and classes to avoid N+1
    _cids = [c.id for c in children]
    _enrollments_map = {
        e.child_id: e for e in db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id.in_(_cids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).all()
    }
    _class_ids = list({e.class_id for e in _enrollments_map.values() if e.class_id})
    _classes_map = {c.id: c for c in db.query(models.Class).filter(models.Class.id.in_(_class_ids)).all()}

    children_info = []
    for child in children:
        enrollment = _enrollments_map.get(child.id)
        class_info = _classes_map.get(enrollment.class_id) if enrollment else None

        children_info.append({
            "id": child.id,
            "name_ar": f"{child.first_name_ar} {child.last_name_ar}",
            "name_en": f"{child.first_name_en or ''} {child.last_name_en or ''}".strip(),
            "class_id": enrollment.class_id if enrollment else None,
            "class_name": class_info.name_ar if class_info else None
        })

    # Chart data
    total_days = len(dates)
    total_children = len(children)
    attendance_rate = (totals["overall"]["present"] / (total_children * total_days)) * 100 if total_children * total_days > 0 else 0

    chart_data = {
        "breakdown_by_status": {
            "present": totals["overall"]["present"],
            "absent": totals["overall"]["absent"]
        },
        "trend_present_by_day": [{"date": d, "count": totals["per_day"][d]} for d in dates]
    }

    return AttendanceReportResponse(
        meta={
            "kindergarten": {
                "id": kindergarten.id,
                "name_ar": kindergarten.name_ar,
                "name_en": kindergarten.name_en,
                "governorate": kindergarten.governorate,
                "district": kindergarten.district,
                "area": kindergarten.area,
                "phone": kindergarten.contact_phone,
                "address": kindergarten.address_line
            },
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "period_type": request.period_type
        },
        dates=dates,
        children=children_info,
        matrix=matrix,
        totals={
            **totals,
            "summary": {
                "total_children": total_children,
                "total_school_days": total_days,
                "attendance_rate": round(attendance_rate, 2)
            }
        },
        chart_data=chart_data
    )


# ── PATCH /attendance/{id}/status ────────────────────────────────────

class AttendanceCorrectionRequest(BaseModel):
    new_status: str
    notes: Optional[str] = None


@router.patch("/attendance/{att_id}/status")
def correct_attendance_status(
    att_id: int,
    payload: AttendanceCorrectionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Role check: admin, manager, or supervisor only
    validators.validate_supervisor_role(current_user)

    att = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.id == att_id
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    # 2. Limit corrections to within 7 days of the attendance date
    from utils.time_utils import today_amman
    if (today_amman() - att.date).days > 7:
        raise HTTPException(
            status_code=400,
            detail="Attendance corrections are only permitted within 7 days of the recorded date"
        )

    # 3. Kindergarten scope: verify via the class that owns this attendance record
    att_class = db.query(models.Class).filter(models.Class.id == att.class_id).first()
    if not att_class:
        raise HTTPException(status_code=404, detail="Class for attendance record not found")
    validators.validate_kindergarten_scope(current_user, att_class.kindergarten_id)
    if current_user.role == models.UserRole.SUPERVISOR:
        assert_supervisor_owns_class(current_user.id, att.class_id, db)

    try:
        new_status = models.AttendanceStatus(payload.new_status)
    except (ValueError, KeyError):
        raise HTTPException(status_code=422, detail="Invalid attendance status")

    if att.status == new_status:
        return {"message": "No change needed"}

    old_status = att.status.value
    att.status = new_status
    if payload.notes:
        att.notes = payload.notes
    db.commit()
    db.refresh(att)

    # 3. Audit: record actor, previous and new status
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.ATTENDANCE_STATUS_CORRECTED,
        entity_type="AttendanceLog",
        entity_id=att.id,
        details=f"Status changed from {old_status} to {att.status.value} by user {current_user.id}",
        sensitivity_level=2,
        old_data={"status": old_status},
        new_data={"status": att.status.value}
    )

    return {"old_status": old_status, "new_status": att.status.value}


# ── Attendance summary endpoints ─────────────────────────────────────

def _attendance_summary(db: Session, target_date: date, current_user: models.User):
    """Return summary dict for a single date."""
    # Total children with ACTIVE enrollment in this user's scope
    enrolled_q = db.query(models.EnrollmentApplication.child_id).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.deleted_at.is_(None),
    )
    if current_user.role == models.UserRole.SUPERVISOR:
        enrolled_q = enrolled_q.filter(
            models.EnrollmentApplication.child_id.in_(get_supervisor_child_ids(current_user.id, db))
        )
    if not has_global_scope(current_user) and current_user.kindergarten_id:
        enrolled_q = enrolled_q.filter(
            models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
        )
    enrolled_child_ids = enrolled_q.subquery()

    total_children = db.query(func.count()).select_from(enrolled_child_ids).scalar()

    present_children = db.query(func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date == target_date,
        models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        models.AttendanceLog.child_id.in_(db.query(enrolled_child_ids)),
    ).scalar()

    rate = round((present_children / total_children * 100) if total_children else 0, 2)
    return {
        "date": target_date.isoformat(),
        "total_children": total_children,
        "present_children": present_children,
        "attendance_rate": rate,
    }


@router.get("/attendance")
def get_attendance_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from utils.time_utils import today_amman
    return _attendance_summary(db, today_amman(), current_user)


@router.get("/attendance/today")
def get_attendance_today(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from utils.time_utils import today_amman
    return _attendance_summary(db, today_amman(), current_user)


@router.get("/attendance/history-summary")
def get_attendance_history_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    kindergarten_name: Optional[str] = Query(None),
    child_name: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """History summary with filtering — Admin only."""
    validators.validate_admin_role(current_user)

    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")

    # Determine kindergarten scope
    kg_query = db.query(models.Kindergarten)
    filters_applied: dict = {}

    if kindergarten_id:
        mode = "specific_kindergarten"
        kg_query = kg_query.filter(models.Kindergarten.id == kindergarten_id)
    else:
        if governorate or kindergarten_name:
            mode = "filtered_kindergartens"
            if governorate:
                kg_query = kg_query.filter(governorate_filter(models.Kindergarten.governorate, governorate))
                filters_applied["governorate"] = governorate
            if kindergarten_name:
                kg_query = kg_query.filter(
                    or_(
                        models.Kindergarten.name_en.ilike(f"%{kindergarten_name}%"),
                        models.Kindergarten.name_ar.ilike(f"%{kindergarten_name}%"),
                    )
                )
                filters_applied["kindergarten_name"] = kindergarten_name
        else:
            mode = "all_kindergartens"

    if child_name:
        filters_applied["child_name"] = child_name

    kgs = kg_query.all()
    kg_ids = [k.id for k in kgs]

    # Build enrolled child ids within those KGs
    enrolled_q = db.query(models.EnrollmentApplication.child_id).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
    )
    enrolled_child_ids = [r[0] for r in enrolled_q.all()]

    # Filter by child_name if given
    if child_name:
        parts = child_name.strip().split()
        name_filter = db.query(models.Child.id).filter(models.Child.id.in_(enrolled_child_ids))
        for part in parts:
            name_filter = name_filter.filter(
                or_(
                    models.Child.first_name.ilike(f"%{part}%"),
                    models.Child.last_name.ilike(f"%{part}%"),
                )
            )
        enrolled_child_ids = [r[0] for r in name_filter.all()]

    # Build rows per date
    rows = []
    current = start_date
    total_present = 0
    total_total = 0
    while current <= end_date:
        day_total = len(enrolled_child_ids)
        day_present = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date == current,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            models.AttendanceLog.child_id.in_(enrolled_child_ids),
        ).scalar()
        rows.append({
            "date": current.isoformat(),
            "total": day_total,
            "present": day_present,
        })
        total_present += day_present
        total_total += day_total
        current += timedelta(days=1)

    scope: dict = {"mode": mode}
    if mode == "specific_kindergarten":
        scope["kindergarten_id"] = kindergarten_id
        # still report kg count for convenience
        scope["kindergarten_count"] = len(kg_ids)
    else:
        scope["kindergarten_count"] = len(kg_ids)
    if filters_applied:
        scope["filters"] = filters_applied

    return {
        "meta": {"scope": scope},
        "totals": {"present": total_present, "total": total_total},
        "rows": rows,
    }


@router.get("/attendance/{target_date}")
def get_attendance_by_date(
    target_date: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = date.fromisoformat(target_date)
    return _attendance_summary(db, d, current_user)
