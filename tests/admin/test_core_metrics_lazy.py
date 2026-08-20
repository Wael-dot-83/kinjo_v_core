"""ADMIN-SCORING (Phase 2) — _collect_core_metrics defers what it is not asked for.

Measures SQL statements actually issued, rather than asserting that laziness
exists in the abstract. A lazy layer nobody can measure is not an optimisation,
it is a claim.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import event

import admin_reports_api
from admin_reports_api import ReportLevel, _build_scope_filters, _collect_core_metrics


@contextmanager
def count_queries(session):
    """Count SELECTs issued on *session*'s connection inside the block."""
    statements = []
    engine = session.get_bind()

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _before)


@pytest.fixture
def scope():
    return _build_scope_filters(ReportLevel.JORDAN, None, None, None, None, None)


@pytest.fixture
def window():
    from datetime import date, timedelta

    today = date.today()
    return today - timedelta(days=30), today


class TestLazyMetrics:
    def test_reads_look_like_a_dict(self, test_db, scope, window, sample_kindergarten):
        metrics = _collect_core_metrics(test_db, scope, *window)

        assert metrics["total_children"] == 0
        assert "compliance_score" in metrics
        assert metrics.get("total_kindergartens") == 1

    def test_missing_key_still_raises_keyerror(self, test_db, scope, window):
        metrics = _collect_core_metrics(test_db, scope, *window)

        with pytest.raises(KeyError):
            metrics["no_such_metric"]

    def test_deferred_sections_cost_nothing_until_read(
        self, test_db, scope, window, sample_kindergarten
    ):
        with count_queries(test_db) as during_build:
            metrics = _collect_core_metrics(test_db, scope, *window)
            built = len(during_build)

            metrics["total_children"]
            metrics["age_buckets"]
            after_eager_reads = len(during_build)

            metrics["duplicate_children"]
            after_duplicates = len(during_build)

        # Reading eager keys issues nothing further...
        assert after_eager_reads == built
        # ...but reading a deferred one does.
        assert after_duplicates > after_eager_reads

    def test_deferred_sections_are_memoized(
        self, test_db, scope, window, sample_kindergarten
    ):
        metrics = _collect_core_metrics(test_db, scope, *window)

        with count_queries(test_db) as issued:
            metrics["duplicate_children"]
            first = len(issued)
            for _ in range(5):
                metrics["duplicate_children"]

            assert len(issued) == first

    def test_an_endpoint_that_wants_age_buckets_skips_the_compliance_queries(
        self, test_db, scope, window, sample_kindergarten
    ):
        """The defect this change addresses.

        Every caller used to pay for the duplicate-children scan, the
        multi-class probe and the daily-report recency probe, whatever it
        actually needed.
        """
        with count_queries(test_db) as minimal:
            metrics = _collect_core_metrics(test_db, scope, *window)
            metrics["age_buckets"]
            metrics["gender_counts"]
            minimal_count = len(minimal)

        with count_queries(test_db) as everything:
            metrics = _collect_core_metrics(test_db, scope, *window)
            metrics["compliance_score"]
            metrics["data_quality_score"]
            full_count = len(everything)

        assert minimal_count < full_count

    def test_reading_everything_still_works(
        self, test_db, scope, window, sample_kindergarten
    ):
        """Laziness must not change any value, only when it is computed."""
        metrics = _collect_core_metrics(test_db, scope, *window)

        assert 0.0 <= metrics["compliance_score"] <= 100.0
        assert 0.0 <= metrics["data_quality_score"] <= 100.0
        assert set(metrics["data_quality"]["dimensions"]) == {
            "completeness", "timeliness", "validity", "uniqueness"
        }
        assert isinstance(metrics["by_governorate"], list)
        assert isinstance(metrics["by_city"], list)
        assert isinstance(metrics["by_area"], list)

    def test_geography_rollups_share_one_computation(
        self, test_db, scope, window, sample_kindergarten
    ):
        """All three rollups come from a single pass, not three."""
        metrics = _collect_core_metrics(test_db, scope, *window)

        metrics["by_governorate"]
        computed = metrics["_geography"]

        assert computed["by_city"] is not None
        assert metrics["by_city"] is computed["by_city"]
        assert metrics["by_area"] is computed["by_area"]

    def test_lazy_bundle_is_a_mapping(self, test_db, scope, window):
        from collections.abc import Mapping

        metrics = _collect_core_metrics(test_db, scope, *window)

        assert isinstance(metrics, Mapping)
        assert isinstance(metrics, admin_reports_api._LazyMetrics)
        assert len(metrics) > 0
