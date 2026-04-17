"""
Centralized child age policy utilities.

Business rule:
- Minimum child age = 70 days (inclusive)
- Maximum child age = 4 years and 8 months (inclusive)
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_

from config import settings

MIN_CHILD_AGE_DAYS = settings.MIN_CHILD_AGE_DAYS
MAX_CHILD_AGE_MONTHS = settings.MAX_CHILD_AGE_MONTHS


@dataclass(frozen=True)
class ChildAgeBounds:
    """Inclusive DOB bounds for valid children."""
    min_date: date  # Oldest allowed (today minus 4y8m)
    max_date: date  # Youngest allowed (today minus 70 days)


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
    today = today or date.today()
    max_date = today - timedelta(days=MIN_CHILD_AGE_DAYS)
    min_date = _subtract_months(today, MAX_CHILD_AGE_MONTHS)
    return ChildAgeBounds(min_date=min_date, max_date=max_date)


def calculate_age_days(dob: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    return (today - dob).days


def calculate_age_months(dob: date, today: Optional[date] = None) -> int:
    """Full months difference based on calendar boundaries."""
    today = today or date.today()
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
