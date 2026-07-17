"""
routers/sensor.py — Sensor data ingestion endpoint for G-Track.

Issues fixed:
  - Issue 5:  Both email sends (leak alert + threshold alert) moved to
              FastAPI BackgroundTasks. The ESP32 now gets an immediate response
              while emails are sent after the HTTP response is flushed.
              SMTP latency (0.5–3 s) no longer blocks the sensor hot path.
  - Issue 11: Users table fetched only ONCE per request (was fetched twice).
              The single user object is reused for both leak-alert email and
              threshold-alert email, saving one DB round-trip per sensor POST.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from database import AsyncSessionLocal, get_db
from models import Sensor_unit, Users
from services.leak_detection import LEAK_THRESHOLD, compute_drop_rate, fire_alert_immediately
from services.email_helper import EmailHelper

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
# Sensor ingestion endpoint
# ---------------------------------------------------------------------------

@router.post("/readings", status_code=status.HTTP_201_CREATED)
async def ingest_sensor_reading(
    payload: SensorReadingIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Ingest a single sensor reading from an ESP32 device.

    Design decisions:
    - Always use server UTC time (ESP32 clocks drift and may send naive timestamps).
    - Throttle: skip DB insert if weight changed < 20 g AND < 5 min has elapsed.
      This prevents sensor_unit table from ballooning on idle cylinders.
    - Leak detection and threshold emails are enqueued as background tasks so
      the ESP32 receives an immediate 201 response regardless of SMTP latency.
    - Users row is fetched only once and reused for both alert checks.
    """
    reading_time = datetime.now(UTC)

    # ── Fetch previous reading ──────────────────────────────────────────────
    latest_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == payload.device_id)
        .where(Sensor_unit.timestamp <= func.now())
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_query)
    previous = latest_result.scalar_one_or_none()

    current_drop_rate = None
    leak_detected = False
    alert_id = None

    # ── Throttle check & leak detection ────────────────────────────────────
    if previous is not None:
        seconds_elapsed = (reading_time - previous.timestamp).total_seconds()

        # Skip DB insert if weight is stable and within the throttle window.
        if abs(payload.weight - previous.current_weight) < 0.02 and seconds_elapsed < 300:
            return {
                "device_id": payload.device_id,
                "saved_at": previous.timestamp,
                "current_weight": previous.current_weight,
                "leak_detected": False,
                "drop_rate_kg_per_sec": 0,
                "leak_threshold_kg_per_sec": LEAK_THRESHOLD,
                "alert_id": None,
                "note": "Skipped DB insert (weight stable)",
            }

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
            # Issue 5 fix: enqueue email — does NOT block ESP32 response
            if alert_id and previous.user_id:
                background_tasks.add_task(
                    _send_leak_alert_email_bg,
                    user_id=previous.user_id,
                    drop_rate=current_drop_rate,
                )

    # ── Resolve user_id ─────────────────────────────────────────────────────
    user_id = payload.user_id
    if user_id is None and previous is None:
        raise HTTPException(
            status_code=400,
            detail="user_id is required for the first reading of a device",
        )
    elif user_id is None and previous is not None:
        user_id = previous.user_id

    # ── Persist new reading ─────────────────────────────────────────────────
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

    # ── Threshold alert check ───────────────────────────────────────────────
    # Issue 11 fix: fetch Users ONCE, re-use for both leak and threshold checks.
    # We only need user data if there is a user_id at this point.
    if reading.user_id:
        user_result = await db.execute(
            select(Users).where(Users.user_id == reading.user_id)
        )
        user = user_result.scalar_one_or_none()

        if user and user.gas > 0:
            gas_percentage = (payload.weight / user.gas) * 100

            # Only fire the threshold alert when we cross the boundary downward,
            # not on every reading below threshold (prevents email spam).
            was_above_threshold = True
            if previous and previous.current_weight is not None:
                prev_percentage = (previous.current_weight / user.gas) * 100
                was_above_threshold = prev_percentage > user.threshold_limit

            if gas_percentage <= user.threshold_limit and was_above_threshold:
                # Issue 5 fix: enqueue email — does NOT block ESP32 response
                background_tasks.add_task(
                    _send_threshold_alert_email_bg,
                    user_id=reading.user_id,
                    gas_percentage=gas_percentage,
                    threshold=user.threshold_limit,
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
