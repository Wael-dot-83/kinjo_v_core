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


def test_env_templates_match_canonical_policy():
    """No shipped env template may contradict the policy it deploys.

    0768814 lowered the minimum from 70 days to 1 in config.py and
    child_age_policy.py but left the templates at 70. Because a value in an env
    file overrides the code default, every deployment seeded from one silently
    refused children aged 1-69 days.

    This guard deliberately scans *every* tracked env template rather than only
    .env.example: the first version of it checked that one file, so
    .env.local.example and reqMd/.env.local.example kept shipping 70 unnoticed.
    Any template added later is covered automatically.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    templates = sorted(
        p for p in root.rglob("*.env*example*")
        if ".git" not in p.parts and "node_modules" not in p.parts
    )
    templates += sorted(
        p for p in root.rglob(".env*example")
        if ".git" not in p.parts and "node_modules" not in p.parts
    )
    templates = sorted(set(templates))
    assert templates, "no env templates found — the search is broken"

    checked = 0
    for path in templates:
        text = path.read_text(encoding="utf-8")
        for key, expected in (
            ("MIN_CHILD_AGE_DAYS", CANONICAL_MIN_AGE_DAYS),
            ("MAX_CHILD_AGE_MONTHS", CANONICAL_MAX_AGE_MONTHS),
        ):
            match = re.search(rf"^{key}=(\d+)", text, re.M)
            if match is None:
                continue  # a template need not set it; inheriting the default is fine
            checked += 1
            assert int(match.group(1)) == expected, (
                f"{path.relative_to(root)} sets {key}={match.group(1)}, "
                f"contradicting the canonical policy of {expected}"
            )

    assert checked, "no env template declares the age policy — the search is broken"


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


def test_minimum_age_rejection_message_is_translated_for_arabic_callers():
    """The catalogue key must stay parameterised, not interpolated.

    api/enrollment.py built this message with an f-string, so the lookup key
    carried the configured number. The catalogue held
    "Child must be at least 70 days old"; once the policy became 1 day the key
    became "Child must be at least 1 days old", matched nothing, and Arabic
    callers silently received the untranslated English string. Arabic is the
    platform's primary language, so that is a user-facing regression.
    """
    from i18n import gettext

    key = "Child must be at least {days} days old"
    arabic = gettext(key, "ar", days=CANONICAL_MIN_AGE_DAYS)

    assert arabic != key, "the Arabic catalogue no longer resolves this message"
    assert "يجب أن يكون عمر الطفل" in arabic
    assert str(CANONICAL_MIN_AGE_DAYS) in arabic

    # The enrollment endpoint must pass the value as a parameter, never bake it
    # into the key, or the catalogue silently stops matching again.
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "api" / "enrollment.py").read_text(encoding="utf-8")
    assert 'f"Child must be at least {settings.MIN_CHILD_AGE_DAYS} days old"' not in source
    assert "days=settings.MIN_CHILD_AGE_DAYS" in source


def test_non_integer_age_configuration_is_rejected_at_load():
    """A malformed override fails loudly at settings load, never silently to 0."""
    import pydantic

    from config import Settings

    with pytest.raises(pydantic.ValidationError):
        Settings(MIN_CHILD_AGE_DAYS="not-a-number")
