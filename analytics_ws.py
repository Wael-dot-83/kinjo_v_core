"""
WebSocket endpoint for live analytics dashboard updates (FastAPI)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List
import models
from database import get_db
from dependencies import get_current_user
import asyncio

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
        dead: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.disconnect(conn)

manager = ConnectionManager()

@router.websocket("/ws/analytics/dashboard")
async def websocket_dashboard(
    websocket: WebSocket,
    current_user: models.User = Depends(get_current_user),
):
    """Live analytics dashboard WebSocket.  Requires authentication (cookie or Bearer token)."""
    await manager.connect(websocket)
    try:
        while True:
            # Simulate periodic push of dashboard data
            await asyncio.sleep(10)
            # In production, fetch real analytics summary here
            await manager.broadcast("{\"type\": \"dashboard_update\", \"data\": {}}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
