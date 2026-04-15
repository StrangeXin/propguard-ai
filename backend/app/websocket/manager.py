"""
WebSocket connection manager — handles client connections for real-time
compliance updates, with reconnection support.
"""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections from frontend clients."""

    def __init__(self):
        # account_id -> list of connected websockets
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, account_id: str):
        await websocket.accept()
        if account_id not in self._connections:
            self._connections[account_id] = []
        self._connections[account_id].append(websocket)
        logger.info(f"Client connected for account {account_id}. Total: {len(self._connections[account_id])}")

    def disconnect(self, websocket: WebSocket, account_id: str):
        if account_id in self._connections:
            self._connections[account_id] = [
                ws for ws in self._connections[account_id] if ws != websocket
            ]
            if not self._connections[account_id]:
                del self._connections[account_id]
        logger.info(f"Client disconnected from account {account_id}")

    async def send_compliance_update(self, account_id: str, data: dict):
        """Send compliance report to all clients watching this account."""
        if account_id not in self._connections:
            return

        dead_connections = []
        message = json.dumps(data, default=str)

        for ws in self._connections[account_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws, account_id)

    async def broadcast(self, data: dict):
        """Send to all connected clients across all accounts."""
        message = json.dumps(data, default=str)
        for account_id, connections in list(self._connections.items()):
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    self.disconnect(ws, account_id)

    @property
    def active_accounts(self) -> list[str]:
        return list(self._connections.keys())

    def connection_count(self, account_id: str | None = None) -> int:
        if account_id:
            return len(self._connections.get(account_id, []))
        return sum(len(conns) for conns in self._connections.values())


# Singleton
ws_manager = ConnectionManager()
