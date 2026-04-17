"""
Attendance domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

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
    
    # Verify child has active enrollment
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    
    if not active_enrollment:
        raise HTTPException(status_code=400, detail="Child does not have active enrollment")
    
    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)
    
    # Check if already checked in today (any record, even if checked out)
    today = date.today()
    existing_checkin = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today
    ).first()
    
    if existing_checkin:
        raise HTTPException(status_code=400, detail="Child already checked in today (one record per day allowed)")
    
    # Create attendance log
    attendance = models.AttendanceLog(
        child_id=child_id,
        class_id=active_enrollment.class_id,
        date=today,
        status=models.AttendanceStatus.PRESENT,
        check_in_at=datetime.now(),
        recorded_by=current_user.id
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="ATTENDANCE_CHECK_IN",
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
    
    # Find today's check-in without check-out
    today = date.today()
    attendance = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == child_id,
        models.AttendanceLog.date == today,
        models.AttendanceLog.check_out_at.is_(None)
    ).first()
    
    if not attendance:
        raise HTTPException(status_code=400, detail="Child is not checked in today")
    
    attendance.check_out_at = datetime.now()
    attendance.picked_by_name = picked_by_name
    db.commit()
    db.refresh(attendance)
    
    validators.log_audit_action(
        db=db,
        user_id=current_user.id,
        action="ATTENDANCE_CHECK_OUT",
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
    # Authorization: Admin can see all, others only their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        validators.validate_supervisor_role(current_user)

    # Validate kindergarten exists and user has access
    kindergarten = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == request.kindergarten_id
    ).first()
    if not kindergarten:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    if current_user.role != models.UserRole.ADMIN:
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

    # Validate date range (max 62 days)
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

    # Children info
    children_info = []
    for child in children:
        enrollment = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).first()
        class_info = db.query(models.Class).filter(models.Class.id == enrollment.class_id).first() if enrollment else None

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
                "city": kindergarten.city,
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
