"""
Daily Reports domain endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import date, datetime, timedelta, timezone
import re
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Daily Reports"])

class DailyReportCreateRequest(BaseModel):
    child_id: int
    date: str
    arrival_time: str
    leave_time: str
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    activities: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("date")
    @classmethod
    def date_not_in_future(cls, v: str) -> str:
        try:
            parsed = date.fromisoformat(v)
        except ValueError:
            raise ValueError("date must be in YYYY-MM-DD format")
        if parsed > date.today():
            raise ValueError("date cannot be in the future")
        return v

    @field_validator("arrival_time", "leave_time")
    @classmethod
    def time_format_hhmm(cls, v: str) -> str:
        if not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', v):
            raise ValueError("time must be in HH:MM format (24-hour)")
        return v


@router.post("/daily-reports/create", status_code=status.HTTP_201_CREATED)
def create_daily_report(
    report_data: DailyReportCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new daily report (Supervisor only)"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can create daily reports")
    
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == report_data.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
        
    # Verify active enrollment and scope
    active_enrollment = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id == report_data.child_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).first()
    
    if not active_enrollment:
         raise HTTPException(status_code=400, detail="Child not active in any class")
         
    validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)
    
    # Validate date
    report_date = date.fromisoformat(report_data.date)
    if report_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot create reports for future dates")

    # Ensure child profile is complete before creating a report
    ok, missing = validators.check_profile_complete(db, report_data.child_id)
    if not ok:
        raise HTTPException(status_code=400, detail={"message": "Child profile incomplete", "missing_fields": missing})

    # Working day validation
    if not validators.is_working_day(db, active_enrollment.kindergarten_id, report_date):
        raise HTTPException(status_code=400, detail="Date is not a working day for this kindergarten")

    # Ensure only one report per child per day
    existing = db.query(models.DailyReport).filter(
        models.DailyReport.child_id == report_data.child_id,
        models.DailyReport.date == report_date
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Daily report for this child and date already exists")

    # If supervisor, ensure they are assigned to the child's class on that date
    if current_user.role == models.UserRole.SUPERVISOR:
        assignment = db.query(models.SupervisorAssignment).join(
            models.Class, models.Class.id == models.SupervisorAssignment.class_id
        ).filter(
            models.SupervisorAssignment.supervisor_id == current_user.id,
            models.SupervisorAssignment.class_id == active_enrollment.class_id,
            models.SupervisorAssignment.start_date <= report_date,
            (models.SupervisorAssignment.end_date == None) | (models.SupervisorAssignment.end_date >= report_date)
        ).first()
        if not assignment:
            raise HTTPException(status_code=403, detail="Supervisor not assigned to this class on the report date")
    report = models.DailyReport(
        child_id=report_data.child_id,
        kindergarten_id=active_enrollment.kindergarten_id,
        date=report_date,
        status=models.DailyReportStatus.DRAFT,
        submitted_by=current_user.id,
        arrival_time=report_data.arrival_time,
        leave_time=report_data.leave_time,
        breakfast=report_data.breakfast,
        snack=report_data.snack,
        milk=report_data.milk,
        lunch=report_data.lunch,
        nap_start=report_data.nap_start,
        nap_end=report_data.nap_end,
        activities=report_data.activities,
        notes=report_data.notes
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        # Handle race condition where another report was inserted concurrently
        db.rollback()
        raise HTTPException(status_code=409, detail="Daily report for this child and date already exists")
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(report)

    return {
        "id": report.id,
        "child_id": report.child_id,
        "date": report.date.isoformat(),
        "status": report.status.value.lower()
    }


@router.post("/daily-reports/{report_id}/submit")
def submit_daily_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit daily report for approval — Supervisor only, must own the report."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can submit daily reports")

    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    if report.submitted_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only submit your own reports")

    if report.status != models.DailyReportStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft reports can be submitted")
    
    report.status = models.DailyReportStatus.SUBMITTED
    report.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None
    }


@router.post("/daily-reports/{report_id}/approve")
def approve_daily_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a daily report (Manager only)"""
    validators.validate_manager_role(current_user)
    
    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    # Cross-KG scope: managers cannot approve reports outside their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        if report.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Report not in your kindergarten scope")

    if report.status != models.DailyReportStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted reports can be approved")
    
    report.status = models.DailyReportStatus.APPROVED
    report.approved_by = current_user.id
    report.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "approved_at": report.approved_at.isoformat() if report.approved_at else None
    }


@router.get("/daily-reports/child/{child_id}")
def get_child_daily_reports(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get daily reports for a child (parents only see approved reports)"""
    # Verify child exists
    child = db.query(models.Child).filter(models.Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # If requester is a parent, ensure they own the child
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if not parent_profile or parent_profile.id != child.parent_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif current_user.role != models.UserRole.ADMIN:
        # Supervisors and managers are scoped to their kindergarten
        if child.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Child not in your kindergarten scope")

    query = db.query(models.DailyReport).filter(models.DailyReport.child_id == child_id)
    
    # Parents see approved and sent-to-parent reports
    if current_user.role == models.UserRole.PARENT:
        query = query.filter(models.DailyReport.status.in_([
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
        ]))
    
    reports = query.order_by(models.DailyReport.date.desc()).all()
    
    return {
        "reports": [
            {
                "id": r.id,
                "date": r.date.isoformat(),
                "status": r.status.value,
                "arrival_time": r.arrival_time,
                "leave_time": r.leave_time,
                "activities": r.activities,
                "notes": r.notes
            }
            for r in reports
        ]
    }


@router.get("/daily-reports/{report_id}")
def get_daily_report_by_id(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single daily report by ID"""
    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    # Parents can only see approved reports for their own children
    if current_user.role == models.UserRole.PARENT:
        child = db.query(models.Child).filter(models.Child.id == report.child_id).first()
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        if not parent_profile or not child or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if report.status != models.DailyReportStatus.APPROVED:
            raise HTTPException(status_code=403, detail="Report not available")

    return {
        "id": report.id,
        "child_id": report.child_id,
        "kindergarten_id": report.kindergarten_id,
        "date": report.date.isoformat(),
        "status": report.status.value,
        "arrival_time": report.arrival_time,
        "leave_time": report.leave_time,
        "activities": getattr(report, "activities", None),
        "notes": getattr(report, "notes", None),
        "mood": getattr(report, "mood", None),
        "submitted_by": report.submitted_by,
    }


@router.get("/supervisor/daily-reports")
def list_supervisor_daily_reports(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List daily reports accessible to the current supervisor/manager/admin"""
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Parents cannot access this endpoint")

    query = db.query(models.DailyReport)

    # Scope to kindergarten for non-admins
    if current_user.role != models.UserRole.ADMIN and current_user.kindergarten_id:
        query = query.filter(models.DailyReport.kindergarten_id == current_user.kindergarten_id)

    reports = query.order_by(models.DailyReport.date.desc()).all()

    return [
        {
            "id": r.id,
            "child_id": r.child_id,
            "kindergarten_id": r.kindergarten_id,
            "date": r.date.isoformat(),
            "status": r.status.value,
            "arrival_time": r.arrival_time,
            "leave_time": r.leave_time,
            "activities": getattr(r, "activities", None),
            "notes": getattr(r, "notes", None),
            "submitted_by": r.submitted_by,
        }
        for r in reports
    ]


@router.post("/daily-reports/{report_id}/view")
def record_daily_report_view(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record that a parent has viewed a daily report."""
    # 1. Restrict to PARENT role only
    if current_user.role != models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Only parents can record report views")

    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 2. Report must be in an accessible status (not a draft)
    allowed_statuses = {models.DailyReportStatus.APPROVED, models.DailyReportStatus.SENT_TO_PARENT}
    if report.status not in allowed_statuses:
        raise HTTPException(status_code=403, detail="Report is not accessible")

    # 3. Verify the authenticated parent owns the child referenced in the report
    child = db.query(models.Child).filter(models.Child.id == report.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Report not found")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    if not parent_profile or child.parent_id != parent_profile.id:
        raise HTTPException(status_code=403, detail="Access denied to this report")

    existing = db.query(models.DailyReportView).filter(
        models.DailyReportView.daily_report_id == report_id,
        models.DailyReportView.parent_user_id == current_user.id,
    ).first()
    if existing:
        return {"status": "already_recorded"}

    view = models.DailyReportView(
        daily_report_id=report_id,
        parent_user_id=current_user.id,
    )
    db.add(view)
    db.commit()
    return {"status": "recorded"}
