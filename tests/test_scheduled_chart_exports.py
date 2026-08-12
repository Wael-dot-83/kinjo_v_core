"""Recurring chart exports: scheduling maths, serialisation and API surface."""

from datetime import date, datetime, timedelta, timezone

import pytest

import chart_export_tasks as tasks
import models


def test_window_presets_resolve_to_jordan_dates():
    start, end = tasks.resolve_window("last_30")
    assert (end - start).days == 29
    start, end = tasks.resolve_window("last_7")
    assert (end - start).days == 6
    start, end = tasks.resolve_window("today")
    assert start == end


def test_last_month_is_the_whole_previous_calendar_month():
    start, end = tasks.resolve_window("last_month")
    assert start.day == 1
    assert (end + timedelta(days=1)).day == 1      # end is the month's last day
    assert start.month == end.month


def test_unknown_preset_falls_back_to_the_documented_default():
    assert tasks.resolve_window("nonsense") == tasks.resolve_window("last_30")


def test_next_run_rolls_to_tomorrow_when_the_hour_has_passed():
    after = datetime(2026, 8, 13, 7, 0, tzinfo=timezone.utc)
    assert tasks.compute_next_run("DAILY", 6, after) == datetime(2026, 8, 14, 6, 0)


def test_next_run_is_today_when_the_hour_is_still_ahead():
    after = datetime(2026, 8, 13, 3, 0, tzinfo=timezone.utc)
    assert tasks.compute_next_run("DAILY", 6, after) == datetime(2026, 8, 13, 6, 0)


def test_weekly_and_monthly_space_runs_further_apart():
    after = datetime(2026, 8, 13, 7, 0, tzinfo=timezone.utc)
    daily = tasks.compute_next_run("DAILY", 6, after)
    weekly = tasks.compute_next_run("WEEKLY", 6, after)
    monthly = tasks.compute_next_run("MONTHLY", 6, after)
    assert daily < weekly < monthly
    assert (weekly - daily).days == 6


def test_next_run_is_naive_utc_to_match_the_column():
    """next_run_at is compared against a naive UTC now; a tz-aware value would
    raise on comparison in Postgres."""
    assert tasks.compute_next_run("DAILY", 6).tzinfo is None


def test_csv_carries_a_bom_for_excel():
    text, ext = tasks._serialise([{"name": "حضانة", "count": 3}], "CSV")
    assert ext == "csv"
    assert text.startswith("﻿")
    assert "name" in text


def test_json_export_keeps_arabic_readable():
    text, ext = tasks._serialise([{"name": "حضانة"}], "JSON")
    assert ext == "json"
    assert "حضانة" in text          # not \u-escaped


def test_empty_result_still_produces_a_file_body():
    text, _ = tasks._serialise([], "CSV")
    assert text == "﻿"


def test_model_constraints_are_declared():
    names = {c.name for c in models.ScheduledChartExport.__table__.constraints if c.name}
    assert "ck_sched_export_hour_range" in names
    assert "ck_sched_export_frequency" in names
    assert "ck_sched_export_format" in names


def test_beat_registers_the_sweep():
    from celery_app import celery_app
    assert "run-due-chart-exports" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["run-due-chart-exports"]
    assert entry["task"] == "chart_export_tasks.run_due_exports"
    assert "chart_export_tasks" in celery_app.conf.include


def test_endpoints_are_registered_and_admin_only():
    import charts_api
    paths = {r.path for r in charts_api.router.routes}
    assert any(p.endswith("/scheduled-exports") for p in paths)
    assert any("{schedule_id}" in p for p in paths)
    # The router itself carries require_admin.
    assert charts_api.router.dependencies


def test_audit_actions_exist_for_both_state_changes():
    from audit_actions import AuditAction
    assert AuditAction.SCHEDULED_EXPORT_CREATED
    assert AuditAction.SCHEDULED_EXPORT_DELETED


def test_migration_is_the_single_head():
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "sched_chart_exports_01.py"
    src = p.read_text(encoding="utf-8")
    assert 'down_revision = "audit_details_text_01"' in src
    assert "scheduled_chart_exports" in src
