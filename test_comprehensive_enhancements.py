"""
Test suite for comprehensive enhancement implementation
Tests all new features: caching, WebSocket, dashboard customization, filtering, export
"""
import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from models import UserDashboardPreference, UserFilterPreference
from cache_service import CacheService
from realtime_service import ConnectionManager
from dashboard_customization import DashboardCustomizationService
from filter_service import DashboardFilterService
from export_service import ExportService
from datetime import datetime, timedelta
import io

client = TestClient(app)

class TestComprehensiveEnhancements:
    """Test all enhancement features together"""

    def setup_method(self):
        """Setup test data"""
        self.test_user_id = 1
        self.test_role = "manager"

    @patch('cache_service.redis.Redis')
    def test_cache_service_redis_fallback(self, mock_redis):
        """Test Redis fallback to in-memory cache"""
        mock_redis_instance = Mock()
        mock_redis_instance.get.side_effect = Exception("Redis connection failed")
        mock_redis.return_value = mock_redis_instance

        cache = CacheService()
        cache.set("test_key", "test_value", ttl_seconds=60)

        # Should fallback to in-memory cache
        assert cache.get("test_key") == "test_value"

    @pytest.mark.asyncio
    async def test_websocket_connection_manager(self):
        """Test WebSocket connection management"""
        manager = ConnectionManager()

        # Test connection addition
        websocket_mock = AsyncMock()
        await manager.connect(websocket_mock, str(self.test_user_id), self.test_role)

        assert websocket_mock in manager.active_connections[self.test_role]
        assert manager.user_connections[str(self.test_user_id)] == websocket_mock

        # Test disconnection
        manager.disconnect(websocket_mock, str(self.test_user_id), self.test_role)
        assert websocket_mock not in manager.active_connections[self.test_role]
        assert str(self.test_user_id) not in manager.user_connections

    @patch('dashboard_customization.get_db')
    def test_dashboard_customization_service(self, mock_get_db):
        """Test dashboard customization service"""
        mock_db = Mock()
        mock_get_db.return_value = mock_db

        service = DashboardCustomizationService()

        # Mock existing preference
        mock_pref = Mock()
        mock_pref.widget_config = json.dumps([{"id": "kpi", "enabled": True}])
        mock_db.query.return_value.filter.return_value.first.return_value = mock_pref

        # Test get user widgets
        widgets = service.get_user_widgets(self.test_user_id, self.test_role)
        assert len(widgets) > 0
        assert widgets[0]["id"] == "kpi"

    @patch('filter_service.get_db')
    def test_filter_service(self, mock_get_db):
        """Test advanced filtering service"""
        mock_db = Mock()
        mock_get_db.return_value = mock_db

        service = DashboardFilterService()

        # Mock existing filter preference
        mock_pref = Mock()
        mock_pref.filter_config = json.dumps({
            "date_range": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
            "governorates": ["Cairo", "Alexandria"]
        })
        mock_db.query.return_value.filter.return_value.first.return_value = mock_pref

        # Test get user filters
        filters = service.get_user_filters(self.test_user_id)
        assert "date_range" in filters
        assert filters["governorates"] == ["Cairo", "Alexandria"]

    def test_export_service_formats(self):
        """Test export service format generation"""
        service = ExportService()

        test_data = [
            {"name": "Test KPI", "value": 100, "target": 120},
            {"name": "Test KPI 2", "value": 80, "target": 90}
        ]

        # Test CSV export
        csv_result = service._export_kpi_csv(test_data)
        assert "text/csv" in csv_result["content_type"]
        assert "kpi_dashboard_" in csv_result["filename"]

        # Test JSON export
        json_result = service._export_kpi_json(test_data)
        assert "application/json" in json_result["content_type"]
        parsed = json.loads(json_result["content"])
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Test KPI"

    def test_models_user_preferences(self):
        """Test user preference models"""
        # Test UserDashboardPreference
        pref = UserDashboardPreference(
            user_id=self.test_user_id,
            widget_config=json.dumps([{"id": "kpi"}])
        )
        assert pref.user_id == self.test_user_id
        assert json.loads(pref.widget_config)[0]["id"] == "kpi"

        # Test UserFilterPreference
        filter_pref = UserFilterPreference(
            user_id=self.test_user_id,
            filter_config=json.dumps({"date_range": {"start": "2024-01-01"}})
        )
        assert filter_pref.user_id == self.test_user_id
        filters = json.loads(filter_pref.filter_config)
        assert filters["date_range"]["start"] == "2024-01-01"

    @patch('dashboard_api.get_current_user')
    @patch('dashboard_api.get_db')
    def test_dashboard_api_endpoints(self, mock_get_db, mock_get_current_user):
        """Test dashboard API endpoints"""
        mock_get_current_user.return_value = Mock(id=self.test_user_id, role=self.test_role)
        mock_db_instance = Mock()
        mock_get_db.return_value = mock_db_instance

        # Mock no existing preferences
        mock_db_instance.query.return_value.filter.return_value.first.return_value = None

        # Test get dashboard widgets
        response = client.get("/api/dashboard/widgets")
        assert response.status_code == 200
        data = response.json()
        assert "widgets" in data

        # Test update widgets
        update_data = {"widgets": [{"id": "kpi", "enabled": True, "order": 1}]}
        response = client.put("/api/dashboard/widgets", json=update_data)
        assert response.status_code == 200

    @patch('filter_api.get_current_user')
    @patch('filter_api.get_db')
    def test_filter_api_endpoints(self, mock_get_db, mock_get_current_user):
        """Test filter API endpoints"""
        mock_get_current_user.return_value = Mock(id=self.test_user_id, role=self.test_role)
        mock_db_instance = Mock()
        mock_get_db.return_value = mock_db_instance

        # Mock no existing filters
        mock_db_instance.query.return_value.filter.return_value.first.return_value = None

        # Test get saved filters
        response = client.get("/api/dashboard/filters")
        assert response.status_code == 200
        data = response.json()
        assert "filters" in data

        # Test update filters
        filter_data = {
            "date_range": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
            "governorates": ["Cairo"]
        }
        response = client.put("/api/dashboard/filters", json=filter_data)
        assert response.status_code == 200

    @patch('export_api.get_current_user')
    @patch('kpi_service.get_consolidated_kpi_dashboard_data')
    def test_export_api_endpoints(self, mock_get_kpi_data, mock_get_current_user):
        """Test export API endpoints"""
        mock_get_current_user.return_value = Mock(id=self.test_user_id, role=self.test_role)

        # Mock KPI service
        mock_get_kpi_data.return_value = [
            {"name": "Test KPI", "value": 100, "target": 120}
        ]

        # Test CSV export
        response = client.get("/api/export/dashboard/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

        # Test JSON export
        response = client.get("/api/export/dashboard/json")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_websocket_endpoint_exists(self):
        """Test that WebSocket endpoint is properly configured"""
        # Check that the WebSocket route is registered
        routes = [route.path for route in app.routes]
        assert "/ws/dashboard/{user_id}/{role}" in routes

        # Verify it's a WebSocket route
        ws_route = next(route for route in app.routes if route.path == "/ws/dashboard/{user_id}/{role}")
        assert hasattr(ws_route, 'endpoint')  # Should be a WebSocket endpoint

    def test_cache_integration_in_services(self):
        """Test that cache service is properly integrated"""
        # Test cache service initialization
        cache = CacheService()

        # Test basic operations
        cache.set("integration_test", "working", ttl_seconds=60)
        assert cache.get("integration_test") == "working"

        # Test stats
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "total_requests" in stats

    def test_service_initialization(self):
        """Test that all new services can be initialized"""
        try:
            # Test all service imports and initialization
            from cache_service import CacheService
            from realtime_service import ConnectionManager
            from dashboard_customization import DashboardCustomizationService
            from filter_service import DashboardFilterService
            from export_service import ExportService

            cache = CacheService()
            ws_manager = ConnectionManager()
            dashboard_svc = DashboardCustomizationService()
            filter_svc = DashboardFilterService()
            export_svc = ExportService()

            # All services should initialize without errors
            assert cache is not None
            assert ws_manager is not None
            assert dashboard_svc is not None
            assert filter_svc is not None
            assert export_svc is not None

        except ImportError as e:
            pytest.fail(f"Service import failed: {e}")
        except Exception as e:
            pytest.fail(f"Service initialization failed: {e}")

    def test_api_router_integration(self):
        """Test that all new API routers are properly integrated"""
        # Check that all expected routes are present
        routes = [route.path for route in app.routes]

        # Dashboard API routes
        assert "/api/dashboard/widgets" in routes
        assert "/api/dashboard/filters" in routes

        # Export API routes
        assert "/api/export/dashboard/csv" in routes
        assert "/api/export/dashboard/json" in routes
        assert "/api/export/dashboard/excel" in routes
        assert "/api/export/dashboard/pdf" in routes

        # WebSocket route
        assert "/ws/dashboard/{user_id}/{role}" in routes

    def test_error_handling_in_services(self):
        """Test error handling in services"""
        cache = CacheService()

        # Test getting non-existent key
        result = cache.get("non_existent_key")
        assert result is None

        # Test deleting non-existent key
        cache.delete("non_existent_key")  # Should not raise error

        # Test setting with invalid TTL
        cache.set("test", "value", ttl_seconds=-1)  # Should handle gracefully