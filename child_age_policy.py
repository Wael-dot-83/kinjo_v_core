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

# Read from `settings` at call time, not bound here at import.
#
# These were module-level snapshots taken when child_age_policy was first
# imported, which made the policy look configurable while actually freezing it:
# anything that adjusted settings afterwards (a test pinning the rule, a reload)
# was silently ignored, and the frozen copy was the only value the bounds ever
# used. Reading inside the accessors keeps `settings` the single source of truth.
def _min_child_age_days() -> int:
    return settings.MIN_CHILD_AGE_DAYS


def _max_child_age_months() -> int:
    return settings.MAX_CHILD_AGE_MONTHS


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
