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


# ── New policy: minimum = 1 day (was 70 days) ──────────────────────────────

def test_child_age_exactly_1_day_is_valid():
    today = date(2026, 6, 23)
    dob = date(2026, 6, 22)  # exactly 1 day old
    assert is_dob_within_bounds(dob, today) is True


def test_child_age_same_day_birth_is_invalid():
    today = date(2026, 6, 23)
    dob = date(2026, 6, 23)  # 0 days old — born today
    assert is_dob_within_bounds(dob, today) is False


def test_child_age_future_birth_date_is_invalid():
    today = date(2026, 6, 23)
    dob = date(2026, 6, 24)  # born tomorrow
    assert is_dob_within_bounds(dob, today) is False


def test_child_age_exactly_4_years_8_months_is_valid():
    today = date(2026, 6, 23)
    dob = date(2021, 10, 23)  # exactly 4 years 8 months ago
    assert is_dob_within_bounds(dob, today) is True


def test_child_age_4_years_8_months_plus_1_day_is_invalid():
    today = date(2026, 6, 23)
    dob = date(2021, 10, 22)  # 1 day past the maximum age
    assert is_dob_within_bounds(dob, today) is False


def test_child_age_boundary_with_leap_year():
    # Feb 29 anchor: 4y8m before 2024-10-29 = 2020-02-29 (leap day exists)
    today = date(2024, 10, 29)
    dob = date(2020, 2, 29)
    assert is_dob_within_bounds(dob, today) is True
    dob_too_old = date(2020, 2, 28)  # one day further back
    assert is_dob_within_bounds(dob_too_old, today) is False


def test_child_age_uses_supplied_as_of_date_not_system_today():
    # Pinned reference date; result must not depend on when the test runs
    as_of = date(2025, 1, 15)
    dob_valid = date(2025, 1, 14)       # exactly 1 day old relative to as_of
    dob_invalid = date(2025, 1, 15)     # same-day birth relative to as_of
    assert is_dob_within_bounds(dob_valid, as_of) is True
    assert is_dob_within_bounds(dob_invalid, as_of) is False
