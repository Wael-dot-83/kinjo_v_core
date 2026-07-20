"""Heatmap resilience to unavailable (None) indicator data.

Background: `_upsert_sub_indicator_value` compared a None raw value against a
threshold. The TypeError propagated to `run_daily_pipeline`'s outer handler, so a
single unmeasurable sub-indicator aborted the whole run and wrote **zero** rows
for every governorate.

Contract pinned here:
  * unavailable != 0 — no fabricated measurement is written;
  * one unavailable component never suppresses the measurable ones;
  * failure is local to the smallest unit (one indicator), not the whole run.

Governorate/indicator counts are read from the repository's canonical constants
rather than hardcoded, so adding a governorate cannot silently pass a stale count.
"""
from datetime import date

import pytest

import models
from heatmap.backend import constants as C
from heatmap.backend import pipeline

GOV_COUNT = len(C.GOVERNORATES)
MAIN_KEYS = {m["key"] for m in C.MAIN_INDICATORS}
# children_registration has no defensible population denominator and is reported
# unavailable by design (see pipeline.py) — it is never snapshotted.
UNAVAILABLE_MAIN = {"children_registration"}
MEASURABLE_MAIN = MAIN_KEYS - UNAVAILABLE_MAIN


def _snapshot_rows(db, today):
    return (
        db.query(models.MapIndicatorSnapshot)
        .filter(models.MapIndicatorSnapshot.snapshot_date == today)
        .all()
    )


def _sub_rows(db, today):
    return (
        db.query(models.MapSubIndicatorValue)
        .filter(models.MapSubIndicatorValue.snapshot_date == today)
        .all()
    )


class TestPipelineSurvivesUnavailableData:
    """A pipeline run completes and still produces rows for every governorate."""

    def test_run_succeeds_and_covers_every_governorate(self, in_memory_db):
        today = date.today()
        summary = pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        assert summary["status"] == "success"
        assert summary["governorates"] == GOV_COUNT

        rows = _snapshot_rows(in_memory_db, today)
        covered = {r.governorate_code for r in rows}
        assert len(covered) == GOV_COUNT, (
            f"expected rows for all {GOV_COUNT} governorates, got {len(covered)}"
        )

    def test_unavailable_indicator_does_not_suppress_measurable_ones(self, in_memory_db):
        """The defining regression: one unavailable component must not zero the run."""
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = _snapshot_rows(in_memory_db, today)

        assert rows, "pipeline produced no indicator rows at all"
        present = {r.main_indicator for r in rows}
        assert present == MEASURABLE_MAIN, (
            f"expected every measurable indicator, missing {MEASURABLE_MAIN - present}"
        )

    def test_no_fabricated_zero_written_for_unavailable_indicator(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = _snapshot_rows(in_memory_db, today)

        for key in UNAVAILABLE_MAIN:
            assert not [r for r in rows if r.main_indicator == key], (
                f"{key} is unavailable and must have no row — a 0 row would read "
                "downstream as a genuine measurement"
            )
        assert all(r.value is not None for r in rows)

    def test_written_sub_indicators_never_carry_a_null_raw_value(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = _sub_rows(in_memory_db, today)
        assert rows
        assert all(r.raw_value is not None for r in rows)


class TestUpsertHandlesNoneLocally:
    """Failure is contained to the individual indicator, not the run."""

    def test_none_sub_indicator_value_is_skipped_not_raised(self, in_memory_db):
        """A single None must not raise, and must not become a row."""
        today = date.today()
        sub_key = next(
            d["key"] for defs in C.SUB_INDICATORS.values() for d in defs
        )
        pipeline._upsert_sub_indicator_value(
            in_memory_db, today, "JO-AM", {sub_key: None}
        )
        in_memory_db.commit()
        assert not _sub_rows(in_memory_db, today)

    def test_several_none_values_are_all_skipped(self, in_memory_db):
        today = date.today()
        keys = [d["key"] for defs in C.SUB_INDICATORS.values() for d in defs][:5]
        pipeline._upsert_sub_indicator_value(
            in_memory_db, today, "JO-AM", {k: None for k in keys}
        )
        in_memory_db.commit()
        assert not _sub_rows(in_memory_db, today)

    def test_mixed_available_and_unavailable_writes_only_the_available(self, in_memory_db):
        """The measurable half of a mixed payload must still be recorded."""
        today = date.today()
        defs = [d for group in C.SUB_INDICATORS.values() for d in group]
        available, unavailable = defs[0], defs[1]
        pipeline._upsert_sub_indicator_value(
            in_memory_db,
            today,
            "JO-AM",
            {available["key"]: 5, unavailable["key"]: None},
        )
        in_memory_db.commit()
        written = {r.sub_indicator for r in _sub_rows(in_memory_db, today)}
        assert available["key"] in written
        assert unavailable["key"] not in written

    def test_none_main_indicator_value_is_skipped_not_raised(self, in_memory_db):
        today = date.today()
        pipeline._upsert_indicator_snapshot(
            in_memory_db, today, "JO-AM", {"nursery_status": None}, None
        )
        in_memory_db.commit()
        assert not _snapshot_rows(in_memory_db, today)

    def test_entirely_unavailable_group_yields_no_rows_and_no_exception(self, in_memory_db):
        """An indicator group with nothing measurable degrades quietly to no rows."""
        today = date.today()
        group_key = next(iter(C.SUB_INDICATORS))
        payload = {d["key"]: None for d in C.SUB_INDICATORS[group_key]}
        pipeline._upsert_sub_indicator_value(in_memory_db, today, "JO-AM", payload)
        in_memory_db.commit()
        assert not _sub_rows(in_memory_db, today)


class TestIdempotenceWithUnavailableData:
    def test_rerun_does_not_duplicate_or_lose_rows(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        first = len(_snapshot_rows(in_memory_db, today))
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        second = len(_snapshot_rows(in_memory_db, today))
        assert first == second == GOV_COUNT * len(MEASURABLE_MAIN)
