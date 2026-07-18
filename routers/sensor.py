"""
routers/sensor.py — Sensor data ingestion endpoint for G-Track.

Issues fixed (original):
  - Issue 5:  Both email sends moved to FastAPI BackgroundTasks.
  - Issue 11: Users table fetched only ONCE per request.

Architecture change (this revision):
  - The DB SELECT query that previously ran on EVERY incoming IoT reading to
    fetch the previous weight has been ELIMINATED.

  - Instead, the previous state is read from services.state_manager (RAM).
    This is a plain dictionary lookup — ~100 ns vs ~30 ms for a DB round-trip.

  - DB fallback on cold cache: If the backend just restarted (Render spin-down),
    the state_manager cache is empty. On the very first request for a device_id,
    ONE DB SELECT is performed to warm the cache. All subsequent requests for
    that device skip the DB entirely for the throttle check.

  - After processing, the new weight is broadcast to connected WebSocket clients
    via services.ws_manager — real-time frontend updates with zero DB queries.

  - The DB INSERT is still throttled the same way (weight change < 20g AND
    < 5 min elapsed = skip INSERT). This prevents the sensor_unit table from
    ballooning. However, the WebSocket broadcast fires even for throttled
    readings so the frontend always shows the latest live weight.

DB connection budget analysis (Render free tier — pool_size=3, max_overflow=2):
  Before: Every IoT reading = 1 SELECT + 1 INSERT = 2 connection checkouts
  After:  Cold start: 1 SELECT (warm-up) + 1 INSERT
          Warm:       0 SELECT + 1 conditional INSERT (often 0 total)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from database import AsyncSessionLocal, get_db
from models import Sensor_unit, Users
from services.leak_detection import LEAK_THRESHOLD, compute_drop_rate, fire_alert_immediately
from services.email_helper import EmailHelper
from services.state_manager import device_state, DeviceState
from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sensor")


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class SensorReadingIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=20)
    weight: float = Field(gt=0)
    user_id: str | None = Field(default=None, min_length=1, max_length=20)
    connection_status: bool | None = None
    timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Background task helpers — run AFTER HTTP response is sent to ESP32
# ---------------------------------------------------------------------------

async def _send_leak_alert_email_bg(
    user_id: str,
    drop_rate: float,
) -> None:
    """Background task: send leak detection email outside the request lifecycle."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Users).where(Users.user_id == user_id))
            user = result.scalar_one_or_none()
            if user:
                sent = await EmailHelper.send_leak_detection_alert(
                    email=user.email,
                    name=user.name,
                    drop_rate=drop_rate,
                    threshold=LEAK_THRESHOLD,
                )
                if not sent:
                    logger.warning("Leak alert email failed for user %s", user_id)
    except Exception:
        logger.exception("Unexpected error in leak alert background task for user %s", user_id)


async def _send_threshold_alert_email_bg(
    user_id: str,
    gas_percentage: float,
    threshold: float,
) -> None:
    """Background task: send low-gas threshold email outside the request lifecycle."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Users).where(Users.user_id == user_id))
            user = result.scalar_one_or_none()
            if user:
                sent = await EmailHelper.send_refill_reminder(
                    email=user.email,
                    name=user.name,
                    gas_level=gas_percentage,
                    threshold=threshold,
                )
                if not sent:
                    logger.warning("Threshold alert email failed for user %s", user_id)
    except Exception:
        logger.exception("Unexpected error in threshold alert background task for user %s", user_id)


# ---------------------------------------------------------------------------
# Cold-cache DB warm-up helper
# ---------------------------------------------------------------------------

async def _warm_cache_from_db(device_id: str, db: AsyncSession) -> DeviceState | None:
    """
    Fetch the latest DB row for *device_id* and populate the in-memory cache.

    Called only once per device_id after a backend restart (cold cache).
    All subsequent requests for this device skip this entirely.
    """
    from sqlalchemy import func
    latest_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == device_id)
        .where(Sensor_unit.timestamp <= func.now())
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )
    result = await db.execute(latest_query)
    row = result.scalar_one_or_none()

    if row is None:
        return None

    return device_state.warm_from_db_row(
        device_id=device_id,
        current_weight=row.current_weight,
        timestamp=row.timestamp,
        user_id=row.user_id,
        connection_status=row.connection_status,
    )


# ---------------------------------------------------------------------------
# Sensor ingestion endpoint
# ---------------------------------------------------------------------------

@router.post("/readings", status_code=status.HTTP_201_CREATED)
async def ingest_sensor_reading(
    payload: SensorReadingIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Ingest a single sensor reading from an ESP32 device.

    Hot-path flow:
      1. Look up previous state from in-memory cache (NO DB read).
      2. If cache is cold (backend just restarted), warm it from DB (ONE read).
      3. Throttle check against cached state.
      4. Broadcast new weight to WebSocket clients (even if DB insert is skipped).
      5. Conditionally INSERT into DB if throttle check passes.
      6. Update in-memory cache.
      7. Run email alerts as BackgroundTasks (after HTTP response is sent).
    """
    reading_time = datetime.now(UTC)

    # ── Step 1: Resolve previous state from RAM ─────────────────────────────
    previous: DeviceState | None = device_state.get(payload.device_id)

    # ── Step 2: Cold-cache warm-up (once per device per backend restart) ────
    if previous is None:
        logger.info(
            "Cache cold for device=%s — warming from DB (one-time per restart)",
            payload.device_id,
        )
        previous = await _warm_cache_from_db(payload.device_id, db)

    # ── Step 3: Throttle check ───────────────────────────────────────────────
    if previous is not None:
        seconds_elapsed = (reading_time - previous.timestamp).total_seconds()
        weight_delta = abs(payload.weight - previous.current_weight)

        # Always broadcast to WebSocket clients (frontend sees live weight)
        # even when the DB insert is throttled.
        if weight_delta < 0.02 and seconds_elapsed < 300:
            # Update RAM cache so the next throttle check uses the freshest weight
            device_state.update(
                device_id=payload.device_id,
                current_weight=payload.weight,
                timestamp=reading_time,
                user_id=payload.user_id,
                connection_status=payload.connection_status,
            )
            # Broadcast to WebSocket clients — zero DB queries
            await ws_manager.broadcast(
                payload.device_id,
                {
                    "event": "reading",
                    "device_id": payload.device_id,
                    "current_weight": payload.weight,
                    "timestamp": reading_time.isoformat(),
                    "leak_detected": False,
                    "drop_rate_kg_per_sec": 0.0,
                },
            )
            return {
                "device_id": payload.device_id,
                "saved_at": previous.timestamp,
                "current_weight": previous.current_weight,
                "leak_detected": False,
                "drop_rate_kg_per_sec": 0,
                "leak_threshold_kg_per_sec": LEAK_THRESHOLD,
                "alert_id": None,
                "note": "Skipped DB insert (weight stable) — WebSocket broadcast sent",
            }

    # ── Step 4: Leak detection ───────────────────────────────────────────────
    current_drop_rate = None
    leak_detected = False
    alert_id = None

    if previous is not None:
        seconds_elapsed = (reading_time - previous.timestamp).total_seconds()
        current_drop_rate = compute_drop_rate(
            previous_weight=previous.current_weight,
            current_weight=payload.weight,
            seconds_elapsed=seconds_elapsed,
        )

        if current_drop_rate is not None and current_drop_rate > LEAK_THRESHOLD:
            leak_detected = True
            alert_id = await fire_alert_immediately(
                db=db,
                user_id=previous.user_id,
                drop_rate=current_drop_rate,
                threshold=LEAK_THRESHOLD,
            )
            if alert_id and previous.user_id:
                background_tasks.add_task(
                    _send_leak_alert_email_bg,
                    user_id=previous.user_id,
                    drop_rate=current_drop_rate,
                )

    # ── Step 5: Resolve user_id ──────────────────────────────────────────────
    user_id = payload.user_id
    if user_id is None and previous is None:
        raise HTTPException(
            status_code=400,
            detail="user_id is required for the first reading of a device",
        )
    elif user_id is None and previous is not None:
        user_id = previous.user_id

    # ── Step 6: Persist new reading to DB ────────────────────────────────────
    reading = Sensor_unit(
        sensor_id=payload.device_id,
        current_weight=payload.weight,
        connection_status=payload.connection_status,
        timestamp=reading_time,
        user_id=user_id,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)

    # ── Step 7: Threshold alert check ────────────────────────────────────────
    # Fetch Users ONCE (Issue 11) — only if a user_id is known.
    if reading.user_id:
        user_result = await db.execute(
            select(Users).where(Users.user_id == reading.user_id)
        )
        user = user_result.scalar_one_or_none()

        if user and user.gas > 0:
            gas_percentage = (payload.weight / user.gas) * 100

            was_above_threshold = True
            if previous and previous.current_weight is not None:
                prev_percentage = (previous.current_weight / user.gas) * 100
                was_above_threshold = prev_percentage > user.threshold_limit

            if gas_percentage <= user.threshold_limit and was_above_threshold:
                background_tasks.add_task(
                    _send_threshold_alert_email_bg,
                    user_id=reading.user_id,
                    gas_percentage=gas_percentage,
                    threshold=user.threshold_limit,
                )

    # ── Step 8: Update in-memory cache ───────────────────────────────────────
    device_state.update(
        device_id=payload.device_id,
        current_weight=reading.current_weight,
        timestamp=reading.timestamp,
        user_id=reading.user_id,
        connection_status=reading.connection_status,
    )

    # ── Step 9: Broadcast to WebSocket clients ───────────────────────────────
    await ws_manager.broadcast(
        payload.device_id,
        {
            "event": "reading",
            "device_id": payload.device_id,
            "current_weight": reading.current_weight,
            "timestamp": reading.timestamp.isoformat(),
            "leak_detected": leak_detected,
            "drop_rate_kg_per_sec": current_drop_rate,
        },
    )

    return {
        "device_id": payload.device_id,
        "saved_at": reading.timestamp,
        "current_weight": reading.current_weight,
        "leak_detected": leak_detected,
        "drop_rate_kg_per_sec": current_drop_rate,
        "leak_threshold_kg_per_sec": LEAK_THRESHOLD,
        "alert_id": alert_id,
    }
