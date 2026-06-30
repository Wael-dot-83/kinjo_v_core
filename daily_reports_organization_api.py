"""
Organization-level daily reports endpoint for admin users.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from utils.time_utils import today_amman as _today
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models
import validators
from database import get_db
from dependencies import get_current_admin_user

from api.reports.constants import REPORT_STATUS_DISPLAY, REPORT_STATUS_UI_METADATA


router = APIRouter(tags=["Daily Reports Organization"])


STATUS_LABELS_AR: Dict[str, str] = REPORT_STATUS_DISPLAY

STATUS_COLORS: Dict[str, str] = {k: v['color'] for k, v in REPORT_STATUS_UI_METADATA.items()}

STATUS_ICONS: Dict[str, str] = {k: v['icon'] for k, v in REPORT_STATUS_UI_METADATA.items()}

AR_MONTHS: Dict[int, str] = {
    1: "يناير",
    2: "فبراير",
    3: "مارس",
    4: "أبريل",
    5: "مايو",
    6: "يونيو",
    7: "يوليو",
    8: "أغسطس",
    9: "سبتمبر",
    10: "أكتوبر",
    11: "نوفمبر",
    12: "ديسمبر",
}

ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

ACTIVE_ENROLLMENT_STATUSES = (
    models.EnrollmentStatus.SUBMITTED,
    models.EnrollmentStatus.PENDING_REVIEW,
    models.EnrollmentStatus.ACCEPTED,
    models.EnrollmentStatus.ACTIVE,
)


class DailyReportRowOut(BaseModel):
    daily_report_id: Optional[int]
    child_id: int
    child_name_ar: str
    child_label_ar: str
    filled_by_name_ar: str
    status: str
    status_ar: str
    status_color: str
    status_icon: str
    acknowledged_by_parent: bool
    notes: str


class KindergartenDailyReportsOut(BaseModel):
    id: int
    name_ar: str
    manager_name_ar: str
    report_date: str
    report_date_ar: str
    has_reports: bool
    total_reports: int
    status_counts: Dict[str, int]
    message: Optional[str]
    reports: List[DailyReportRowOut]


class PaginationOut(BaseModel):
    current_page: int
    per_page: int
    total_kindergartens: int
    total_reports_all_kindergartens: int
    total_reports_returned_this_request: int
    has_more_pages: bool


class DailyReportsOrganizationResponse(BaseModel):
    date: str
    date_ar: str
    is_future_date: bool
    message: Optional[str]
    kindergartens: List[KindergartenDailyReportsOut]
    pagination: Optional[PaginationOut] = None


def _to_arabic_digits(value: str) -> str:
    return value.translate(ARABIC_DIGITS)


def _format_date_ar(report_date: date) -> str:
    month_name = AR_MONTHS.get(report_date.month, str(report_date.month))
    text = f"{report_date.day} {month_name} {report_date.year}"
    return _to_arabic_digits(text)


def _child_full_name(child: models.Child) -> str:
    parts = [child.first_name or "", child.last_name or ""]
    value = " ".join([part.strip() for part in parts if part and part.strip()]).strip()
    return value or f"طفل رقم {_to_arabic_digits(str(child.id))}"


def _display_user_name(user: Optional[models.User]) -> str:
    if not user:
        return "غير متاح"
    if user.full_name and user.full_name.strip():
        return user.full_name.strip()
    return user.username or "غير متاح"


def _parse_kindergarten_ids(raw_value: Optional[str]) -> List[int]:
    if not raw_value:
        return []

    ids: List[int] = []
    for part in raw_value.split(","):
        item = part.strip()
        if not item:
            continue
        if not item.isdigit():
            raise HTTPException(status_code=400, detail="Invalid kindergarten ID values")
        parsed = int(item)
        if parsed <= 0:
            raise HTTPException(status_code=400, detail="Kindergarten ID must be a positive integer")
        ids.append(parsed)

    return sorted(set(ids))


def _resolve_status(
    report: Optional[models.DailyReport],
    attendance_status: Optional[models.AttendanceStatus],
    viewed_report_ids: Set[int],
) -> Tuple[str, bool]:
    if report:
        if report.status == models.DailyReportStatus.SENT_TO_PARENT and report.id in viewed_report_ids:
            return "received", True
        if report.status in (
            models.DailyReportStatus.SUBMITTED,
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
        ):
            return "pending", False
        return "incomplete", False

    if attendance_status == models.AttendanceStatus.ABSENT:
        return "absent", False
    return "not_submitted", False


def _build_empty_status_counts() -> Dict[str, int]:
    return {code: 0 for code in STATUS_LABELS_AR}


@router.get("/daily-reports", response_model=DailyReportsOrganizationResponse)
def list_daily_reports_for_organization(
    date_param: Optional[date] = Query(default=None, alias="date"),
    kindergarten_ids: Optional[str] = Query(default=None, description="Comma-separated kindergarten IDs"),
    governorate_id: Optional[str] = Query(default=None),
    governorate: Optional[str] = Query(default=None),
    all_kindergartens: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    page: Optional[int] = Query(None, ge=1, description="Page number (1-based)"),
    per_page: Optional[int] = Query(None, ge=10, le=500, description="Number of reports per kindergarten per page (default 200 = almost no limit)"),
    current_admin: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> DailyReportsOrganizationResponse:
    selected_date = date_param or _today()

    selected_kindergarten_ids = _parse_kindergarten_ids(kindergarten_ids)
    governorate_filter = (governorate or governorate_id or "").strip()
    if governorate_filter:
        try:
            governorate_filter = validators.validate_jordan_governorate(governorate_filter)
        except validators.ValidationError:
            pass

    kindergarten_query = db.query(models.Kindergarten)

    if all_kindergartens:
        pass
    elif selected_kindergarten_ids:
        kindergarten_query = kindergarten_query.filter(models.Kindergarten.id.in_(selected_kindergarten_ids))
    elif governorate_filter:
        kindergarten_query = kindergarten_query.filter(
            models.Kindergarten.governorate.ilike(f"%{governorate_filter}%")
        )
    else:
        return DailyReportsOrganizationResponse(
            date=selected_date.isoformat(),
            date_ar=_format_date_ar(selected_date),
            is_future_date=selected_date > _today(),
            message="لا توجد تقارير متاحة بناءً على الاختيارات",
            kindergartens=[],
        )

    kindergartens = kindergarten_query.order_by(models.Kindergarten.name_ar.asc()).all()
    if not kindergartens:
        return DailyReportsOrganizationResponse(
            date=selected_date.isoformat(),
            date_ar=_format_date_ar(selected_date),
            is_future_date=selected_date > _today(),
            message="لا توجد تقارير متاحة بناءً على الاختيارات",
            kindergartens=[],
        )

    kg_ids = [kg.id for kg in kindergartens]
    manager_rows = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.MANAGER,
            models.User.kindergarten_id.in_(kg_ids),
            models.User.status == models.UserStatus.ACTIVE,
        )
        .order_by(models.User.kindergarten_id.asc(), models.User.id.asc())
        .all()
    )

    manager_name_by_kg: Dict[int, str] = {}
    for manager in manager_rows:
        if manager.kindergarten_id and manager.kindergarten_id not in manager_name_by_kg:
            manager_name_by_kg[manager.kindergarten_id] = _display_user_name(manager)

    enrollment_rows = (
        db.query(models.EnrollmentApplication.kindergarten_id, models.Child)
        .join(models.Child, models.Child.id == models.EnrollmentApplication.child_id)
        .filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES),
        )
        .all()
    )

    children_by_kg: Dict[int, List[models.Child]] = defaultdict(list)
    child_ids: List[int] = []
    for kg_id, child in enrollment_rows:
        children_by_kg[kg_id].append(child)
        child_ids.append(child.id)

    child_ids = sorted(set(child_ids))
    attendance_by_child: Dict[int, models.AttendanceStatus] = {}
    if child_ids:
        attendance_rows = (
            db.query(models.AttendanceLog.child_id, models.AttendanceLog.status)
            .filter(
                models.AttendanceLog.child_id.in_(child_ids),
                models.AttendanceLog.date == selected_date,
            )
            .all()
        )
        attendance_by_child = {row.child_id: row.status for row in attendance_rows}

    report_query = (
        db.query(models.DailyReport)
        .options(
            joinedload(models.DailyReport.child),
            joinedload(models.DailyReport.submitter),
        )
        .filter(
            models.DailyReport.kindergarten_id.in_(kg_ids),
            models.DailyReport.date == selected_date,
        )
    )
    daily_reports = report_query.all()
    reports_by_key: Dict[Tuple[int, int], models.DailyReport] = {
        (report.kindergarten_id, report.child_id): report for report in daily_reports
    }

    report_ids = [report.id for report in daily_reports]
    viewed_report_ids: Set[int] = set()
    if report_ids:
        viewed_rows = (
            db.query(models.DailyReportView.daily_report_id)
            .filter(models.DailyReportView.daily_report_id.in_(report_ids))
            .distinct()
            .all()
        )
        viewed_report_ids = {row.daily_report_id for row in viewed_rows}

    kindergarten_groups: List[KindergartenDailyReportsOut] = []
    total_rows_all = 0
    total_actual_reports = 0
    total_reports_all_kindergartens = 0
    total_reports_returned = 0
    has_more_any = False

    for kg in kindergartens:
        children = children_by_kg.get(kg.id, [])
        children = sorted(children, key=lambda child: (child.first_name or "", child.last_name or "", child.id))
        status_counts = _build_empty_status_counts()
        report_rows: List[DailyReportRowOut] = []
        actual_reports_in_kg = 0

        for child in children:
            report = reports_by_key.get((kg.id, child.id))
            if report:
                actual_reports_in_kg += 1

            status_code, acknowledged = _resolve_status(
                report=report,
                attendance_status=attendance_by_child.get(child.id),
                viewed_report_ids=viewed_report_ids,
            )
            status_counts[status_code] += 1

            child_name = _child_full_name(child)
            row = DailyReportRowOut(
                daily_report_id=report.id if report else None,
                child_id=child.id,
                child_name_ar=child_name,
                child_label_ar=f"اسم الطفل: {child_name} (المعرف: {_to_arabic_digits(str(child.id))})",
                filled_by_name_ar=_display_user_name(report.submitter) if report else "غير متاح",
                status=status_code,
                status_ar=STATUS_LABELS_AR[status_code],
                status_color=STATUS_COLORS[status_code],
                status_icon=STATUS_ICONS[status_code],
                acknowledged_by_parent=acknowledged,
                notes=(report.notes or "").strip() if report and report.notes else "",
            )
            report_rows.append(row)

        total_rows_all += len(report_rows)
        total_actual_reports += actual_reports_in_kg
        total_reports_all_kindergartens += len(report_rows)

        if page is not None and per_page is not None:
            start = (page - 1) * per_page
            end = start + per_page
            paginated_reports = report_rows[start:end]
            has_more = len(report_rows) > end
            if has_more:
                has_more_any = True
        else:
            paginated_reports = report_rows[offset : offset + limit]
            has_more = False

        total_reports_returned += len(paginated_reports)

        kindergarten_groups.append(
            KindergartenDailyReportsOut(
                id=kg.id,
                name_ar=kg.name_ar,
                manager_name_ar=manager_name_by_kg.get(kg.id, "غير محدد"),
                report_date=selected_date.isoformat(),
                report_date_ar=_format_date_ar(selected_date),
                has_reports=actual_reports_in_kg > 0,
                total_reports=len(report_rows),
                status_counts=status_counts,
                message=None if actual_reports_in_kg > 0 else "لا توجد تقارير يومية مقدمة لهذا اليوم",
                reports=paginated_reports,
            )
        )

    response_message: Optional[str] = None
    is_future_date = selected_date > _today()
    if total_rows_all == 0:
        response_message = "لا توجد تقارير متاحة بناءً على الاختيارات"
    elif total_actual_reports == 0:
        response_message = "غير متاح" if is_future_date else "لا توجد تقارير متاحة بناءً على الاختيارات"

    pagination = None
    if page is not None and per_page is not None:
        pagination = {
            "current_page": page,
            "per_page": per_page,
            "total_kindergartens": len(kindergarten_groups),
            "total_reports_all_kindergartens": total_reports_all_kindergartens,
            "total_reports_returned_this_request": total_reports_returned,
            "has_more_pages": has_more_any
        }

    return DailyReportsOrganizationResponse(
        date=selected_date.isoformat(),
        date_ar=_format_date_ar(selected_date),
        is_future_date=is_future_date,
        message=response_message,
        kindergartens=kindergarten_groups,
        pagination=pagination,
    )
