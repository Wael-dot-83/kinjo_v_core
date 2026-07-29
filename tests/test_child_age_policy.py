from datetime import date, timedelta

import pytest

from config import settings
from child_age_policy import (
    calculate_age_months,
    get_child_age_bounds,
    is_dob_within_bounds,
)

# Canonical policy, per child_age_policy's docstring and config.py's defaults:
# minimum 1 day, maximum 4 years 8 months (56 months), both inclusive.
CANONICAL_MIN_AGE_DAYS = 1
CANONICAL_MAX_AGE_MONTHS = 56


@pytest.fixture(autouse=True)
def pinned_age_policy(monkeypatch):
    """Pin the age policy so these tests assert the rule, not the local .env.

    MIN_CHILD_AGE_DAYS / MAX_CHILD_AGE_MONTHS are overridable per deployment, and
    a stale `.env` carrying the pre-0768814 value of 70 made the day-boundary
    cases below fail on a developer machine while passing in CI — the outcome
    depended on which environment file happened to be loaded. Pinning makes the
    boundary assertions deterministic; `test_env_example_matches_canonical_policy`
    below is what guards the shipped configuration instead.
    """
    monkeypatch.setattr(settings, "MIN_CHILD_AGE_DAYS", CANONICAL_MIN_AGE_DAYS)
    monkeypatch.setattr(settings, "MAX_CHILD_AGE_MONTHS", CANONICAL_MAX_AGE_MONTHS)


def test_config_default_matches_canonical_policy():
    """config.py's defaults are the policy of record when no env overrides it."""
    from config import Settings

    defaults = Settings.model_fields
    assert defaults["MIN_CHILD_AGE_DAYS"].default == CANONICAL_MIN_AGE_DAYS
    assert defaults["MAX_CHILD_AGE_MONTHS"].default == CANONICAL_MAX_AGE_MONTHS


def test_env_example_matches_canonical_policy():
    """The shipped template must not contradict the policy it deploys.

    0768814 lowered the minimum from 70 days to 1 in config.py and
    child_age_policy.py but left .env.example at 70. Because a value in the env
    file overrides the code default, every deployment seeded from that template
    silently refused children aged 1-69 days. This is the regression guard.
    """
    import re
    from pathlib import Path

    template = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")

    def _value(key: str) -> int:
        match = re.search(rf"^{key}=(\d+)", template, re.M)
        assert match, f"{key} is not set in .env.example"
        return int(match.group(1))

    assert _value("MIN_CHILD_AGE_DAYS") == CANONICAL_MIN_AGE_DAYS
    assert _value("MAX_CHILD_AGE_MONTHS") == CANONICAL_MAX_AGE_MONTHS


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


# ── The policy must actually be configurable ───────────────────────────────

def test_bounds_follow_configuration_changed_after_import(monkeypatch):
    """The bounds read `settings` per call, so a deployment override takes effect.

    child_age_policy used to snapshot MIN_CHILD_AGE_DAYS / MAX_CHILD_AGE_MONTHS
    into module globals at import time. That made the rule look configurable
    while freezing it at whatever `settings` held when the module first loaded,
    so an operator changing the value — or a test pinning it — was silently
    ignored. This is the regression guard: mutate the setting after import and
    the bounds must move with it.
    """
    today = date(2026, 6, 23)

    baseline = get_child_age_bounds(today)
    assert baseline.max_date == date(2026, 6, 22)   # 1 day
    assert baseline.min_date == date(2021, 10, 23)  # 56 months

    monkeypatch.setattr(settings, "MIN_CHILD_AGE_DAYS", 70)
    monkeypatch.setattr(settings, "MAX_CHILD_AGE_MONTHS", 12)
    overridden = get_child_age_bounds(today)

    assert overridden.max_date == date(2026, 4, 14)  # 70 days before today
    assert overridden.min_date == date(2025, 6, 23)  # 12 months before today
    # ...and the superseded 70-day rule genuinely rejects a 1-day-old again,
    # which is precisely what a .env carrying MIN_CHILD_AGE_DAYS=70 did in prod.
    assert is_dob_within_bounds(date(2026, 6, 22), today) is False


def test_bounds_clamp_to_short_month_end():
    """Subtracting months off a 31st lands on the target month's real last day.

    Without clamping this raises ValueError (day out of range for month) rather
    than returning a date, so the enrollment form would 500 on the 29th-31st of
    any month whose target month is shorter.
    """
    # 2026-10-31 minus 56 months -> 2022-02-28 (February 2022 has 28 days)
    assert get_child_age_bounds(date(2026, 10, 31)).min_date == date(2022, 2, 28)
    # ...and onto a leap February, which does have a 29th.
    assert get_child_age_bounds(date(2028, 10, 31)).min_date == date(2024, 2, 29)
    # 31 -> 30 for a 30-day month.
    assert get_child_age_bounds(date(2026, 5, 31)).min_date == date(2021, 9, 30)


def test_non_integer_age_configuration_is_rejected_at_load():
    """A malformed override fails loudly at settings load, never silently to 0."""
    import pydantic

    from config import Settings

    with pytest.raises(pydantic.ValidationError):
        Settings(MIN_CHILD_AGE_DAYS="not-a-number")
