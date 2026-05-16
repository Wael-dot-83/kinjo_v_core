"""Attendance summary domain logic extracted from endpoint module."""
from datetime import date
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import validators


def resolve_attendance_kindergarten_id(
    current_user: models.User,
    kindergarten_id: Optional[int],
) -> Optional[int]:
    if current_user.role == models.UserRole.ADMIN:
        return kindergarten_id
    if kindergarten_id and current_user.kindergarten_id != kindergarten_id:
        raise HTTPException(status_code=403, detail="Access denied to this kindergarten")
    return current_user.kindergarten_id


def build_attendance_summary(
    attendance_date: date,
    current_user: models.User,
    db: Session,
    kindergarten_id: Optional[int],
) -> Dict[str, float]:
    validators.validate_supervisor_role(current_user)

    scoped_kindergarten_id = resolve_attendance_kindergarten_id(current_user, kindergarten_id)

    total_query = db.query(func.count(func.distinct(models.EnrollmentApplication.child_id))).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    )
    if scoped_kindergarten_id:
        total_query = total_query.filter(models.EnrollmentApplication.kindergarten_id == scoped_kindergarten_id)
    total_children = total_query.scalar() or 0

    present_query = (
        db.query(func.count(func.distinct(models.AttendanceLog.child_id)))
        .join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
        )
        .filter(
            models.AttendanceLog.date == attendance_date,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
    )
    if scoped_kindergarten_id:
        present_query = present_query.filter(
            models.EnrollmentApplication.kindergarten_id == scoped_kindergarten_id
        )
    present_children = present_query.scalar() or 0

    absent_children = max(total_children - present_children, 0)
    attendance_rate = round((present_children / total_children) * 100, 2) if total_children > 0 else 0.0

    return {
        "date": attendance_date,
        "kindergarten_id": scoped_kindergarten_id,
        "total_children": total_children,
        "present_children": present_children,
        "absent_children": absent_children,
        "attendance_rate": attendance_rate,
    }
