"""
Daily Reports domain endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import date, datetime, timedelta, timezone

_JORDAN_TZ = timezone(timedelta(hours=3))
import re
from typing import Optional
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
        if parsed > datetime.now(_JORDAN_TZ).date():
            raise ValueError("date cannot be in the future")
        return v

    @field_validator("arrival_time", "leave_time")
    @classmethod
    def time_format_hhmm(cls, v: str) -> str:
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("time must be in HH:MM format (24-hour)")
        return v


def _authorize_report_for_child(
    db: Session,
    current_user: models.User,
    child_id: int,
    report_date: date,
    *,
    require_no_existing_report: bool = True,
):
    """Run every gate that guards creating a daily report for one child.

    Returns the child's ACTIVE enrolment on success and raises HTTPException on
    the first failure, so a caller can either let it propagate (single create)
    or catch it and record a per-child outcome (batch create).

    Extracted rather than duplicated: the batch endpoint below has to apply the
    identical nine checks, and routers/supervisor.py already demonstrates what
    happens when a second report-creation path is written by hand — its
    endpoints construct DailyReport with columns the model does not have
    (`class_id`, `meals`) and answer 500 for every caller, because nothing kept
    them in step with this one.
    """
    # ---- Phase A: identity and scope -----------------------------------
    #
    # Every failure in this phase answers 404 "Child not found", byte for byte.
    # A child in another kindergarten, a child in a class this supervisor does
    # not run, and a child that does not exist must be indistinguishable —
    # otherwise numeric child IDs can be walked to map another tenant's roll.
    # This is the policy dependencies.ManagerScope already states ("404, not 403
    # — do not reveal that another tenant's resource exists").
    #
    # The ordering is load-bearing, not cosmetic. These gates previously ran
    # interleaved with the state gates below, and the class-assignment check ran
    # LAST — after the duplicate check. A foreign-class child who already had a
    # report therefore answered 409, which leaked both that the child exists and
    # that somebody had reported on them, before the assignment gate was reached.
    def _not_found():
        raise HTTPException(status_code=404, detail="Child not found")

    child = db.query(models.Child).filter(
        models.Child.id == child_id, models.Child.deleted_at.is_(None)
    ).first()
    if not child:
        _not_found()

    active_enrollment = (
        db.query(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.child_id == child_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
        )
        .first()
    )
    is_admin = current_user.role == models.UserRole.ADMIN
    if not active_enrollment:
        # An admin sees the whole network, so the distinction leaks nothing and
        # is worth keeping; for anyone scoped it is another existence signal.
        if is_admin:
            raise HTTPException(status_code=400, detail="Child not active in any class")
        _not_found()

    try:
        validators.validate_kindergarten_scope(current_user, active_enrollment.kindergarten_id)
    except HTTPException as exc:
        # Reuse the shared scope policy, but convert its 403 so a cross-tenant
        # child cannot be told apart from an absent one on this surface.
        if exc.status_code == 403:
            _not_found()
        raise

    if current_user.role == models.UserRole.SUPERVISOR:
        assignment = (
            db.query(models.SupervisorAssignment)
            .join(models.Class, models.Class.id == models.SupervisorAssignment.class_id)
            .filter(
                models.SupervisorAssignment.supervisor_id == current_user.id,
                models.SupervisorAssignment.class_id == active_enrollment.class_id,
                models.SupervisorAssignment.deleted_at.is_(None),
                models.SupervisorAssignment.start_date <= report_date,
                (models.SupervisorAssignment.end_date == None) | (models.SupervisorAssignment.end_date >= report_date),
            )
            .first()
        )
        if not assignment:
            _not_found()

    # ---- Phase B: reportable state --------------------------------------
    #
    # Past this point the caller is entitled to report on this child, so the
    # remaining failures describe the request rather than the child's existence
    # and can answer specifically.
    if report_date > datetime.now(_JORDAN_TZ).date():
        raise HTTPException(status_code=400, detail="Cannot create reports for future dates")

    ok, missing = validators.check_profile_complete(db, child_id)
    if not ok:
        raise HTTPException(status_code=400, detail={"message": "Child profile incomplete", "missing_fields": missing})

    if not validators.is_working_day(db, active_enrollment.kindergarten_id, report_date):
        raise HTTPException(status_code=400, detail="Date is not a working day for this kindergarten")

    if require_no_existing_report:
        existing = (
            db.query(models.DailyReport)
            .filter(models.DailyReport.child_id == child_id, models.DailyReport.date == report_date)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Daily report for this child and date already exists")

    return active_enrollment


@router.post("/daily-reports/create", status_code=status.HTTP_201_CREATED)
def create_daily_report(
    report_data: DailyReportCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new daily report (Supervisor only)"""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can create daily reports")

    try:
        report_date = date.fromisoformat(report_data.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must use ISO format (YYYY-MM-DD)")
    active_enrollment = _authorize_report_for_child(db, current_user, report_data.child_id, report_date)

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
        notes=report_data.notes,
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
        "status": report.status.value.lower(),
    }


class RosterEntry(BaseModel):
    """One child's row on the class roster. Everything except child_id is
    optional: a row left untouched inherits the shared defaults."""

    child_id: int
    arrival_time: Optional[str] = None
    leave_time: Optional[str] = None
    mood: Optional[str] = None
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    nap_start: Optional[str] = None
    nap_end: Optional[str] = None
    activities: Optional[str] = None
    notes: Optional[str] = None
    health_notes: Optional[str] = None
    skip: bool = False  # absent today, or already reported elsewhere


class RosterBatchRequest(BaseModel):
    """Shared values entered once at the top of the roster, plus per-child rows."""

    date: str
    arrival_time: str
    leave_time: str
    breakfast: Optional[bool] = None
    snack: Optional[bool] = None
    milk: Optional[bool] = None
    lunch: Optional[bool] = None
    children: list[RosterEntry] = Field(min_length=1, max_length=60)

    @field_validator("date")
    @classmethod
    def date_not_in_future(cls, v: str) -> str:
        try:
            parsed = date.fromisoformat(v)
        except ValueError:
            raise ValueError("date must be in YYYY-MM-DD format")
        if parsed > datetime.now(_JORDAN_TZ).date():
            raise ValueError("date cannot be in the future")
        return v

    @field_validator("arrival_time", "leave_time")
    @classmethod
    def time_format_hhmm(cls, v: str) -> str:
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("time must be in HH:MM format (24-hour)")
        return v


@router.post("/daily-reports/batch", status_code=status.HTTP_207_MULTI_STATUS)
def create_daily_reports_batch(
    payload: RosterBatchRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """File a whole class's daily reports in one request (Supervisor only).

    Filing reports one child at a time meant a supervisor walked the same
    twenty-field form once per child, re-entering near-identical arrival, leave
    and meal values every time. Here those are sent once and each row carries
    only its exceptions.

    Deliberately 207, not 201. A class is not all-or-nothing: one child may be
    absent, another may already have a report from this morning, a third may
    have an incomplete profile. Failing the whole batch on any of those would
    make the screen unusable on exactly the days it matters. Every child is
    therefore reported individually and the successes are kept.

    Each child is written inside its own SAVEPOINT so a failure rolls back only
    that row — without it, one IntegrityError would poison the session and lose
    the reports that had already succeeded.

    Authorisation is not relaxed for being a batch: every child goes through the
    same _authorize_report_for_child gates as the single-create endpoint, so a
    child outside the caller's class or kindergarten is refused here too.
    """
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can create daily reports")

    report_date = date.fromisoformat(payload.date)
    results = []
    created = 0

    for entry in payload.children:
        if entry.skip:
            results.append({"child_id": entry.child_id, "status": "skipped", "detail": "Skipped by supervisor"})
            continue

        try:
            with db.begin_nested():
                active_enrollment = _authorize_report_for_child(
                    db, current_user, entry.child_id, report_date
                )
                report = models.DailyReport(
                    child_id=entry.child_id,
                    kindergarten_id=active_enrollment.kindergarten_id,
                    date=report_date,
                    status=models.DailyReportStatus.DRAFT,
                    submitted_by=current_user.id,
                    # Per-child value when the supervisor changed the row,
                    # otherwise the shared value from the top of the roster.
                    arrival_time=entry.arrival_time or payload.arrival_time,
                    leave_time=entry.leave_time or payload.leave_time,
                    mood=entry.mood,
                    health_notes=entry.health_notes,
                    breakfast=entry.breakfast if entry.breakfast is not None else payload.breakfast,
                    snack=entry.snack if entry.snack is not None else payload.snack,
                    milk=entry.milk if entry.milk is not None else payload.milk,
                    lunch=entry.lunch if entry.lunch is not None else payload.lunch,
                    nap_start=entry.nap_start,
                    nap_end=entry.nap_end,
                    activities=entry.activities,
                    notes=entry.notes,
                )
                db.add(report)
                db.flush()
                report_id = report.id
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                detail = detail.get("message", "Rejected")
            results.append(
                {"child_id": entry.child_id, "status": "failed", "code": exc.status_code, "detail": detail}
            )
            continue
        except IntegrityError:
            results.append(
                {
                    "child_id": entry.child_id,
                    "status": "failed",
                    "code": 409,
                    "detail": "Daily report for this child and date already exists",
                }
            )
            continue

        results.append({"child_id": entry.child_id, "status": "created", "report_id": report_id})
        created += 1

    if created:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
    else:
        db.rollback()

    return {
        "date": payload.date,
        "created": created,
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results,
    }


@router.post("/daily-reports/{report_id}/submit")
def submit_daily_report(
    report_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Submit daily report for approval — Supervisor only, must own the report."""
    if current_user.role != models.UserRole.SUPERVISOR:
        raise HTTPException(status_code=403, detail="Only supervisors can submit daily reports")

    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).with_for_update().first()

    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    if report.submitted_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only submit your own reports")

    if report.status != models.DailyReportStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft reports can be submitted")

    validators.validate_daily_report_deadline()

    report.status = models.DailyReportStatus.SUBMITTED
    report.submitted_at = datetime.now(_JORDAN_TZ)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
    }


@router.post("/daily-reports/{report_id}/approve")
def approve_daily_report(
    report_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Approve a daily report (Manager only)"""
    validators.validate_manager_role(current_user)

    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).with_for_update().first()

    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    # Cross-KG scope: managers cannot approve reports outside their kindergarten
    if current_user.role != models.UserRole.ADMIN:
        if report.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=404, detail="Daily report not found")

    if report.status != models.DailyReportStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted reports can be approved")

    report.status = models.DailyReportStatus.APPROVED
    report.approved_by = current_user.id
    report.approved_at = datetime.now(_JORDAN_TZ)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "status": report.status.value.lower(),
        "approved_at": report.approved_at.isoformat() if report.approved_at else None,
    }


@router.get("/daily-reports/child/{child_id}")
def get_child_daily_reports(
    child_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get daily reports for a child (parents only see approved reports)"""
    # Verify child exists
    child = db.query(models.Child).filter(
        models.Child.id == child_id, models.Child.deleted_at.is_(None)
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # If requester is a parent, ensure they own the child
    if current_user.role == models.UserRole.PARENT:
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if not parent_profile or parent_profile.id != child.parent_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif current_user.role != models.UserRole.ADMIN:
        # Supervisors and managers are scoped to their kindergarten
        enrollment = (
            db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.child_id == child_id,
                models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
                models.EnrollmentApplication.status.in_(models.ACTIVE_ENROLLMENT_STATUSES),
            )
            .first()
        )
        if not enrollment:
            raise HTTPException(status_code=403, detail="Child not in your kindergarten scope")

    query = db.query(models.DailyReport).filter(models.DailyReport.child_id == child_id)
    if current_user.role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        query = query.filter(models.DailyReport.kindergarten_id == current_user.kindergarten_id)

    # Explicit manager delivery is the publication boundary.
    if current_user.role == models.UserRole.PARENT:
        query = query.filter(models.DailyReport.status == models.DailyReportStatus.SENT_TO_PARENT)

    reports = query.order_by(models.DailyReport.date.desc()).all()

    def _parent_report_payload(r: models.DailyReport) -> dict:
        meals = [name for name, eaten in (("breakfast", r.breakfast), ("snack", r.snack), ("milk", r.milk), ("lunch", r.lunch)) if eaten]
        nap_time = (
            f"{r.nap_duration_minutes} min" if r.nap_duration_minutes is not None
            else " - ".join(value for value in (r.nap_start, r.nap_end) if value) or None
        )
        return {
                "id": r.id,
                "date": r.date.isoformat(),
                "status": r.status.value,
                "arrival_time": r.arrival_time,
                "leave_time": r.leave_time,
                "activities": r.activities,
                "notes": r.notes,
                "mood": r.mood,
                "health_notes": r.health_notes,
                "breakfast": r.breakfast,
                "snack": r.snack,
                "milk": r.milk,
                "lunch": r.lunch,
                "nap_start": r.nap_start,
                "nap_end": r.nap_end,
                "nap_duration_minutes": r.nap_duration_minutes,
                "meals": ", ".join(meals) if meals else None,
                "nap_time": nap_time,
            }
    return {"reports": [_parent_report_payload(r) for r in reports]}


@router.get("/daily-reports/{report_id}")
def get_daily_report_by_id(
    report_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get a single daily report by ID"""
    report = db.query(models.DailyReport).filter(models.DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Daily report not found")

    # Parents can only see published reports for their own children. Staff are
    # scoped by the report's immutable kindergarten context, not the child's
    # current enrollment, so transfers cannot create cross-tenant disclosure.
    if current_user.role == models.UserRole.PARENT:
        child = db.query(models.Child).filter(
            models.Child.id == report.child_id, models.Child.deleted_at.is_(None)
        ).first()
        parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
        if not parent_profile or not child or child.parent_id != parent_profile.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if report.status != models.DailyReportStatus.SENT_TO_PARENT:
            raise HTTPException(status_code=403, detail="Report not available")
    elif current_user.role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        if not current_user.kindergarten_id or report.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=404, detail="Daily report not found")
    elif current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

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
        "health_notes": getattr(report, "health_notes", None),
        "breakfast": getattr(report, "breakfast", None),
        "snack": getattr(report, "snack", None),
        "milk": getattr(report, "milk", None),
        "lunch": getattr(report, "lunch", None),
        "nap_start": getattr(report, "nap_start", None),
        "nap_end": getattr(report, "nap_end", None),
        "nap_duration_minutes": getattr(report, "nap_duration_minutes", None),
        "submitted_by": report.submitted_by,
    }


# GET /supervisor/daily-reports is now handled by routers/supervisor.py:get_daily_reports
# with improved per-child scoping, date filtering, and stats.


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
    allowed_statuses = {models.DailyReportStatus.SENT_TO_PARENT}
    if report.status not in allowed_statuses:
        raise HTTPException(status_code=403, detail="Report is not accessible")

    # 3. Verify the authenticated parent owns the child referenced in the report
    child = db.query(models.Child).filter(
        models.Child.id == report.child_id, models.Child.deleted_at.is_(None)
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="Report not found")

    parent_profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == current_user.id).first()
    if not parent_profile or child.parent_id != parent_profile.id:
        raise HTTPException(status_code=403, detail="Access denied to this report")

    existing = (
        db.query(models.DailyReportView)
        .filter(
            models.DailyReportView.daily_report_id == report_id,
            models.DailyReportView.parent_user_id == current_user.id,
        )
        .first()
    )
    if existing:
        return {"status": "already_recorded"}

    view = models.DailyReportView(
        daily_report_id=report_id,
        parent_user_id=current_user.id,
    )
    db.add(view)
    db.commit()
    return {"status": "recorded"}
