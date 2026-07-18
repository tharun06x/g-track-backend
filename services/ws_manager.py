"""
services/ws_manager.py — WebSocket connection manager for G-Track.

Why this exists:
  Instead of the frontend polling GET /api/v1/dashboard/summary repeatedly
  (each poll triggers 3 DB queries), the frontend opens a single long-lived
  WebSocket connection. Whenever the backend receives an IoT reading, it
  broadcasts the new weight to all connected frontends for that device — with
  zero DB queries.

Design:
  _connections maps device_id → set of active WebSocket connections.
  A set is used so that multiple browser tabs for the same device all receive
  updates simultaneously.

Thread-safety:
  Same single-threaded asyncio event loop assumption as state_manager.py.
  broadcast() is a coroutine; awaiting it yields control cooperatively.

Graceful disconnect handling:
  If a WebSocket disconnects mid-broadcast (e.g., client navigated away),
  the send raises WebSocketDisconnect or RuntimeError. broadcast() catches
  these silently and removes the stale connection.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class _ConnectionManager:
    """Manages active WebSocket connections grouped by device_id."""

    def __init__(self) -> None:
        # device_id → set of connected WebSocket objects
        self._connections: dict[str, set[WebSocket]] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        """Accept a new WebSocket and register it under *device_id*."""
        await websocket.accept()
        self._connections.setdefault(device_id, set()).add(websocket)
        logger.info(
            "WebSocket connected for device=%s | active=%d",
            device_id,
            self.active_count(device_id),
        )

    def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket from the registry (called on disconnect or error)."""
        bucket = self._connections.get(device_id)
        if bucket:
            bucket.discard(websocket)
            if not bucket:
                # Clean up empty sets to avoid memory leaks on long-running servers
                del self._connections[device_id]
        logger.info(
            "WebSocket disconnected for device=%s | remaining=%d",
            device_id,
            self.active_count(device_id),
        )

    # ── Broadcast ────────────────────────────────────────────────────────────

    async def broadcast(self, device_id: str, data: dict[str, Any]) -> None:
        """
        Send *data* as JSON to every active connection for *device_id*.

        Stale / broken connections are removed silently.
        This is a no-op if no frontend is currently connected.
        """
        bucket = self._connections.get(device_id)
        if not bucket:
            return  # No frontend connected — nothing to do

        dead: list[WebSocket] = []
        for ws in list(bucket):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(data)
                else:
                    dead.append(ws)
            except Exception:
                # Client disconnected between the state check and the send
                dead.append(ws)

        # Prune dead connections
        for ws in dead:
            self.disconnect(device_id, ws)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def active_count(self, device_id: str) -> int:
        """Return the number of active connections for *device_id*."""
        return len(self._connections.get(device_id, set()))

    def total_connections(self) -> int:
        """Return the total number of open WebSocket connections across all devices."""
        return sum(len(v) for v in self._connections.values())

    def connected_devices(self) -> list[str]:
        """Return the list of device_ids that currently have active connections."""
        return list(self._connections.keys())


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

ws_manager = _ConnectionManager()
