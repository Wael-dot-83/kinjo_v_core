"""
Centralized child age policy utilities.

Business rule:
- Minimum child age = 1 day (inclusive)
- Maximum child age = 4 years and 8 months (inclusive)
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from utils.time_utils import today_amman as _today
from typing import Optional

from sqlalchemy import and_

from config import settings


def _min_child_age_days() -> int:
    """Minimum child age in days, read from ``settings`` at call time.

    Read live rather than snapshotted at import, so a change to
    ``settings.MIN_CHILD_AGE_DAYS`` (a test override or a runtime reconfiguration)
    takes effect on the next evaluation — no module reload required.
    """
    return settings.MIN_CHILD_AGE_DAYS


def _max_child_age_months() -> int:
    """Maximum child age in months, read from ``settings`` at call time."""
    return settings.MAX_CHILD_AGE_MONTHS


def __getattr__(name: str):
    # Back-compat: this module historically exposed MIN_CHILD_AGE_DAYS /
    # MAX_CHILD_AGE_MONTHS as module attributes. Serve them live so any external
    # reader sees the current settings value, never a stale import-time snapshot.
    if name == "MIN_CHILD_AGE_DAYS":
        return settings.MIN_CHILD_AGE_DAYS
    if name == "MAX_CHILD_AGE_MONTHS":
        return settings.MAX_CHILD_AGE_MONTHS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True)
class ChildAgeBounds:
    """Inclusive DOB bounds for valid children."""
    min_date: date  # Oldest allowed (today minus 4y8m)
    max_date: date  # Youngest allowed (today minus 1 day)


def _subtract_months(base: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be non-negative")

    year = base.year
    month = base.month - months
    while month <= 0:
        month += 12
        year -= 1

    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_child_age_bounds(today: Optional[date] = None) -> ChildAgeBounds:
    """Return inclusive DOB bounds for the child age policy."""
    today = today or _today()
    max_date = today - timedelta(days=_min_child_age_days())
    min_date = _subtract_months(today, _max_child_age_months())
    return ChildAgeBounds(min_date=min_date, max_date=max_date)


def calculate_age_days(dob: date, today: Optional[date] = None) -> int:
    today = today or _today()
    return (today - dob).days


def calculate_age_months(dob: date, today: Optional[date] = None) -> int:
    """Full months difference based on calendar boundaries."""
    today = today or _today()
    months = (today.year - dob.year) * 12 + (today.month - dob.month)
    if today.day < dob.day:
        months -= 1
    return months


def classify_dob(dob: date, today: Optional[date] = None) -> str:
    """Return 'ok', 'too_young', or 'too_old'."""
    bounds = get_child_age_bounds(today)
    if dob > bounds.max_date:
        return "too_young"
    if dob < bounds.min_date:
        return "too_old"
    return "ok"


def is_dob_within_bounds(dob: date, today: Optional[date] = None) -> bool:
    bounds = get_child_age_bounds(today)
    return bounds.min_date <= dob <= bounds.max_date


def build_child_age_filter(column, today: Optional[date] = None):
    """SQLAlchemy filter for DOB bounds."""
    bounds = get_child_age_bounds(today)
    return and_(column >= bounds.min_date, column <= bounds.max_date)


def get_bounds_iso(today: Optional[date] = None) -> dict:
    bounds = get_child_age_bounds(today)
    return {"min_date": bounds.min_date.isoformat(), "max_date": bounds.max_date.isoformat()}
