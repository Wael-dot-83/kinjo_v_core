"""
Shared dashboard metrics helpers.

Provides canonical implementations for:
- Soft-delete active scopes
- Attendance calculations (distinct child-days, PRESENT+LATE only)
- Date window resolution and validation

Usage:
    from dashboard_metrics import (
        active_enrollments,
        count_attended_children_on_date,
        count_attended_child_days_in_period,
        DashboardPeriod,
        resolve_dashboard_period,
        seven_day_period,
        chart_days_start,
        _ATTENDED_STATUSES,
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

import models


_JORDAN_TZ = timezone(timedelta(hours=3))

# Canonical set of statuses that count as physical attendance.
# ABSENT and EXCUSED must never inflate attendance figures.
_ATTENDED_STATUSES = (models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE)


# ---------------------------------------------------------------------------
# Soft-delete active scopes
# ---------------------------------------------------------------------------

def active_users(query) -> any:
    """Filter query to non-deleted users."""
    return query.filter(models.User.deleted_at.is_(None))


def active_children(query) -> any:
    """Filter query to non-deleted children."""
    return query.filter(models.Child.deleted_at.is_(None))


def active_enrollments(query) -> any:
    """Filter query to non-soft-deleted enrollment applications."""
    return query.filter(models.EnrollmentApplication.deleted_at.is_(None))


def active_kindergartens(query) -> any:
    """Filter query to non-deleted, non-DELETED-status kindergartens."""
    return query.filter(
        models.Kindergarten.deleted_at.is_(None),
        models.Kindergarten.status != models.KindergartenStatus.DELETED,
    )


def active_incidents(query) -> any:
    """Filter query to non-deleted incidents."""
    return query.filter(models.Incident.deleted_at.is_(None))


def active_supervisor_assignments(query) -> any:
    """Filter query to non-deleted supervisor assignments."""
    return query.filter(models.SupervisorAssignment.deleted_at.is_(None))


# ---------------------------------------------------------------------------
# Attendance helpers
# ---------------------------------------------------------------------------

def count_active_enrolled_children(
    db: Session,
    kindergarten_id: Optional[int] = None,
    class_ids: Optional[List[int]] = None,
) -> int:
    """Count distinct children with ACTIVE enrollment, excluding soft-deleted records.

    Filter by kindergarten_id, class_ids, or both. At least one scope should be
    provided for meaningful results; without scope the query returns the global total.
    """
    q = db.query(func.count(func.distinct(models.EnrollmentApplication.child_id))).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    )
    q = active_enrollments(q)
    if kindergarten_id is not None:
        q = q.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
    if class_ids is not None:
        q = q.filter(models.EnrollmentApplication.class_id.in_(class_ids))
    return q.scalar() or 0


def count_attended_children_on_date(
    db: Session,
    target_date: date,
    kindergarten_id: Optional[int] = None,
    class_ids: Optional[List[int]] = None,
) -> int:
    """Count distinct children with PRESENT or LATE attendance on a specific date."""
    q = db.query(func.count(func.distinct(models.AttendanceLog.child_id))).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
    ).filter(
        models.AttendanceLog.date == target_date,
        models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    )
    q = active_enrollments(q)
    if kindergarten_id is not None:
        q = q.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
    if class_ids is not None:
        q = q.filter(models.EnrollmentApplication.class_id.in_(class_ids))
    return q.scalar() or 0


def count_attended_child_days_in_period(
    db: Session,
    start_date: date,
    end_date: date,
    kindergarten_id: Optional[int] = None,
    class_ids: Optional[List[int]] = None,
) -> int:
    """Count distinct child-days with PRESENT or LATE in a date range.

    One child contributes at most one attended day per calendar date.
    Uses a DISTINCT subquery for correctness across all supported backends.
    """
    base_q = (
        db.query(
            models.AttendanceLog.child_id,
            models.AttendanceLog.date,
        )
        .join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
        )
        .filter(
            models.AttendanceLog.date >= start_date,
            models.AttendanceLog.date <= end_date,
            models.AttendanceLog.status.in_(_ATTENDED_STATUSES),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
    )
    base_q = active_enrollments(base_q)
    if kindergarten_id is not None:
        base_q = base_q.filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id
        )
    if class_ids is not None:
        base_q = base_q.filter(
            models.EnrollmentApplication.class_id.in_(class_ids)
        )

    distinct_subq = base_q.distinct().subquery()
    return db.query(func.count()).select_from(distinct_subq).scalar() or 0


# ---------------------------------------------------------------------------
# Date window helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DashboardPeriod:
    """Typed date range for dashboard queries."""

    start_date: date
    end_date: date

    @property
    def inclusive_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def validate(self, max_days: int = 365) -> None:
        """Reject reversed or excessively large periods."""
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        if self.inclusive_days > max_days:
            raise ValueError(f"Period cannot exceed {max_days} days")


def _today_jordan() -> date:
    """Current date in Jordan timezone."""
    return datetime.now(_JORDAN_TZ).date()


def resolve_dashboard_period(
    period_start: Optional[str],
    period_end: Optional[str],
    range_name: str = "month",
    max_days: int = 90,
) -> DashboardPeriod:
    """Resolve a dashboard period from custom dates or a named range.

    Named ranges:
    - today:     single calendar date
    - week:      today + previous 6 dates (7 days total)
    - quarter:   today - 89 days (90 days total)
    - month:     first of current month to today (default)

    Invalid custom dates fall back to the month range.
    """
    today = _today_jordan()

    if period_start and period_end:
        try:
            start = date.fromisoformat(period_start)
            end = date.fromisoformat(period_end)
        except ValueError:
            start = date(today.year, today.month, 1)
            end = today
        period = DashboardPeriod(start, end)
        period.validate(max_days=max_days)
        return period

    if range_name == "today":
        return DashboardPeriod(today, today)
    elif range_name == "week":
        start = today - timedelta(days=6)
        return DashboardPeriod(start, today)
    elif range_name == "quarter":
        start = today - timedelta(days=89)
        return DashboardPeriod(start, today)
    elif range_name == "month":
        start = date(today.year, today.month, 1)
        return DashboardPeriod(start, today)
    else:
        raise ValueError(f"Unknown range: {range_name}. Use today, week, month, or quarter.")


def seven_day_period(today: Optional[date] = None) -> tuple[date, date]:
    """Return (start, end) for a 7-day inclusive period ending today."""
    if today is None:
        today = _today_jordan()
    start = today - timedelta(days=6)
    return start, today


def chart_days_start(chart_days: int, today: Optional[date] = None) -> date:
    """Return the start date for a chart spanning chart_days inclusive days ending today."""
    if today is None:
        today = _today_jordan()
    return today - timedelta(days=chart_days - 1)
