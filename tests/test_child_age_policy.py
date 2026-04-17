from datetime import date, timedelta

import pytest

from child_age_policy import (
    calculate_age_months,
    get_child_age_bounds,
    is_dob_within_bounds,
)


def test_bounds_inclusive():
    today = date(2026, 2, 6)
    bounds = get_child_age_bounds(today)

    assert is_dob_within_bounds(bounds.min_date, today) is True
    assert is_dob_within_bounds(bounds.max_date, today) is True
    assert is_dob_within_bounds(bounds.min_date - timedelta(days=1), today) is False
    assert is_dob_within_bounds(bounds.max_date + timedelta(days=1), today) is False


def test_calculate_age_months_day_boundary():
    today = date(2026, 2, 6)
    dob = date(2022, 2, 7)
    assert calculate_age_months(dob, today) == 47


def test_calculate_age_months_leap_day():
    today = date(2024, 2, 28)
    dob = date(2020, 2, 29)
    assert calculate_age_months(dob, today) == 47
