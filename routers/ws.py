"""
routers/ws.py — WebSocket endpoint for real-time sensor data streaming.

Design:
  - No JWT auth on the WebSocket (intentional — only live weight is pushed,
    no PII or sensitive operations are exposed through this channel).
  - On connect: immediately sends the latest cached state from RAM so the
    frontend renders the current weight before the next IoT update arrives.
  - Stays alive in a receive-loop until the client disconnects.
  - The actual data broadcasting is triggered by sensor.py, not this router.

Usage (frontend JS example):
    const ws = new WebSocket("wss://your-api.onrender.com/api/v1/ws/sensor/ESP32_001");
    ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        console.log(data.current_weight);   // live weight in kg
    };

Payload shape (matches sensor POST response for consistency):
    {
        "device_id": "ESP32_001",
        "current_weight": 12.34,
        "timestamp": "2024-01-01T12:00:00+00:00",
        "leak_detected": false,
        "drop_rate_kg_per_sec": 0.0,
        "event": "reading"          // "snapshot" on initial connect
    }
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.state_manager import device_state
from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])


@router.websocket("/sensor/{device_id}")
async def sensor_ws(device_id: str, websocket: WebSocket) -> None:
    """
    WebSocket endpoint — streams live sensor readings for *device_id*.

    The frontend connects once and receives JSON pushes whenever the IoT
    device sends a new reading to POST /api/v1/sensor/readings.

    On initial connect, a "snapshot" message is sent with the latest known
    weight from the in-memory state cache (zero DB queries).
    """
    await ws_manager.connect(device_id, websocket)
    try:
        # ── Send initial snapshot ────────────────────────────────────────────
        # Lets the frontend render the current weight immediately without
        # waiting for the next IoT reading.
        cached = device_state.get(device_id)
        if cached is not None:
            await websocket.send_json({
                "event": "snapshot",
                "device_id": device_id,
                "current_weight": cached.current_weight,
                "timestamp": cached.timestamp.isoformat(),
                "leak_detected": False,
                "drop_rate_kg_per_sec": 0.0,
            })
        else:
            # Cache cold (backend just restarted) — inform the client
            await websocket.send_json({
                "event": "snapshot",
                "device_id": device_id,
                "current_weight": None,
                "timestamp": None,
                "note": "Cache cold — waiting for first IoT reading",
            })

        # ── Keep-alive receive loop ──────────────────────────────────────────
        # We don't expect meaningful messages from the frontend, but we must
        # await receive_text() / receive_bytes() so the connection stays open
        # and disconnects are detected promptly.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected cleanly for device=%s", device_id)
    except Exception:
        logger.exception("Unexpected error in WebSocket for device=%s", device_id)
    finally:
        ws_manager.disconnect(device_id, websocket)
