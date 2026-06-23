"""
Wave 3 Tests: Parent Engagement + Predictive Analytics
"""
import pytest
from unittest.mock import MagicMock

from parent_engagement_service import ParentEngagementService
from predictive_service import PredictiveAnalyticsService


class TestParentEngagementService:
    @pytest.fixture
    def service(self):
        return ParentEngagementService()

    def test_report_view_rate_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.report_view_rate(mock_db)
        assert result["classification"] == "no_data"
        assert result["total_sent"] == 0
        assert result["view_rate"] == 0.0

    def test_parent_login_frequency_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.parent_login_frequency(mock_db)
        assert result["classification"] == "no_data"
        assert result["total_parents"] == 0

    def test_nps_score_no_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.nps_score(mock_db)
        assert result["classification"] == "no_data"
        assert result["response_count"] == 0
        assert result["nps_score"] is None

    def test_nps_score_with_rating(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.scalar.side_effect = [4.5, 20]
        mock_db.query.return_value = mock_query
        result = service.nps_score(mock_db)
        assert "avg_rating" in result
        assert "nps_score" in result
        assert result["response_count"] == 20

    def test_overall_parent_engagement_aggregates(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.overall_parent_engagement(mock_db)
        assert "overall_score" in result
        assert "report_views" in result
        assert "parent_logins" in result
        assert "nps" in result
        assert "status" in result


class TestPredictiveAnalyticsService:
    @pytest.fixture
    def service(self):
        return PredictiveAnalyticsService()

    def test_compute_trend_increasing(self, service):
        values = [10.0, 12.0, 14.0, 16.0, 18.0]
        slope = service._compute_trend(values)
        assert slope > 1.5

    def test_compute_trend_decreasing(self, service):
        values = [20.0, 18.0, 16.0, 14.0, 12.0]
        slope = service._compute_trend(values)
        assert slope < -1.5

    def test_compute_trend_flat(self, service):
        values = [10.0, 10.0, 10.0, 10.0, 10.0]
        slope = service._compute_trend(values)
        assert abs(slope) < 0.01

    def test_compute_trend_empty(self, service):
        assert service._compute_trend([]) == 0.0

    def test_compute_trend_single_point(self, service):
        assert service._compute_trend([5.0]) == 0.0

    def test_attendance_volatility_no_kindergartens(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.attendance_volatility_index(mock_db)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_capacity_runway_no_kindergartens(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        result = service.capacity_runway(mock_db)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_enrollment_projection_requires_kg_id(self, service):
        mock_db = MagicMock()
        result = service.enrollment_projection(mock_db, kindergarten_id=None)
        assert "error" in result

    def test_enrollment_projection_insufficient_data(self, service):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_db.query.return_value = mock_query
        result = service.enrollment_projection(mock_db, kindergarten_id=1)
        assert result["classification"] == "stable"
