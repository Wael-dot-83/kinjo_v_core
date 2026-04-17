"""
KPI domain endpoints
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

router = APIRouter(tags=["KPI"])

@router.get("/kpi/attendance-rate")
def get_attendance_rate_kpi(
    kindergarten_id: int,
    period_start: str,
    period_end: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate attendance rate KPI for a kindergarten"""
    validators.validate_manager_role(current_user)
    validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)
    
    # Get all active enrollments for this kindergarten
    active_enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).count()
    
    if active_enrollments == 0:
        return {
            "kpi_name": "attendance_rate",
            "kpi_value": 0,
            "period_start": period_start,
            "period_end": period_end,
            "kindergarten_id": kindergarten_id
        }
    
    # Count attendance records in period
    child_ids = [e.child_id for e in db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.kindergarten_id == kindergarten_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).all()]
    
    attendance_count = db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id.in_(child_ids),
        models.AttendanceLog.date >= start_date,
        models.AttendanceLog.date <= end_date
    ).count()
    
    # Calculate working days
    days = (end_date - start_date).days + 1
    working_days = days * 5 // 7  # Rough estimate
    
    expected_attendance = active_enrollments * working_days
    rate = (attendance_count / expected_attendance * 100) if expected_attendance > 0 else 0
    
    return {
        "kpi_name": "attendance_rate",
        "kpi_value": min(100, round(rate, 2)),
        "period_start": period_start,
        "period_end": period_end,
        "kindergarten_id": kindergarten_id
    }


# @router.get("/kpi/summary")  # Moved to kpi_service.py
# def get_kpi_summary(
#     kindergarten_id: Optional[int] = None,
#     period_start: Optional[str] = None,
#     period_end: Optional[str] = None,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get comprehensive KPI summary dashboard for all metrics"""
#     if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
#         raise HTTPException(status_code=403, detail="Only admin or manager can view KPI summaries")
#     
#     # Determine kindergarten scope
#     if kindergarten_id is None:
#         if current_user.role == models.UserRole.MANAGER:
#             kindergarten_id = current_user.kindergarten_id
#         else:
#             # Admin without kindergarten_id sees all (return first kindergarten for demo)
#             first_kg = db.query(models.Kindergarten).first()
#             kindergarten_id = first_kg.id if first_kg else None
#     
#     if not kindergarten_id:
#         raise HTTPException(status_code=400, detail="No kindergarten available")
#     
#     # Set default period to current month if not provided
#     if not period_start or not period_end:
#         today = date.today()
#         period_start = date(today.year, today.month, 1).isoformat()
#         last_day = date(today.year, today.month + 1, 1) - timedelta(days=1) if today.month < 12 else date(today.year, 12, 31)
#         period_end = last_day.isoformat()
#     
#     # Get active enrollments count
#     active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
#     ).scalar() or 0
#     
#     # Get total capacity across all classes
#     total_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
#         models.Class.kindergarten_id == kindergarten_id,
#         models.Class.is_active == True
#     ).scalar() or 0
#     
#     # Calculate occupancy rate
#     occupancy_rate = (active_enrollments / total_capacity * 100) if total_capacity > 0 else 0
#     
#     # Count attendance records in period
#     start_date = date.fromisoformat(period_start)
#     end_date = date.fromisoformat(period_end)
#     
#     child_ids = [e.child_id for e in db.query(models.EnrollmentApplication).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
#     ).all()]
#     
#     attendance_count = db.query(func.count(models.AttendanceLog.id)).filter(
#         models.AttendanceLog.child_id.in_(child_ids) if child_ids else False,
#         models.AttendanceLog.date >= start_date,
#         models.AttendanceLog.date <= end_date
#     ).scalar() or 0
#     
#     # Calculate attendance rate
#     days = (end_date - start_date).days + 1
#     working_days = max(1, days * 5 // 7)  # Rough estimate
#     expected_attendance = active_enrollments * working_days
#     attendance_rate = (attendance_count / expected_attendance * 100) if expected_attendance > 0 else 0
#     
#     # Count incidents in period
#     incident_count = db.query(func.count(models.Incident.id)).filter(
#         models.Incident.kindergarten_id == kindergarten_id,
#         func.date(models.Incident.occurred_at) >= start_date,
#         func.date(models.Incident.occurred_at) <= end_date
#     ).scalar() or 0
#     
#     # Count pending daily reports
#     pending_reports = db.query(func.count(models.DailyReport.id)).join(
#         models.Child
#     ).join(
#     models.EnrollmentApplication
#     ).filter(
#         models.EnrollmentApplication.kindergarten_id == kindergarten_id,
#         models.DailyReport.status == models.DailyReportStatus.SUBMITTED
#     ).scalar() or 0
#     
#     # Calculate governance score (weighted composite)
#     safety_score = max(0, 100 - (incident_count * 5))  # Deduct 5 points per incident
#     reports_score = 100 if pending_reports == 0 else max(50, 100 - (pending_reports * 2))
#     compliance_score = 85  # Placeholder for license/compliance checks
#     
#     governance_score = (
#         attendance_rate * 0.25 +
#         safety_score * 0.30 +
#         reports_score * 0.20 +
#         compliance_score * 0.25
#     )
#     
#     # Determine governance band
#     if governance_score >= 80:
#         governance_band = "GREEN"
#     elif governance_score >= 60:
#         governance_band = "AMBER"
#     else:
#         governance_band = "RED"
#     
#     return {
#         "kindergarten_id": kindergarten_id,
#         "period_start": period_start,
#         "period_end": period_end,
#         "kpis": {
#             "occupancy_rate": {
#                 "value": round(occupancy_rate, 2),
#                 "unit": "percent",
#                 "description": "Enrollment vs total capacity",
#                 "enrolled": active_enrollments,
#                 "capacity": total_capacity
#             },
#             "attendance_rate": {
#                 "value": round(min(100, attendance_rate), 2),
#                 "unit": "percent",
#                 "description": "Daily attendance rate",
#                 "attendance_count": attendance_count,
#                 "expected": expected_attendance
#             },
#             "governance_score": {
#                 "value": round(governance_score, 2),
#                 "unit": "score",
#                 "band": governance_band,
#                 "description": "Composite governance score"
#             },
#             "incident_count": {
#                 "value": incident_count,
#                 "unit": "count",
#                 "description": "Total incidents reported"
#             },
#             "pending_reports": {
#                 "value": pending_reports,
#                 "unit": "count",
#                 "description": "Daily reports pending approval"
#             }
#         }
#     }


@router.get("/kpi/governance-score")
def get_governance_score(
    kindergarten_id: int,
    period_start: str,
    period_end: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate governance score with traffic light band"""
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only admin or manager can view governance scores")
    
    if current_user.role == models.UserRole.MANAGER:
        validators.validate_kindergarten_scope(current_user, kindergarten_id)
    
    # Calculate sub-scores (simplified)
    # In production, these would be calculated from actual data
    attendance_score = 75.0
    safety_score = 90.0
    reports_score = 80.0
    compliance_score = 85.0
    
    # Weighted average
    final_score = (
        attendance_score * 0.25 +
        safety_score * 0.30 +
        reports_score * 0.20 +
        compliance_score * 0.25
    )
    
    # Determine band
    if final_score >= 80:
        band = "GREEN"
    elif final_score >= 60:
        band = "AMBER"
    else:
        band = "RED"
    
    return {
        "kindergarten_id": kindergarten_id,
        "period_start": period_start,
        "period_end": period_end,
        "final_governance_score": round(final_score, 2),
        "band": band,
        "sub_scores": {
            "attendance": attendance_score,
            "safety": safety_score,
            "daily_reports": reports_score,
            "compliance": compliance_score
        }
    }
