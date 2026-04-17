"""
Tests for the report service functionality
"""
import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch
import models
from report_service import ReportService


class TestReportService:
    """Test cases for ReportService"""

    def test_calculate_date_range_week(self):
        """Test week period calculation"""
        # Test with a Monday
        reference_date = date(2024, 1, 8)  # Monday
        start, end = ReportService.calculate_date_range("week", reference_date)
        assert start == date(2024, 1, 2)  # Previous Monday
        assert end == reference_date

    def test_calculate_date_range_month(self):
        """Test month period calculation (last 30 days)"""
        reference_date = date(2024, 1, 15)
        start, end = ReportService.calculate_date_range("month", reference_date)
        assert start == date(2023, 12, 17)  # 30 days back
        assert end == reference_date

    def test_calculate_date_range_3years(self):
        """Test 3 years rolling period"""
        reference_date = date(2024, 6, 15)
        start, end = ReportService.calculate_date_range("3years", reference_date)
        assert start == date(2021, 6, 16)  # 3 years back + 1 day
        assert end == reference_date

    def test_calculate_date_range_annual(self):
        """Test annual period (current year)"""
        reference_date = date(2024, 6, 15)
        start, end = ReportService.calculate_date_range("annual", reference_date)
        assert start == date(2024, 1, 1)
        assert end == date(2024, 12, 31)

    def test_calculate_date_range_invalid(self):
        """Test invalid period type"""
        with pytest.raises(ValueError, match="Unknown period type"):
            ReportService.calculate_date_range("invalid", date.today())

    def test_generate_incident_report_kindergarten_scope(self):
        """Test report generation for kindergarten scope"""
        # Mock database
        mock_db = Mock()

        # Mock incidents
        mock_incidents = [
            Mock(type=models.IncidentType.INJURY, severity_level=models.SeverityLevel.HIGH, closed_at=None),
            Mock(type=models.IncidentType.BEHAVIOR, severity_level=models.SeverityLevel.LOW, closed_at=datetime.now()),
        ]
        # Make .filter() chainable (returns self so multiple .filter() calls work)
        query_mock = mock_db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.all.return_value = mock_incidents

        # Test - pass db directly to avoid get_db() mocking issues
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        metrics = ReportService.generate_incident_report(
            models.ReportScopeType.KINDERGARTEN, start_date, end_date,
            kindergarten_id=1, db=mock_db
        )

        assert metrics['total_incidents'] == 2
        assert metrics['incidents_by_type']['INJURY'] == 1
        assert metrics['incidents_by_type']['BEHAVIOR'] == 1
        assert metrics['incidents_by_severity']['HIGH'] == 1
        assert metrics['incidents_by_severity']['LOW'] == 1
        assert metrics['open_incidents'] == 1
        assert metrics['closed_incidents'] == 1

    def test_generate_incident_report_governorate_scope(self):
        """Test report generation for governorate scope"""
        # Mock database
        mock_db = Mock()

        # Mock incidents
        mock_incidents = [Mock(type=models.IncidentType.INJURY, severity_level=models.SeverityLevel.MEDIUM, closed_at=None)]
        # Make .filter()/.join()/.group_by() chainable (returns self)
        query_mock = mock_db.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.join.return_value = query_mock
        # group_by returns a separate mock so .all() returns tuples, not incidents
        group_by_mock = Mock()
        query_mock.group_by.return_value = group_by_mock
        group_by_mock.all.return_value = [("KG Test", 1)]
        # First .all() returns incident list, after group_by returns tuples
        query_mock.all.return_value = mock_incidents

        # Test - pass db directly to avoid get_db() mocking issues
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        metrics = ReportService.generate_incident_report(
            models.ReportScopeType.GOVERNORATE, start_date, end_date,
            governorate="Test Governorate", db=mock_db
        )

        assert metrics['total_incidents'] == 1

    def test_generate_incident_report_invalid_scope(self):
        """Test report generation with invalid scope parameters"""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)

        # Missing kindergarten_id for KINDERGARTEN scope
        with pytest.raises(ValueError, match="kindergarten_id required"):
            ReportService.generate_incident_report(
                models.ReportScopeType.KINDERGARTEN, start_date, end_date
            )

        # Missing governorate for GOVERNORATE scope
        with pytest.raises(ValueError, match="governorate required"):
            ReportService.generate_incident_report(
                models.ReportScopeType.GOVERNORATE, start_date, end_date
            )

    def test_get_available_scopes_admin(self):
        """Test getting available scopes for admin user"""
        # Mock database
        mock_db = Mock()

        # Mock governorates
        mock_governorates = [("Governorate1",), ("Governorate2",)]
        mock_db.query.return_value.distinct.return_value.all.return_value = mock_governorates

        # Mock kindergartens
        mock_kindergartens = [
            Mock(id=1, name_ar="KG1", governorate="Governorate1"),
            Mock(id=2, name_ar="KG2", governorate="Governorate2"),
        ]
        mock_db.query.return_value.all.return_value = mock_kindergartens

        # Mock admin user
        admin_user = Mock(role=models.UserRole.ADMIN)

        scopes = ReportService.get_available_scopes(admin_user, db=mock_db)

        # Should include ALL scope, governorates, and kindergartens
        scope_types = [s['type'] for s in scopes]
        assert 'ALL' in scope_types
        assert 'GOVERNORATE' in scope_types
        assert 'KINDERGARTEN' in scope_types

    def test_get_available_scopes_manager(self):
        """Test getting available scopes for manager user"""
        # Mock database
        mock_db = Mock()

        # Mock kindergarten
        mock_kg = Mock(id=1, name_ar="Test KG", governorate="Test Gov")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_kg

        # Mock manager user
        manager_user = Mock(role=models.UserRole.MANAGER, kindergarten_id=1)

        scopes = ReportService.get_available_scopes(manager_user, db=mock_db)

        assert len(scopes) == 1
        assert scopes[0]['type'] == 'KINDERGARTEN'
        assert scopes[0]['id'] == 1