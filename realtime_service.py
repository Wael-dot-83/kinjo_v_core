"""
Real-time WebSocket service for dashboard updates
"""
import json
import logging
import asyncio
from typing import Dict, List, Set
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from database import get_db
# from kpi_service import get_basic_kpi_data
from monitoring_service import performance_monitor

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager for real-time dashboard updates"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "admin": set(),
            "manager": set(),
            "supervisor": set(),
            "parent": set()
        }
        self.user_connections: Dict[str, WebSocket] = {}  # user_id -> websocket

    async def connect(self, websocket: WebSocket, user_id: str, role: str):
        """Connect a user to their role-based channel"""
        await websocket.accept()

        # Add to role-based connections
        if role not in self.active_connections:
            self.active_connections[role] = set()
        self.active_connections[role].add(websocket)

        # Track user connection
        self.user_connections[user_id] = websocket

        # Record metrics
        performance_monitor.collector.record_websocket_connection(connected=True)
        performance_monitor.collector.record_dashboard_session(active=True)

        logger.info(f"User {user_id} ({role}) connected via WebSocket")

    def disconnect(self, websocket: WebSocket, user_id: str = None, role: str = None):
        """Disconnect a user from WebSocket"""
        # Remove from role-based connections
        for role_connections in self.active_connections.values():
            role_connections.discard(websocket)

        # Remove from user connections
        if user_id and user_id in self.user_connections:
            del self.user_connections[user_id]

        # Record metrics
        performance_monitor.collector.record_websocket_connection(connected=False)
        performance_monitor.collector.record_dashboard_session(active=False)

        logger.info(f"User {user_id} ({role}) disconnected from WebSocket")

    async def broadcast_to_role(self, role: str, message: dict):
        """Broadcast message to all users of a specific role"""
        if role not in self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections[role]:
            try:
                await connection.send_json(message)
                # Record successful message
                performance_monitor.collector.record_websocket_message()
            except (WebSocketDisconnect, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to send message to {role} connection: {e}")
                disconnected.add(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.active_connections[role].discard(conn)

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to specific user"""
        if user_id in self.user_connections:
            try:
                await self.user_connections[user_id].send_json(message)
                # Record successful message
                performance_monitor.collector.record_websocket_message()
            except (WebSocketDisconnect, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to send message to user {user_id}: {e}")
                # Clean up failed connection
                del self.user_connections[user_id]

    async def broadcast_kpi_update(self, role: str = None):
        """Broadcast KPI data updates to connected clients"""
        db_gen = get_db()
        db = None
        try:
            # Get fresh KPI data
            db = next(db_gen)
            kpi_data = {"message": "KPI data temporarily disabled"}

            message = {
                "type": "kpi_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": kpi_data
            }

            if role:
                await self.broadcast_to_role(role, message)
            else:
                # Broadcast to all roles
                for role_name in self.active_connections.keys():
                    await self.broadcast_to_role(role_name, message)

            logger.info(f"KPI update broadcasted to {role or 'all roles'}")

        except (RuntimeError, StopIteration, TypeError, ValueError) as e:
            logger.error(f"Failed to broadcast KPI update: {e}")
        finally:
            try:
                if db is not None:
                    db.close()
                db_gen.close()
            except RuntimeError:
                pass

    async def broadcast_alert(self, alert_type: str, title: str, message: str, priority: str = "info", roles: List[str] = None):
        """Broadcast alert/notification to specified roles"""
        alert_message = {
            "type": "alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": {
                "type": alert_type,
                "title": title,
                "message": message,
                "priority": priority
            }
        }

        target_roles = roles or list(self.active_connections.keys())

        for role in target_roles:
            await self.broadcast_to_role(role, alert_message)

        logger.info(f"Alert broadcasted to roles: {target_roles}")

    async def send_personal_notification(self, user_id: str, title: str, message: str, notification_type: str = "info"):
        """Send personal notification to specific user"""
        notification = {
            "type": "notification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notification": {
                "title": title,
                "message": message,
                "type": notification_type
            }
        }

        await self.send_to_user(user_id, notification)
        logger.info(f"Personal notification sent to user {user_id}")


# Global connection manager instance
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, user_id: str, role: str):
    """WebSocket endpoint for real-time dashboard updates"""
    await manager.connect(websocket, user_id, role)

    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_json()

            # Handle client messages (e.g., subscription requests, ping)
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            elif data.get("type") == "subscribe":
                # Client wants to subscribe to specific data streams
                subscriptions = data.get("subscriptions", [])
                await websocket.send_json({
                    "type": "subscribed",
                    "subscriptions": subscriptions,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"User {user_id} subscribed to: {subscriptions}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id, role)
    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id, role)


# Background task for periodic KPI updates
async def periodic_kpi_updates():
    """Background task to send periodic KPI updates"""
    while True:
        try:
            # Update KPIs for all roles
            await manager.broadcast_kpi_update()

            # Wait for next update (every 5 minutes)
            await asyncio.sleep(300)

        except (RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Error in periodic KPI updates: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying


# Function to trigger real-time updates when data changes
async def notify_kpi_change(role: str = None):
    """Notify connected clients of KPI data changes"""
    await manager.broadcast_kpi_update(role)


async def notify_system_alert(alert_type: str, title: str, message: str, priority: str = "warning", roles: List[str] = None):
    """Send system-wide alerts"""
    await manager.broadcast_alert(alert_type, title, message, priority, roles)


# WebSocket endpoint handler
async def websocket_endpoint(websocket: WebSocket, user_id: str, role: str):
    """Handle WebSocket connections for real-time dashboard updates"""
    await manager.connect(websocket, user_id, role)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "message": f"Connected as {role}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Keep connection alive and listen for client messages
        while True:
            try:
                # Wait for client messages (optional - clients can send commands)
                data = await websocket.receive_text()

                # Handle client commands if needed
                try:
                    message = json.loads(data)
                    command = message.get("command")

                    if command == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    elif command == "request_update":
                        # Send immediate KPI update
                        await manager.send_kpi_update_to_user(user_id, role)

                except json.JSONDecodeError:
                    # Ignore invalid JSON
                    pass

            except WebSocketDisconnect:
                break

    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        manager.disconnect(websocket, user_id, role)