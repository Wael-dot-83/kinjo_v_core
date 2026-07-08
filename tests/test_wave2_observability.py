"""
Wave 2 Tests: Staff Equity, Governance Quality, Enrollment, Correlation Engine
"""
import pytest
from unittest.mock import MagicMock

from staff_equity_service import StaffEquityService, compute_gini
from governance_quality_service import GovernanceQualityService
from enrollment_analytics_service import EnrollmentAnalyticsService
from correlation_engine import (
    pearson_r,
    spearman_rho,
    interpret_strength,
    CorrelationEngine,
)
from staff_equity_service import staff_equity_service
from governance_quality_service import governance_quality_service
from enrollment_analytics_service import enrollment_analytics_service
from correlation_engine import correlation_engine


class TestStaffEquityService:
    def test_gini_perfect_equality(self):
        assert compute_gini([10.0, 10.0, 10.0, 10.0]) == 0.0

    def test_gini_perfect_inequality(self):
        result = compute_gini([0.0, 0.0, 0.0, 400.0])
        assert result >= 0.74

    def test_gini_moderate_inequality(self):
        result = compute_gini([10.0, 20.0, 30.0, 40.0])
        assert 0.1 < result < 0.5

    def test_gini_empty_list(self):
        assert compute_gini([]) == 0.0

    def test_gini_single_value(self):
        assert compute_gini([100.0]) == 0.0

    def test_workload_gini_no_data(self):
        service = StaffEquityService()
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(filter=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        result = service.teacher_workload_gini(mock_db)
        assert result["classification"] == "no_data"
        assert result["gini"] == 0.0

    def test_equity_index_no_data(self):
        service = StaffEquityService()
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(filter=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        result = service.teacher_workload_equity_index(mock_db)
        assert result["classification"] == "no_data"

    def test_overtime_no_data(self):
        service = StaffEquityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.overtime_tracking(mock_db)
        assert result["avg_daily_hours"] == 0.0

    def test_compliance_no_data(self):
        service = StaffEquityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.staffing_ratio_compliance(mock_db)
        assert result["compliance_rate"] == 100.0

    def test_overall_staff_equity_aggregates(self):
        service = StaffEquityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.overall_staff_equity(mock_db)
        assert "overall_score" in result
        assert "gini" in result
        assert "equity_index" in result
        assert "overtime" in result
        assert "compliance" in result
        assert "status" in result


class TestGovernanceQualityService:
    def test_rejection_rate_no_data(self):
        service = GovernanceQualityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.report_rejection_rate(mock_db)
        assert result["classification"] == "no_data"

    def test_first_pass_no_data(self):
        service = GovernanceQualityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.first_pass_approval_rate(mock_db)
        assert result["first_pass_rate"] == 0.0

    def test_submission_timing_no_data(self):
        service = GovernanceQualityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.submission_timing_distribution(mock_db)
        assert result["classification"] == "no_data"
        assert result["total_reports"] == 0

    def test_morning_routine_no_data(self):
        service = GovernanceQualityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.morning_routine_completion(mock_db)
        assert result["classification"] == "no_data"

    def test_overall_governance_aggregates(self):
        service = GovernanceQualityService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.overall_governance_quality(mock_db)
        assert "overall_score" in result
        assert "rejection_rate" in result
        assert "first_pass_approval" in result
        assert "submission_timing" in result
        assert "morning_routine" in result
        assert "status" in result


class TestEnrollmentAnalyticsService:
    def test_funnel_no_data(self):
        service = EnrollmentAnalyticsService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.enrollment_funnel(mock_db)
        assert result["classification"] == "no_data"
        assert result["total_applications"] == 0

    def test_turnaround_no_data(self):
        service = EnrollmentAnalyticsService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.enrollment_turnaround(mock_db)
        assert result["classification"] == "no_data"
        assert result["avg_hours"] is None

    def test_waitlist_no_data(self):
        service = EnrollmentAnalyticsService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.waitlist_conversion_rate(mock_db)
        assert result["classification"] == "no_data"

    def test_overall_enrollment_aggregates(self):
        service = EnrollmentAnalyticsService()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_query.all.return_value = []
        mock_query.join.return_value = mock_query
        mock_db.query.return_value = mock_query
        result = service.overall_enrollment_analytics(mock_db)
        assert "funnel" in result
        assert "turnaround" in result
        assert "waitlist" in result
        assert "overall_health" in result


class TestCorrelationEngine:
    def test_pearson_r_perfect_positive(self):
        r, p = pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert abs(r - 1.0) < 0.001
        assert p < 0.05

    def test_pearson_r_perfect_negative(self):
        r, p = pearson_r([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert abs(r - (-1.0)) < 0.001
        assert p < 0.05

    def test_pearson_r_insufficient_data(self):
        r, p = pearson_r([1], [2])
        assert r == 0.0
        assert p == 1.0

    def test_spearman_rho_rank_correlation(self):
        r, p = spearman_rho([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert abs(r - 1.0) < 0.001

    def test_spearman_robust_to_outliers(self):
        r, p = spearman_rho([1, 2, 3, 4, 5], [2, 4, 6, 8, 1000])
        assert r > 0.8

    def test_interpret_strength_strong(self):
        assert interpret_strength(0.75) == "strong"
        assert interpret_strength(-0.75) == "strong"

    def test_interpret_strength_medium(self):
        assert interpret_strength(0.55) == "medium"

    def test_interpret_strength_weak(self):
        assert interpret_strength(0.35) == "weak"

    def test_interpret_strength_negligible(self):
        assert interpret_strength(0.1) == "negligible"

    def test_discover_correlations_returns_structure(self, test_db):
        result = correlation_engine.discover_correlations(test_db, days=30)
        assert "total_pairs" in result
        assert "significant_count" in result
        assert "all_correlations" in result
        assert "metadata" in result
