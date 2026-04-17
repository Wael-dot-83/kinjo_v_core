"""
WebSocket endpoint for live analytics dashboard updates (FastAPI)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
from jose import JWTError, jwt
import json
from datetime import datetime, timezone

import models
from config import settings
from database import SessionLocal
from data_quality_service import data_quality_service
from cache_service import dashboard_cache
from monitoring_service import performance_monitor, health_checker

router = APIRouter(tags=["Analytics WebSocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception:
            pass

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
        username = payload.get("sub")
        if not username:
            raise JWTError("missing sub")
    except JWTError:
        await websocket.close(code=1008, reason="invalid_token")
        return

    # Use a fresh database session for the query
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
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

    # Add to active connections
    manager.active_connections.append(websocket)

    try:
        while True:
            try:
                # Get fresh database session for each update
                db = SessionLocal()

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
                    dashboard_data['monitoring'] = {
                        'system_health_score': system_health_score,
                        'overall_health_status': health_status,
                        'performance_metrics': {
                            'cpu_percent': recent_metrics[-1].cpu_percent if recent_metrics else 0,
                            'memory_percent': recent_metrics[-1].memory_percent if recent_metrics else 0,
                            'response_time_avg': recent_metrics[-1].response_time_avg if recent_metrics else 0,
                            'error_rate': recent_metrics[-1].error_rate if recent_metrics else 0,
                            'cache_hit_rate': recent_metrics[-1].cache_hit_rate if recent_metrics else 0
                        } if recent_metrics else {}
                    }

                # Send validated data
                await websocket.send_text(json.dumps({
                    "type": "dashboard_update",
                    "data": dashboard_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "validation_status": "passed"
                }))

            except Exception as e:
                # Send error information
                await websocket.send_text(json.dumps({
                    "type": "validation_error",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "validation_status": "failed"
                }))
            finally:
                db.close()

            # Wait 30 seconds before next update
            await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
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
        func.date(models.Incident.created_at) == datetime.now(timezone.utc).date()
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
    if recent_metrics:
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
    except Exception as e:
        print(f"Background admin cache update failed: {e}")
    finally:
        if db:
            db.close()
