"""I-4: child-age policy reads settings at call time, not an import-time snapshot.

Proves get_child_age_bounds reflects a live change to settings.MIN_CHILD_AGE_DAYS /
MAX_CHILD_AGE_MONTHS without a module reload, that restoring the settings restores
behaviour, and that default boundaries + invalid-DOB classification are unchanged.

Settings are changed only via monkeypatch (auto-restored); no process-wide env var
is mutated.
"""
from datetime import date, timedelta

import child_age_policy as cap
from config import settings

_TODAY = date(2026, 8, 1)


def test_default_settings_behaviour_unchanged():
    # Defaults under the test env (conftest sets MIN=1 day, MAX=56 months).
    assert settings.MIN_CHILD_AGE_DAYS == 1
    assert settings.MAX_CHILD_AGE_MONTHS == 56
    bounds = cap.get_child_age_bounds(_TODAY)
    assert bounds.max_date == _TODAY - timedelta(days=1)
    assert bounds.min_date == cap._subtract_months(_TODAY, 56)


def test_min_age_boundary_default():
    # 0 days old -> too_young; exactly 1 day old -> ok.
    assert cap.classify_dob(_TODAY, _TODAY) == "too_young"
    assert cap.classify_dob(_TODAY - timedelta(days=1), _TODAY) == "ok"


def test_max_age_boundary_default():
    oldest_ok = cap._subtract_months(_TODAY, 56)
    assert cap.classify_dob(oldest_ok, _TODAY) == "ok"
    assert cap.classify_dob(oldest_ok - timedelta(days=1), _TODAY) == "too_old"


def test_invalid_dob_classification_default():
    assert cap.classify_dob(_TODAY, _TODAY) == "too_young"           # 0-day-old
    assert cap.classify_dob(date(2000, 1, 1), _TODAY) == "too_old"   # decades old
    assert cap.is_dob_within_bounds(_TODAY - timedelta(days=400), _TODAY) is True


def test_settings_change_after_import_takes_effect_without_reload(monkeypatch):
    before = cap.get_child_age_bounds(_TODAY)
    # Raise the minimum age: youngest-allowed (max_date) moves earlier.
    monkeypatch.setattr(settings, "MIN_CHILD_AGE_DAYS", 30)
    after_min = cap.get_child_age_bounds(_TODAY)
    assert after_min.max_date == _TODAY - timedelta(days=30)
    assert after_min.max_date != before.max_date
    # Shrink the maximum age: oldest-allowed (min_date) moves later.
    monkeypatch.setattr(settings, "MAX_CHILD_AGE_MONTHS", 24)
    after_max = cap.get_child_age_bounds(_TODAY)
    assert after_max.min_date == cap._subtract_months(_TODAY, 24)
    assert after_max.min_date != before.min_date
    # Back-compat module attributes are served live (no stale snapshot).
    assert cap.MIN_CHILD_AGE_DAYS == 30
    assert cap.MAX_CHILD_AGE_MONTHS == 24


def test_restoring_settings_restores_behaviour(monkeypatch):
    baseline = cap.get_child_age_bounds(_TODAY)
    monkeypatch.setattr(settings, "MIN_CHILD_AGE_DAYS", 99)
    assert cap.get_child_age_bounds(_TODAY).max_date != baseline.max_date
    monkeypatch.undo()
    restored = cap.get_child_age_bounds(_TODAY)
    assert restored.max_date == baseline.max_date
    assert restored.min_date == baseline.min_date
    assert cap.MIN_CHILD_AGE_DAYS == 1
