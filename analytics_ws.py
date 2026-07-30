"""
WebSocket endpoint for live analytics dashboard updates (FastAPI)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
import logging
from builtins import Exception as BuiltinException
from jose import JWTError, jwt
import json
from datetime import datetime, timezone, timedelta

import models
from config import settings
from database import SessionLocal
from data_quality_service import data_quality_service
from cache_service import dashboard_cache
from monitoring_service import performance_monitor, health_checker
from utils.time_utils import today_amman, jordan_date_range_filter
from utils.time_utils import today_amman, jordan_date_range_filter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics WebSocket"])

class ConnectionManager:
    def __init__(self):
        # Scope-aware connection registry: websocket → (role, kindergarten_id | None)
        self._connections: dict[WebSocket, tuple[str, int | None]] = {}

    @property
    def active_connections(self) -> List[WebSocket]:
        return list(self._connections.keys())

    async def connect(self, websocket: WebSocket, role: str, kindergarten_id: int | None = None):
        # websocket is already accepted before auth; just register the scope.
        self._connections[websocket] = (role, kindergarten_id)

    def disconnect(self, websocket: WebSocket):
        self._connections.pop(websocket, None)

    async def broadcast(self, message: str, admin_only: bool = True):
        """Broadcast to connections.  Defaults to admin-only to prevent cross-scope leakage."""
        disconnected_connections = []
        for connection, (role, _kg_id) in list(self._connections.items()):
            if admin_only and role != "ADMIN":
                continue
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                logger.debug("Client disconnected during broadcast")
                disconnected_connections.append(connection)
            except (RuntimeError, TypeError, BuiltinException) as e:
                logger.warning("Failed to send broadcast message to WebSocket client: %s", str(e), exc_info=False)
                disconnected_connections.append(connection)

        for conn in disconnected_connections:
            self.disconnect(conn)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except WebSocketDisconnect:
            logger.debug("Client disconnected before message delivery")
        except (RuntimeError, TypeError, BuiltinException) as e:
            logger.warning("Failed to send personal message to WebSocket client: %s", str(e), exc_info=False)

manager = ConnectionManager()

@router.websocket("/ws/analytics/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    Authenticated analytics websocket with real-time validated data.
    - Expects JWT in ?token=... query param (same token as /token)
    - Allows ADMIN, MANAGER, and SUPERVISOR roles for dashboard updates
    - Sends validated real-time dashboard data every 30 seconds
    """
    # Must accept the WebSocket first before we can close it with a code
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="auth_required")
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            raise JWTError("purpose-scoped token is not an access token")
        username = payload.get("sub")
        if not username:
            raise JWTError("missing sub")
    except JWTError:
        await websocket.close(code=1008, reason="invalid_token")
        return

    # Use a fresh database session for the query
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(
            models.User.username == username, models.User.deleted_at.is_(None)
        ).first()
        # Handle both enum and string role values
        allowed_role_values = ["ADMIN", "MANAGER", "SUPERVISOR"]

        if not user:
            await websocket.close(code=1008, reason="forbidden")
            return

        # Get role value as string for comparison
        user_role_str = user.role.value if hasattr(user.role, 'value') else str(user.role)
        user_status_str = user.status.value if hasattr(user.status, 'value') else str(user.status)

        if user_status_str != "ACTIVE" or user_role_str not in allowed_role_values:
            await websocket.close(code=1008, reason="forbidden")
            return

        # Determine kindergarten scope
        kindergarten_id = None
        if user_role_str in ["MANAGER", "SUPERVISOR"]:
            if not user.kindergarten_id:
                await websocket.close(code=1008, reason="no_kindergarten_assigned")
                return
            kindergarten_id = user.kindergarten_id

    finally:
        db.close()

    # Add to active connections with scope metadata
    await manager.connect(websocket, user_role_str, kindergarten_id)

    try:
        while True:
            try:
                # Get fresh database session for each update
                db = SessionLocal()

                # Re-validate scope on each cycle to catch mid-session role/kg changes.
                if user_role_str in ("MANAGER", "SUPERVISOR"):
                    scope_user = db.query(models.User).filter(models.User.id == user.id).first()
                    if (
                        scope_user is None
                        or scope_user.status != models.UserStatus.ACTIVE
                        or scope_user.kindergarten_id != kindergarten_id
                    ):
                        await websocket.close(code=4003, reason="scope_changed")
                        return

                # Get real-time validated dashboard data
                if user_role_str == "ADMIN":
                    # For admin, aggregate data across all kindergartens
                    dashboard_data = await get_admin_dashboard_data(db)
                else:
                    # For manager/supervisor, get kindergarten-specific data
                    dashboard_data = await data_quality_service.get_realtime_dashboard_data(
                        db, kindergarten_id, user_role_str
                    )

                # Add monitoring data for admin users
                if user_role_str == "ADMIN":
                    # Get system health and performance metrics
                    system_health_score = performance_monitor.get_system_health_score()
                    recent_metrics = performance_monitor.get_recent_metrics(minutes=5)

                    # Get latest health checks
                    health_status = health_checker.get_overall_health_status()

                    # Add monitoring section to dashboard data
                    latest_metric = recent_metrics[-1] if isinstance(recent_metrics, list) and recent_metrics else None
                    dashboard_data['monitoring'] = {
                        'system_health_score': system_health_score,
                        'overall_health_status': health_status,
                        'performance_metrics': {
                            'cpu_percent': latest_metric.cpu_percent if latest_metric else 0,
                            'memory_percent': latest_metric.memory_percent if latest_metric else 0,
                            'response_time_avg': latest_metric.response_time_avg if latest_metric else 0,
                            'error_rate': latest_metric.error_rate if latest_metric else 0,
                            'cache_hit_rate': latest_metric.cache_hit_rate if latest_metric else 0
                        } if latest_metric else {}
                    }

                # Send validated data
                await websocket.send_text(json.dumps({
                    "type": "dashboard_update",
                    "data": dashboard_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "validation_status": "passed"
                }))

            except (RuntimeError, TypeError, ValueError, AttributeError, BuiltinException) as e:
                logger.error("Error in WebSocket dashboard update: %s", str(e), exc_info=True)
                # Send error information
                try:
                    await websocket.send_text(json.dumps({
                        "type": "validation_error",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "validation_status": "failed"
                    }))
                except (WebSocketDisconnect, RuntimeError, TypeError, BuiltinException) as send_error:
                    logger.warning("Failed to send error message to client: %s", str(send_error), exc_info=False)
            finally:
                db.close()

            # Wait 30 seconds before next update
            try:
                await asyncio.sleep(30)
            except BuiltinException as sleep_error:
                logger.debug("Stopping analytics WebSocket loop: %s", str(sleep_error))
                break

    except WebSocketDisconnect:
        logger.debug("Client disconnected from analytics WebSocket")
    except (RuntimeError, TypeError, ValueError, AttributeError, BuiltinException) as e:
        logger.error("Unexpected error in WebSocket handler: %s", str(e), exc_info=True)
    finally:
        manager.disconnect(websocket)


async def get_admin_dashboard_data(db):
    """Get aggregated dashboard data for admin users with caching"""
    # Check cache first
    cache_key_data = {'type': 'admin_dashboard'}
    cached_data = await dashboard_cache.get_dashboard_data('admin', 0, cache_key_data)

    if cached_data:
        # Return cached data but update in background
        asyncio.create_task(_update_admin_cache_async())
        return cached_data

    # Cache miss - compute fresh data
    return await _compute_admin_dashboard_data(db)

async def _compute_admin_dashboard_data(db):
    """Compute admin dashboard data (extracted for caching)"""
    from sqlalchemy import func

    # Get system-wide statistics
    total_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE
    ).scalar()

    total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
    ).scalar()

    pending_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
        models.EnrollmentApplication.status.in_([
            models.EnrollmentStatus.SUBMITTED,
            models.EnrollmentStatus.PENDING_REVIEW
        ])
    ).scalar()

    pending_reports = db.query(func.count(models.DailyReport.id)).filter(
        models.DailyReport.status == 'draft'
    ).scalar()

    incidents_today = db.query(func.count(models.Incident.id)).filter(
        *jordan_date_range_filter(models.Incident.created_at, today_amman(), today_amman())
    ).scalar()

    # Calculate system health score
    health_score = (
        (100 if total_kindergartens > 0 else 50) * 0.3 +
        (100 if pending_enrollments < 50 else max(0, 100 - (pending_enrollments - 50) * 2)) * 0.3 +
        (100 if pending_reports < 20 else max(0, 100 - (pending_reports - 20) * 5)) * 0.2 +
        (100 if incidents_today < 5 else max(0, 100 - incidents_today * 20)) * 0.2
    )

    data = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'system_overview': {
            'total_kindergartens': total_kindergartens,
            'total_children': total_children,
            'pending_enrollments': pending_enrollments,
            'pending_reports': pending_reports,
            'incidents_today': incidents_today
        },
        'health_score': round(health_score, 2),
        'validation_status': 'passed' if health_score >= 80 else 'warning' if health_score >= 60 else 'critical',
        'data_quality': {
            'overall_quality': round(health_score, 2)
        },
        'monitoring': {
            'system_health_score': performance_monitor.get_system_health_score(),
            'overall_health_status': health_checker.get_overall_health_status(),
            'performance_metrics': {}
        }
    }

    # Add recent performance metrics if available
    recent_metrics = performance_monitor.get_recent_metrics(minutes=5)
    if isinstance(recent_metrics, list) and recent_metrics:
        latest = recent_metrics[-1]
        data['monitoring']['performance_metrics'] = {
            'cpu_percent': round(latest.cpu_percent, 1),
            'memory_percent': round(latest.memory_percent, 1),
            'response_time_avg': round(latest.response_time_avg, 3),
            'error_rate': round(latest.error_rate, 4),
            'cache_hit_rate': round(latest.cache_hit_rate, 3),
            'active_connections': latest.network_connections,
            'timestamp': latest.timestamp.isoformat()
        }

    # Cache the computed data
    cache_key_data = {'type': 'admin_dashboard'}
    await dashboard_cache.set_dashboard_data('admin', 0, cache_key_data, data)

    return data

async def _update_admin_cache_async():
    """Update admin cache asynchronously in background"""
    db = None
    try:
        db = SessionLocal()
        fresh_data = await _compute_admin_dashboard_data(db)
        # Cache is already updated in _compute_admin_dashboard_data
    except (RuntimeError, TypeError, ValueError, AttributeError, BuiltinException) as e:
        logger.error("Background admin cache update failed: %s", e)
    finally:
        if db:
            db.close()
