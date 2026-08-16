"""
Tests for analytics_ws.py - WebSocket analytics endpoints
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import WebSocket
from jose import jwt

from analytics_ws import router, ConnectionManager, websocket_dashboard, get_admin_dashboard_data, _compute_admin_dashboard_data, _update_admin_cache_async
from config import settings
from database import SessionLocal
from auth import create_access_token
import models


class TestConnectionManager:
    """Test ConnectionManager class"""

    def setup_method(self):
        self.manager = ConnectionManager()

    def test_init(self):
        """Test ConnectionManager initialization"""
        assert self.manager.active_connections == []

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting a websocket"""
        mock_ws = AsyncMock()
        await self.manager.connect(mock_ws, "ADMIN")
        assert mock_ws in self.manager.active_connections

    def test_disconnect(self):
        """Test disconnecting a websocket"""
        mock_ws = Mock()
        self.manager._connections[mock_ws] = ("ADMIN", None)
        self.manager.disconnect(mock_ws)
        assert mock_ws not in self.manager.active_connections

    def test_disconnect_not_connected(self):
        """Test disconnecting a websocket that was never connected"""
        mock_ws = Mock()
        self.manager.disconnect(mock_ws)  # Should not raise error

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting to all connections"""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        self.manager._connections[mock_ws1] = ("ADMIN", None)
        self.manager._connections[mock_ws2] = ("ADMIN", None)

        await self.manager.broadcast("test message", admin_only=False)

        mock_ws1.send_text.assert_called_once_with("test message")
        mock_ws2.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_broadcast_with_exception(self):
        """Test broadcasting when a connection raises exception"""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.send_text.side_effect = Exception("Connection error")
        self.manager._connections[mock_ws1] = ("ADMIN", None)
        self.manager._connections[mock_ws2] = ("ADMIN", None)

        await self.manager.broadcast("test message", admin_only=False)

        mock_ws1.send_text.assert_called_once_with("test message")
        mock_ws2.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        """Test sending personal message to specific websocket"""
        mock_ws = AsyncMock()
        await self.manager.send_personal_message("personal message", mock_ws)
        mock_ws.send_text.assert_called_once_with("personal message")

    @pytest.mark.asyncio
    async def test_send_personal_message_exception(self):
        """Test sending personal message when websocket raises exception"""
        mock_ws = AsyncMock(side_effect=Exception("Send error"))
        await self.manager.send_personal_message("personal message", mock_ws)
        mock_ws.send_text.assert_called_once_with("personal message")


class TestWebSocketDashboard:
    """Test WebSocket dashboard endpoint"""

    def setup_method(self):
        self.test_client = TestClient(router)

    def test_websocket_route_exists(self):
        """Test that the websocket route is registered"""
        # This is more of a route registration test
        # The actual WebSocket testing requires a different approach
        pass

    @pytest.mark.asyncio
    async def test_websocket_authentication_missing_token(self):
        """Test WebSocket connection without token"""
        mock_ws = AsyncMock()
        mock_ws.query_params = {}

        await websocket_dashboard(mock_ws)

        mock_ws.accept.assert_called_once()
        mock_ws.close.assert_called_once_with(code=1008, reason="auth_required")

    @pytest.mark.asyncio
    async def test_websocket_authentication_invalid_token(self):
        """Test WebSocket connection with invalid token"""
        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": "invalid_token"}

        await websocket_dashboard(mock_ws)

        mock_ws.accept.assert_called_once()
        mock_ws.close.assert_called_once_with(code=1008, reason="invalid_token")

    @pytest.mark.asyncio
    async def test_websocket_rejects_revoked_access_session(self):
        token = create_access_token({"sub": "admin_user", "role": "ADMIN"})
        claims = jwt.get_unverified_claims(token)
        from session_service import revoke_access_session

        revoke_access_session("admin_user", claims["jti"])
        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch("analytics_ws.SessionLocal") as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db
            mock_user = Mock()
            mock_user.username = "admin_user"
            mock_user.password_changed_at = None
            mock_user.role.value = "ADMIN"
            mock_user.status.value = "ACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            await websocket_dashboard(mock_ws)

        mock_ws.close.assert_called_once_with(code=1008, reason="session_revoked")

    @pytest.mark.asyncio
    async def test_websocket_authentication_user_not_found(self):
        """Test WebSocket connection with valid token but user not found"""
        # Create a valid token for a non-existent user
        token_data = {"sub": "nonexistent_user", "exp": datetime.now().timestamp() + 3600}
        token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = None

            await websocket_dashboard(mock_ws)

            mock_ws.accept.assert_called_once()
            mock_ws.close.assert_called_once_with(code=1008, reason="forbidden")

    @pytest.mark.asyncio
    async def test_websocket_authentication_inactive_user(self):
        """Test WebSocket connection with inactive user"""
        # Create a valid token
        token_data = {"sub": "test_user", "exp": datetime.now().timestamp() + 3600}
        token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db

            # Mock user with inactive status
            mock_user = Mock()
            mock_user.role.value = "ADMIN"
            mock_user.status.value = "INACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            await websocket_dashboard(mock_ws)

            mock_ws.accept.assert_called_once()
            mock_ws.close.assert_called_once_with(code=1008, reason="forbidden")

    @pytest.mark.asyncio
    async def test_websocket_authentication_unauthorized_role(self):
        """Test WebSocket connection with unauthorized role"""
        # Create a valid token
        token_data = {"sub": "test_user", "exp": datetime.now().timestamp() + 3600}
        token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db

            # Mock user with unauthorized role
            mock_user = Mock()
            mock_user.role.value = "PARENT"  # Not allowed
            mock_user.status.value = "ACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            await websocket_dashboard(mock_ws)

            mock_ws.accept.assert_called_once()
            mock_ws.close.assert_called_once_with(code=1008, reason="forbidden")

    @pytest.mark.asyncio
    async def test_websocket_authentication_manager_no_kindergarten(self):
        """Test WebSocket connection with manager having no kindergarten assigned"""
        # Create a valid token
        token_data = {"sub": "test_user", "exp": datetime.now().timestamp() + 3600}
        token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db

            # Mock manager user with no kindergarten
            mock_user = Mock()
            mock_user.role.value = "MANAGER"
            mock_user.status.value = "ACTIVE"
            mock_user.kindergarten_id = None
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            await websocket_dashboard(mock_ws)

            mock_ws.accept.assert_called_once()
            mock_ws.close.assert_called_once_with(code=1008, reason="no_kindergarten_assigned")

    @pytest.mark.asyncio
    async def test_websocket_successful_connection_admin(self):
        """Test successful WebSocket connection for admin user"""
        token = create_access_token({"sub": "admin_user", "role": "ADMIN"})

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws.validate_and_refresh_access_session'), \
             patch('analytics_ws.get_admin_dashboard_data', new_callable=AsyncMock) as mock_get_data, \
             patch('analytics_ws.manager') as mock_manager, \
             patch('asyncio.sleep', side_effect=Exception("Stop loop")):

            mock_manager.connect = AsyncMock()
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_user = Mock()
            mock_user.username = "admin_user"
            mock_user.password_changed_at = None
            mock_user.role.value = "ADMIN"
            mock_user.status.value = "ACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            mock_get_data.return_value = {"test": "data"}

            try:
                await asyncio.wait_for(websocket_dashboard(mock_ws), timeout=0.1)
            except asyncio.TimeoutError:
                pass

            mock_ws.accept.assert_called_once()
            mock_manager.connect.assert_called_once_with(mock_ws, "ADMIN", None)

    @pytest.mark.asyncio
    async def test_websocket_successful_connection_manager(self):
        """Test successful WebSocket connection for manager user"""
        token = create_access_token({"sub": "manager_user", "role": "MANAGER"})

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws.validate_and_refresh_access_session'), \
             patch('analytics_ws.data_quality_service') as mock_dqs, \
             patch('analytics_ws.manager') as mock_manager, \
             patch('asyncio.sleep', side_effect=Exception("Stop loop")):

            mock_manager.connect = AsyncMock()
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_user = Mock()
            mock_user.username = "manager_user"
            mock_user.password_changed_at = None
            mock_user.role.value = "MANAGER"
            mock_user.status.value = "ACTIVE"
            mock_user.kindergarten_id = 1
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            mock_dqs.get_realtime_dashboard_data = AsyncMock(return_value={"test": "data"})

            try:
                await asyncio.wait_for(websocket_dashboard(mock_ws), timeout=0.1)
            except asyncio.TimeoutError:
                pass

            mock_ws.accept.assert_called_once()
            mock_manager.connect.assert_called_once_with(mock_ws, "MANAGER", 1)

    @pytest.mark.asyncio
    async def test_websocket_data_sending(self):
        """Test that dashboard data is sent to websocket"""
        token = create_access_token({"sub": "admin_user", "role": "ADMIN"})

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws.validate_and_refresh_access_session'), \
             patch('analytics_ws.get_admin_dashboard_data', new_callable=AsyncMock) as mock_get_data, \
             patch('analytics_ws.manager') as mock_manager, \
             patch('analytics_ws.performance_monitor') as mock_monitor, \
             patch('analytics_ws.health_checker') as mock_health, \
             patch('asyncio.sleep', side_effect=Exception("Stop loop")):

            mock_manager.connect = AsyncMock()
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_user = Mock()
            mock_user.username = "admin_user"
            mock_user.password_changed_at = None
            mock_user.role.value = "ADMIN"
            mock_user.status.value = "ACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            mock_get_data.return_value = {"test": "dashboard_data"}
            mock_monitor.get_system_health_score.return_value = 85.5
            mock_health.get_overall_health_status.return_value = "healthy"

            try:
                await asyncio.wait_for(websocket_dashboard(mock_ws), timeout=0.1)
            except asyncio.TimeoutError:
                pass

            mock_ws.accept.assert_called_once()
            mock_get_data.assert_called()

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self):
        """Test error handling in websocket data retrieval"""
        token = create_access_token({"sub": "admin_user", "role": "ADMIN"})

        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": token}

        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws.validate_and_refresh_access_session'), \
             patch('analytics_ws.get_admin_dashboard_data', side_effect=Exception("Data error")), \
             patch('analytics_ws.manager') as mock_manager, \
             patch('asyncio.sleep', side_effect=Exception("Stop loop")):

            mock_manager.connect = AsyncMock()
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_user = Mock()
            mock_user.username = "admin_user"
            mock_user.password_changed_at = None
            mock_user.role.value = "ADMIN"
            mock_user.status.value = "ACTIVE"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user

            try:
                await asyncio.wait_for(websocket_dashboard(mock_ws), timeout=0.1)
            except asyncio.TimeoutError:
                pass

            mock_ws.accept.assert_called_once()


class TestAdminDashboardData:
    """Test admin dashboard data functions"""

    @pytest.mark.asyncio
    async def test_get_admin_dashboard_data_cached(self):
        """Test getting cached admin dashboard data"""
        with patch('analytics_ws.dashboard_cache') as mock_cache, \
             patch('analytics_ws._update_admin_cache_async', new_callable=AsyncMock) as mock_update:

            mock_cache.get_dashboard_data = AsyncMock(return_value={"cached": "data"})

            result = await get_admin_dashboard_data(None)

            assert result == {"cached": "data"}
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_admin_dashboard_data_compute(self):
        """Test computing admin dashboard data when not cached"""
        with patch('analytics_ws.dashboard_cache') as mock_cache, \
             patch('analytics_ws._compute_admin_dashboard_data', new_callable=AsyncMock) as mock_compute:

            mock_cache.get_dashboard_data = AsyncMock(return_value=None)
            mock_compute.return_value = {"computed": "data"}

            result = await get_admin_dashboard_data(None)

            assert result == {"computed": "data"}
            mock_compute.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_compute_admin_dashboard_data(self):
        """Test computing admin dashboard data"""
        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws.performance_monitor') as mock_monitor, \
             patch('analytics_ws.health_checker') as mock_health, \
             patch('analytics_ws.dashboard_cache') as mock_cache:

            mock_db = Mock()
            mock_session.return_value = mock_db

            # Mock database queries
            mock_db.query.return_value.filter.return_value.scalar.side_effect = [5, 100, 3, 2, 1]  # kg, children, pending, reports, incidents

            mock_monitor.get_system_health_score.return_value = 85.5
            mock_health.get_overall_health_status.return_value = "healthy"

            mock_cache.set_dashboard_data = AsyncMock()

            result = await _compute_admin_dashboard_data(mock_db)

            # Verify structure
            assert "system_overview" in result
            assert "health_score" in result
            assert "validation_status" in result
            assert "data_quality" in result
            assert "monitoring" in result

            # Verify data
            assert result["system_overview"]["total_kindergartens"] == 5
            assert result["system_overview"]["total_children"] == 100
            assert result["system_overview"]["pending_enrollments"] == 3
            assert result["system_overview"]["pending_reports"] == 2
            assert result["system_overview"]["incidents_today"] == 1

            # Verify cache was called
            mock_cache.set_dashboard_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_admin_cache_async(self):
        """Test background cache update"""
        with patch('analytics_ws.SessionLocal') as mock_session, \
             patch('analytics_ws._compute_admin_dashboard_data', new_callable=AsyncMock) as mock_compute:

            mock_db = Mock()
            mock_session.return_value = mock_db
            mock_compute.return_value = {"updated": "data"}

            await _update_admin_cache_async()

            mock_compute.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_update_admin_cache_async_error(self):
        """Test background cache update with error"""
        with patch('analytics_ws.SessionLocal', side_effect=Exception("DB error")):
            # Should not raise exception - it's caught internally
            await _update_admin_cache_async()
