"""
Parent service layer.

Pure business/assembly logic for the parent domain, kept out of the API route
handlers so endpoints stay thin. DB access uses the caller-provided session.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import validators

_JORDAN_TZ = timezone(timedelta(hours=3))

ENROLLMENT_STATUS_AR = {
    "DRAFT": "مسودة",
    "SUBMITTED": "مقدّم",
    "PENDING_REVIEW": "قيد المراجعة",
    "ACCEPTED": "مقبول",
    "REJECTED": "مرفوض",
    "WITHDRAWN": "منسحب",
    "WAITLISTED": "قائمة الانتظار",
    "ACTIVE": "نشط",
}

DASHBOARD_ENROLLMENT_STATUS_PRIORITY = {
    models.EnrollmentStatus.ACTIVE: 0,
    models.EnrollmentStatus.PENDING_REVIEW: 1,
    models.EnrollmentStatus.WAITLISTED: 2,
}

_DASHBOARD_ENROLLMENT_STATUSES = [
    models.EnrollmentStatus.ACTIVE,
    models.EnrollmentStatus.WAITLISTED,
    models.EnrollmentStatus.PENDING_REVIEW,
]


def pick_primary_enrollment(enrollment_list: List[models.EnrollmentApplication]) -> Optional[models.EnrollmentApplication]:
    if not enrollment_list:
        return None
    return sorted(
        enrollment_list,
        key=lambda e: (
            DASHBOARD_ENROLLMENT_STATUS_PRIORITY.get(e.status, len(DASHBOARD_ENROLLMENT_STATUS_PRIORITY)),
            -(e.id or 0),
        ),
    )[0]


def group_enrollments_by_child(enrollments: List[models.EnrollmentApplication]) -> Dict[int, List[models.EnrollmentApplication]]:
    grouped: Dict[int, List[models.EnrollmentApplication]] = defaultdict(list)
    for e in enrollments:
        grouped[e.child_id].append(e)
    return grouped


def build_dashboard_payload(db: Session, parent_profile: models.ParentProfile) -> Dict[str, Any]:
    children = (
        db.query(models.Child)
        .filter(
            models.Child.parent_id == parent_profile.id,
            models.Child.deleted_at.is_(None),
        )
        .all()
    )

    today = datetime.now(_JORDAN_TZ).date()
    child_ids = [c.id for c in children]

    enrollments_by_child: Dict[int, List[models.EnrollmentApplication]] = defaultdict(list)
    attendance_by_child: Dict[int, models.AttendanceLog] = {}
    latest_report_by_child: Dict[int, models.DailyReport] = {}

    if child_ids:
        enrollments_by_child = group_enrollments_by_child(
            db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id.in_(child_ids),
                models.EnrollmentApplication.status.in_(_DASHBOARD_ENROLLMENT_STATUSES),
            )
            .all()
        )
        attendance_by_child = {
            a.child_id: a
            for a in db.query(models.AttendanceLog)
            .filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date == today,
            )
            .all()
        }

        subq = (
            db.query(
                models.DailyReport.child_id,
                func.max(models.DailyReport.date).label("max_date"),
            )
            .filter(
                models.DailyReport.child_id.in_(child_ids),
                models.DailyReport.status == models.DailyReportStatus.SENT_TO_PARENT,
            )
            .group_by(models.DailyReport.child_id)
            .subquery()
        )
        for r in (
            db.query(models.DailyReport)
            .join(
                subq,
                (models.DailyReport.child_id == subq.c.child_id) & (models.DailyReport.date == subq.c.max_date),
            )
            .all()
        ):
            latest_report_by_child[r.child_id] = r

    kgs_by_id: Dict[int, models.Kindergarten] = {}
    if child_ids:
        kg_ids = {
            e.kindergarten_id
            for enrollment_list in enrollments_by_child.values()
            for e in enrollment_list
            if e.kindergarten_id
        }
        if kg_ids:
            kgs_by_id = {
                kg.id: kg for kg in db.query(models.Kindergarten).filter(models.Kindergarten.id.in_(kg_ids)).all()
            }

    children_data = []
    for child in children:
        enrollment_list = enrollments_by_child.get(child.id, [])
        primary_enrollment = pick_primary_enrollment(enrollment_list)
        attendance = attendance_by_child.get(child.id)
        latest_report = latest_report_by_child.get(child.id)
        kg = kgs_by_id.get(primary_enrollment.kindergarten_id) if primary_enrollment else None

        child_info: Dict[str, Any] = {
            "id": child.id,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value
            if hasattr(child.gender, "value")
            else (str(child.gender) if child.gender else None),
            "kindergarten_name": (kg.name_ar or kg.name_en) if kg else None,
            "age_months": validators.validate_age_months(child.date_of_birth),
            "enrollment": None,
            "enrollments": [
                {
                    "id": e.id,
                    "status": e.status.value,
                    "status_ar": ENROLLMENT_STATUS_AR.get(e.status.value, e.status.value),
                    "kindergarten_id": e.kindergarten_id,
                    "kindergarten_name": (kgs_by_id[e.kindergarten_id].name_ar or kgs_by_id[e.kindergarten_id].name_en)
                    if e.kindergarten_id in kgs_by_id
                    else None,
                    "class_id": e.class_id,
                }
                for e in enrollment_list
            ],
            "attendance_today": None,
            "latest_report_date": None,
        }

        if primary_enrollment:
            child_info["enrollment"] = {
                "status": primary_enrollment.status.value,
                "kindergarten_id": primary_enrollment.kindergarten_id,
                "class_id": primary_enrollment.class_id,
            }

        if attendance:
            child_info["attendance_today"] = {
                "checked_in": attendance.check_in_at.strftime("%H:%M") if attendance.check_in_at else None,
                "checked_out": attendance.check_out_at.strftime("%H:%M") if attendance.check_out_at else None,
            }

        if latest_report:
            child_info["latest_report_date"] = (
                latest_report.date.isoformat() if isinstance(latest_report.date, date) else latest_report.date
            )

        children_data.append(child_info)

    return {
        "parent": {
            "name": f"{parent_profile.first_name} {parent_profile.last_name}",
            "phone": parent_profile.phone_number,
        },
        "children": children_data,
        "total_children": len(children),
        "notifications": [],
    }
