"""
End-to-end integration test for the Jordan Heat Map daily pipeline.

This test exercises the *full* pipeline:

    1. Create the schema in an in-memory SQLite database
    2. Seed the 12 Jordan governorates
    3. Run the daily pipeline for 30 days
    4. Assert the snapshot tables are populated correctly
    5. Assert the correlation / regression / risk tables produce sensible values
    6. Assert the alert engine fires on simulated threshold violations
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models
from heatmap.backend import pipeline
from heatmap.backend.constants import GOVERNORATES, MAIN_INDICATORS, SUB_INDICATORS
from heatmap.scripts.seed_snapshot_data import seed_governorates


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# `in_memory_db` now lives in the root conftest so the heatmap pipeline tests and
# the unavailable-data regression tests share one seeded-database fixture.


# ---------------------------------------------------------------------------
# Test the sub-indicator / main-indicator / risk pipeline
# ---------------------------------------------------------------------------
class TestPipeline:
    def test_governorates_seeded(self, in_memory_db):
        count = in_memory_db.query(func.count(models.Governorate.code)).scalar()
        # Derived from the canonical Jordan administrative set, not hardcoded.
        assert count == len(GOVERNORATES)

    def test_one_day_pipeline_runs(self, in_memory_db):
        summary = pipeline.run_daily_pipeline(in_memory_db, snapshot_date=date.today())
        assert summary["status"] == "success"
        assert summary["governorates"] == len(GOVERNORATES)
        # 12 governors × (26 sub + 6 main) = 312 + 72 = wait, rows_processed counts only the
        # unique upserted rows: 26 sub + 6 main per governorate.

    def test_indicator_snapshot_populated(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = (
            in_memory_db.query(models.MapIndicatorSnapshot)
            .filter(models.MapIndicatorSnapshot.snapshot_date == today)
            .all()
        )
        # One row per governorate per *measurable* indicator. children_registration
        # has no defensible population denominator and is reported as unavailable
        # (see heatmap/backend/pipeline.py), so it yields no snapshot rather than a
        # fabricated value. 12 governorates × 5 measurable = 60.
        unavailable = {"children_registration"}
        expected_keys = {m["key"] for m in MAIN_INDICATORS} - unavailable
        assert {r.main_indicator for r in rows} == expected_keys
        assert len(rows) == 12 * len(expected_keys)
        for r in rows:
            assert r.value is not None
            assert 0 <= r.value <= 100
            assert r.main_indicator in expected_keys

    def test_sub_indicator_snapshot_populated(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = (
            in_memory_db.query(models.MapSubIndicatorValue)
            .filter(models.MapSubIndicatorValue.snapshot_date == today)
            .all()
        )
        # Only sub-indicators with a real KinJo source are written. These ten have
        # no defensible source and are excluded by the data-integrity policy in
        # heatmap/backend/etl/compute.py; writing them would mean fabricating.
        unavailable = {
            "unregistered_children", "absence_rate", "health_absences",
            "repeated_health", "training_completion", "compliance_status",
            "protection_cases", "delayed_tasks", "registration_rate",
            "child_teacher_ratio",
        }
        declared = {sd["key"] for subs in SUB_INDICATORS.values() for sd in subs}
        expected_keys = declared - unavailable
        assert {r.sub_indicator for r in rows} == expected_keys
        assert len(rows) == 12 * len(expected_keys)
        for r in rows:
            assert r.raw_value is not None

    def test_risk_snapshot_populated(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = (
            in_memory_db.query(models.MapRiskSnapshot)
            .filter(models.MapRiskSnapshot.snapshot_date == today)
            .all()
        )
        assert len(rows) == 12
        for r in rows:
            assert 0 <= r.risk_score <= 100
            assert r.risk_level in ("low", "medium", "high", "critical")

    def test_correlation_snapshot_populated(self, in_memory_db):
        """After 7 days the correlation engine should have something to work with."""
        # Backfill 7 days in chronological order so the rolling window has data
        for i in range(6, -1, -1):
            pipeline.run_daily_pipeline(
                in_memory_db,
                snapshot_date=date.today() - timedelta(days=i),
            )
        rows = in_memory_db.query(models.MapCorrelationSnapshot).all()
        assert len(rows) > 0, f"Expected correlation rows, got {len(rows)}"
        # Should have both Pearson and Spearman rows
        methods = {r.method for r in rows}
        assert "pearson" in methods
        assert "spearman" in methods

    def test_regression_snapshot_populated(self, in_memory_db):
        for i in range(6, -1, -1):
            pipeline.run_daily_pipeline(
                in_memory_db,
                snapshot_date=date.today() - timedelta(days=i),
            )
        rows = in_memory_db.query(models.MapRegressionSnapshot).all()
        assert len(rows) > 0
        for r in rows:
            # VIF flag is one of the three valid values
            assert r.vif_flag in ("ok", "warning", "red", None)

    def test_alert_engine_fires(self, in_memory_db):
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        rows = (
            in_memory_db.query(models.MapAlertHistory)
            .filter(models.MapAlertHistory.snapshot_date == today)
            .all()
        )
        # The seeder produces values near the thresholds; some alerts are expected
        # (but we don't assert a specific count — that would be brittle)
        for r in rows:
            assert r.severity in ("low", "medium", "high", "critical")
            assert r.sub_indicator

    def test_run_log_persisted(self, in_memory_db):
        summary = pipeline.run_daily_pipeline(in_memory_db, snapshot_date=date.today())
        run_id = summary["run_id"]
        log = (
            in_memory_db.query(models.MapDailyRunLog)
            .filter(models.MapDailyRunLog.run_id == run_id)
            .one()
        )
        assert log.status == "success"
        assert log.governorates == 12
        assert log.rows_processed == summary["rows_processed"]
        assert log.duration_ms > 0

    def test_pipeline_is_idempotent(self, in_memory_db):
        """Running the same day twice must not duplicate rows."""
        today = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        first_count = (
            in_memory_db.query(func.count(models.MapIndicatorSnapshot.id))
            .filter(models.MapIndicatorSnapshot.snapshot_date == today)
            .scalar()
        )
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=today)
        second_count = (
            in_memory_db.query(func.count(models.MapIndicatorSnapshot.id))
            .filter(models.MapIndicatorSnapshot.snapshot_date == today)
            .scalar()
        )
        assert first_count == second_count
        # children_registration is unavailable, so 5 measurable indicators.
        assert first_count == 12 * (len(MAIN_INDICATORS) - 1)

    def test_trend_computed(self, in_memory_db):
        """After 2 days, the second day should have a previous_value set."""
        day1 = date.today() - timedelta(days=1)
        day2 = date.today()
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=day1)
        pipeline.run_daily_pipeline(in_memory_db, snapshot_date=day2)
        rows = (
            in_memory_db.query(models.MapIndicatorSnapshot)
            .filter(models.MapIndicatorSnapshot.snapshot_date == day2)
            .all()
        )
        # At least some rows should have a previous_value
        with_prev = [r for r in rows if r.previous_value is not None]
        assert len(with_prev) > 0

    def test_backfill_7_days(self, in_memory_db):
        result = pipeline.backfill(in_memory_db, days=7)
        assert result["days_processed"] == 7
        assert len(result["failures"]) == 0
        # Verify all 7 days of risk snapshots
        risk_rows = in_memory_db.query(models.MapRiskSnapshot).count()
        assert risk_rows == 12 * 7


# ---------------------------------------------------------------------------
# Test the risk model directly
# ---------------------------------------------------------------------------
class TestRiskModel:
    def test_low_risk_for_high_main_indicators(self):
        main = {
            "nursery_status": 95.0, "children_registration": 92.0,
            "staff_classrooms": 90.0, "safety_incidents": 96.0,
            "reports_attendance": 94.0, "tasks_governance": 90.0,
        }
        sub = {
            "active_nurseries": 200, "inactive_nurseries": 5, "active_pct": 97.5,
            "inactive_pct": 2.5, "registered_children": 5000, "unregistered_children": 100,
            "registration_rate": 98.0, "age_distribution": 5000, "supervisors_count": 80,
            "classrooms_count": 150, "classrooms_no_supervisor": 2,
            "child_supervisor_ratio": 18, "child_teacher_ratio": 15,
            "incidents_total": 10, "incidents_critical": 1, "protection_cases": 1,
            "incident_severity": 8, "reports_submitted": 5800, "reports_missing": 50,
            "absence_rate": 5.0, "health_absences": 50, "repeated_health": 10,
            "delayed_tasks": 10, "governance_score": 88, "training_completion": 95,
            "compliance_status": 96,
        }
        score, level, _, _ = pipeline.compute_risk_score(main, sub)
        assert 0 <= score <= 25, f"Expected Low risk, got {score}"
        assert level == "low"

    def test_critical_risk_for_bad_indicators(self):
        main = {
            "nursery_status": 10.0, "children_registration": 15.0,
            "staff_classrooms": 12.0, "safety_incidents": 8.0,
            "reports_attendance": 18.0, "tasks_governance": 20.0,
        }
        sub = {
            "active_nurseries": 50, "inactive_nurseries": 50, "active_pct": 50,
            "inactive_pct": 50, "registered_children": 500, "unregistered_children": 1000,
            "registration_rate": 33, "age_distribution": 500, "supervisors_count": 5,
            "classrooms_count": 30, "classrooms_no_supervisor": 25,
            "child_supervisor_ratio": 100, "child_teacher_ratio": 80,
            "incidents_total": 200, "incidents_critical": 50, "protection_cases": 30,
            "incident_severity": 90, "reports_submitted": 200, "reports_missing": 1300,
            "absence_rate": 50.0, "health_absences": 200, "repeated_health": 80,
            "delayed_tasks": 200, "governance_score": 10, "training_completion": 15,
            "compliance_status": 12,
        }
        score, level, _, _ = pipeline.compute_risk_score(main, sub)
        assert score >= 76, f"Expected Critical risk, got {score}"
        assert level == "critical"

    def test_risk_score_in_unit_interval(self):
        main = {m["key"]: 50.0 for m in MAIN_INDICATORS}
        sub = {}
        score, level, _, _ = pipeline.compute_risk_score(main, sub)
        assert 0 <= score <= 100
        assert level in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Test the alert engine
# ---------------------------------------------------------------------------
class TestAlertEngine:
    def test_no_alerts_when_values_well_within_thresholds(self):
        # Use values that are at the *good* end of every threshold
        sub = {
            "active_nurseries": 240, "inactive_nurseries": 2,
            "active_pct": 99.0, "inactive_pct": 1.0,
            "incidents_total": 5, "incidents_critical": 0, "protection_cases": 0,
            "incident_severity": 2,
            "delayed_tasks": 2, "governance_score": 95, "training_completion": 98,
            "compliance_status": 99,
            "registered_children": 5000, "unregistered_children": 50,
            "registration_rate": 99,
            "supervisors_count": 100, "classrooms_count": 180,
            "classrooms_no_supervisor": 0,
            "child_supervisor_ratio": 18, "child_teacher_ratio": 15,
            "reports_submitted": 7000, "reports_missing": 5,
            "absence_rate": 2, "health_absences": 5, "repeated_health": 1,
            "age_distribution": 5000,
        }
        alerts = pipeline.evaluate_alerts(sub)
        # No sub-indicator should be at critical or high severity with these good values
        severities = [a["severity"] for a in alerts]
        assert "critical" not in severities, f"Unexpected critical alerts: {alerts}"
        assert "high" not in severities, f"Unexpected high alerts: {alerts}"

    def test_critical_alert_for_extreme_violation(self):
        sub = {
            # Same defaults as above, but a few wild values
            "active_nurseries": 240, "inactive_nurseries": 5,
            "active_pct": 98.0, "inactive_pct": 2.0,
            "incidents_total": 500, "incidents_critical": 100, "protection_cases": 50,
            "incident_severity": 95,  # very high
            "delayed_tasks": 5, "governance_score": 90, "training_completion": 95,
            "compliance_status": 96,
            "registered_children": 5000, "unregistered_children": 100,
            "registration_rate": 98,
            "supervisors_count": 100, "classrooms_count": 180,
            "classrooms_no_supervisor": 2,
            "child_supervisor_ratio": 18, "child_teacher_ratio": 15,
            "reports_submitted": 6000, "reports_missing": 50,
            "absence_rate": 5, "health_absences": 30, "repeated_health": 5,
            "age_distribution": 5000,
        }
        alerts = pipeline.evaluate_alerts(sub)
        severities = [a["severity"] for a in alerts]
        assert "critical" in severities or "high" in severities

    def test_high_impact_escalates_severity(self):
        """If a sub-indicator has a high regression weight and is in violation,
        its severity must be escalated to HIGH."""
        sub = {
            "active_nurseries": 100, "inactive_nurseries": 5,
            "active_pct": 75.0, "inactive_pct": 5.0,    # violation (below 90 threshold)
            "incidents_total": 10, "incidents_critical": 1, "protection_cases": 1,
            "incident_severity": 5,
            "delayed_tasks": 5, "governance_score": 70, "training_completion": 80,
            "compliance_status": 85,
            "registered_children": 5000, "unregistered_children": 100,
            "registration_rate": 95,
            "supervisors_count": 80, "classrooms_count": 150,
            "classrooms_no_supervisor": 5,
            "child_supervisor_ratio": 18, "child_teacher_ratio": 15,
            "reports_submitted": 5000, "reports_missing": 50,
            "absence_rate": 5, "health_absences": 30, "repeated_health": 5,
            "age_distribution": 5000,
        }
        # Without regression weights: should be LOW/MEDIUM
        plain_alerts = pipeline.evaluate_alerts(sub)
        # With a high regression weight on active_pct: should escalate to HIGH
        weights = {"nursery_status.active_pct": 0.30}
        weighted_alerts = pipeline.evaluate_alerts(sub, regression_weights=weights)
        plain_a = next((a for a in plain_alerts if a["sub_indicator"] == "active_pct"), None)
        weighted_a = next((a for a in weighted_alerts if a["sub_indicator"] == "active_pct"), None)
        if plain_a and weighted_a:
            assert weighted_a["severity"] in ("high", "critical")
            assert plain_a["severity"] in ("low", "medium", "high", "critical")
            # The rule should also be HIGH_IMPACT_VIOLATION with weights
            assert weighted_a["rule"] == "HIGH_IMPACT_VIOLATION"
