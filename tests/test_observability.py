"""
Tests for the observability, telemetry, and analytics quality components
introduced by the Data Science & Analytics Plan (Wave 1).
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from alert_quality_service import AlertQualityService
from data_quality_enhanced import EnhancedDataQualityService
from staff_equity_service import StaffEquityService, compute_gini
from governance_quality_service import GovernanceQualityService
from enrollment_analytics_service import EnrollmentAnalyticsService
from correlation_engine import (
    pearson_r,
    spearman_rho,
    interpret_strength,
    CorrelationEngine,
)
from telemetry_service import (
    _sanitize_page,
    _sanitize_message,
    _classify_vital_rating,
    _safe_vital_value,
    P95Calculator,
)


class TestAlertQualityService:
    @pytest.fixture
    def service(self):
        return AlertQualityService()

    def test_snr_no_data_returns_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.signal_to_noise_ratio(mock_db, days=30)
        assert result["classification"] == "no_data"
        assert result["total_alerts"] == 0

    def test_snr_all_critical_returns_high_ratio(self, service):
        mock_db = MagicMock()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.count.return_value = 10
        mock_db.query.return_value = query_chain

        result = service.signal_to_noise_ratio(mock_db, days=30)
        assert result["classification"] == "healthy"
        assert result["snr"] == 1.0

    def test_snr_mostly_low_severity_returns_degraded(self, service):
        mock_db = MagicMock()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.count.side_effect = [100, 15]
        mock_db.query.return_value = query_chain

        result = service.signal_to_noise_ratio(mock_db, days=30)
        assert result["total_alerts"] == 100
        assert result["critical_high"] == 15
        assert result["classification"] == "degraded"
        assert result["snr"] < 0.4

    def test_false_positive_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.false_positive_rate(mock_db)
        assert result["classification"] == "no_data"

    def test_time_to_acknowledge_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = service.time_to_acknowledge(mock_db)
        assert result["avg_minutes"] is None
        assert result["acknowledged_count"] == 0

    def test_time_to_acknowledge_with_data(self, service):
        now = datetime.now(timezone.utc)
        triggered = now - timedelta(minutes=10)
        acknowledged = now

        row1 = MagicMock()
        row1.triggered_at = triggered
        row1.acknowledged_at = acknowledged

        row2 = MagicMock()
        row2.triggered_at = triggered
        row2.acknowledged_at = acknowledged

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [row1, row2]
        mock_db.query.return_value = mock_query

        result = service.time_to_acknowledge(mock_db)
        assert result["avg_minutes"] == pytest.approx(10.0, abs=0.1)
        assert result["acknowledged_count"] == 2

    def test_overall_alert_quality_computes_all(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = service.overall_alert_quality(mock_db)
        assert "overall_score" in result
        assert "health" in result
        assert "signal_to_noise" in result
        assert "false_positive_rate" in result
        assert "time_to_acknowledge" in result


class TestEnhancedDataQualityService:
    @pytest.fixture
    def service(self):
        return EnhancedDataQualityService()

    def test_freshness_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = None
        mock_db.query.return_value = mock_query

        result = service.freshness_latency(mock_db)
        assert result["status"] == "no_data"
        assert result["hours_since_last_report"] is None

    def test_freshness_fresh(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_db.query.return_value = mock_query

        result = service.freshness_latency(mock_db)
        assert result["status"] == "fresh"
        assert result["hours_since_last_report"] <= 2.0

    def test_freshness_critical(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = datetime.now(timezone.utc) - timedelta(hours=24)
        mock_db.query.return_value = mock_query

        result = service.freshness_latency(mock_db)
        assert result["status"] == "critical"
        assert result["hours_since_last_report"] > 12.0

    def test_completeness_per_kg(self, service):
        mock_db = MagicMock()

        kg_mock = MagicMock()
        kg_mock.id = 1
        kg_mock.name_ar = "Test KG"
        kg_mock.governorate = "Amman"

        base_query = MagicMock()
        base_query.filter.return_value = base_query
        base_query.all.return_value = [kg_mock]

        # Batch children query: .filter().group_by().all() → [(kg_id, count)]
        child_query = MagicMock()
        child_query.filter.return_value = child_query
        child_query.group_by.return_value = child_query
        child_query.all.return_value = [(1, 10)]

        # Batch reports query: .filter().group_by().all() → [(kg_id, count)]
        report_query = MagicMock()
        report_query.filter.return_value = report_query
        report_query.group_by.return_value = report_query
        report_query.all.return_value = [(1, 8)]

        mock_db.query.side_effect = [base_query, child_query, report_query]

        result = service.completeness_per_kg(mock_db)
        assert len(result) == 1
        assert result[0]["completeness_percent"] == 80.0
        assert result[0]["kindergarten_id"] == 1

    def test_cross_entity_consistency_no_issues(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.scalar.side_effect = [100, 100, 0, 1000, 0, 0]
        mock_db.query.return_value = mock_query

        result = service.cross_entity_consistency(mock_db)
        assert "consistency_score" in result
        assert "enrolled_count" in result

    def test_uniqueness_check_clean(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.having.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.filter.return_value = mock_query
        mock_db.query.return_value = mock_query

        result = service.uniqueness_check(mock_db)
        assert result["uniqueness_score"] >= 99.0
        assert result["status"] == "unique"

    def test_validity_check_clean(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.validity_check(mock_db)
        assert result["validity_score"] == 100.0
        assert result["status"] == "valid"

    def test_overall_quality_aggregates_all(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = None
        mock_query.count.return_value = 0
        mock_query.all.return_value = []
        mock_query.distinct.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.having.return_value = mock_query
        mock_db.query.return_value = mock_query

        result = service.compute_overall_quality(mock_db)
        assert "overall_score" in result
        assert "freshness" in result
        assert "completeness" in result
        assert "consistency" in result
        assert "uniqueness" in result
        assert "validity" in result
        assert "status" in result
        assert result["status"] in ("excellent", "good", "fair", "poor")


class TestTelemetryHelpers:
    def test_sanitize_page_strips_query(self):
        assert _sanitize_page("/admin/dashboard?foo=bar") == "/admin/dashboard"
        assert _sanitize_page("/admin/dashboard#section") == "/admin/dashboard"

    def test_sanitize_page_empty(self):
        assert _sanitize_page("") == "/"
        assert _sanitize_page(None) == "/"

    def test_sanitize_message_strips_pii(self):
        msg = "Error at file:///home/user/app.py and https://example.com/api"
        result = _sanitize_message(msg)
        assert "[path]" in result
        assert "[url]" in result
        assert "file:///" not in result
        assert "https://example.com" not in result

    def test_sanitize_message_strips_email(self):
        msg = "Login failed for user@example.com"
        result = _sanitize_message(msg)
        assert "[email]" in result
        assert "user@example.com" not in result

    def test_sanitize_message_truncates(self):
        msg = "x" * 1000
        result = _sanitize_message(msg)
        assert len(result) <= 500

    def test_classify_lcp(self):
        assert _classify_vital_rating("lcp", 1500) == "good"
        assert _classify_vital_rating("lcp", 3000) == "needs-improvement"
        assert _classify_vital_rating("lcp", 5000) == "poor"

    def test_classify_fid(self):
        assert _classify_vital_rating("fid", 50) == "good"
        assert _classify_vital_rating("fid", 200) == "needs-improvement"
        assert _classify_vital_rating("fid", 500) == "poor"

    def test_classify_cls(self):
        assert _classify_vital_rating("cls", 0.05) == "good"
        assert _classify_vital_rating("cls", 0.2) == "needs-improvement"
        assert _classify_vital_rating("cls", 0.5) == "poor"

    def test_safe_vital_value_clamps(self):
        assert _safe_vital_value("lcp", -100) == 0.0
        assert _safe_vital_value("lcp", 20000) == 10000.0
        assert _safe_vital_value("cls", -1) == 0.0
        assert _safe_vital_value("cls", 10) == 5.0

    def test_safe_vital_value_within_range(self):
        assert _safe_vital_value("lcp", 1500) == 1500.0
        assert _safe_vital_value("fid", 50) == 50.0
        assert _safe_vital_value("cls", 0.1) == 0.1


class TestP95Calculator:
    def test_empty_stats(self):
        calc = P95Calculator()
        stats = calc.stats("test")
        assert stats["count"] == 0
        assert stats["p95"] == 0.0

    def test_single_value(self):
        calc = P95Calculator()
        calc.add("ep1", 100.0)
        stats = calc.stats("ep1")
        assert stats["count"] == 1
        assert stats["avg"] == 100.0

    def test_p95_calculation(self):
        calc = P95Calculator()
        for i in range(100):
            calc.add("ep1", float(i))
        stats = calc.stats("ep1")
        assert stats["count"] == 100
        assert stats["p95"] == 95.0

    def test_max_entries_limit(self):
        calc = P95Calculator(max_entries=10)
        for i in range(20):
            calc.add("ep1", float(i))
        stats = calc.stats("ep1")
        assert stats["count"] == 10

    def test_multiple_keys(self):
        calc = P95Calculator()
        calc.add("ep1", 100.0)
        calc.add("ep2", 200.0)
        assert calc.all_keys() == ["ep1", "ep2"]

    def test_clear(self):
        calc = P95Calculator()
        calc.add("ep1", 100.0)
        calc.clear()
        assert calc.all_keys() == []


class TestCeleryTaskStats:
    def test_get_task_stats_empty(self):
        from celery_app import get_task_stats
        stats = get_task_stats()
        assert "completed" in stats
        assert "failed" in stats
        assert "avg_duration_ms" in stats
        assert "p50_duration_ms" in stats
        assert "p95_duration_ms" in stats
