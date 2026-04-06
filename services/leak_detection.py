from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Alert_log, Users

# kg/s. Can be overridden via environment variable.
LEAK_THRESHOLD = float(os.getenv("LEAK_THRESHOLD", "0.001"))


def compute_drop_rate(previous_weight: float, current_weight: float, seconds_elapsed: float) -> float | None:
    if seconds_elapsed <= 0:
        return None
    return (previous_weight - current_weight) / seconds_elapsed


async def fire_alert_immediately(
    db: AsyncSession,
    user_id: str | None,
    drop_rate: float,
    threshold: float = LEAK_THRESHOLD,
) -> str | None:
    """Persist a leak alert record immediately in the current request context."""
    if user_id is None:
        return None

    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None

    alert_id = uuid.uuid4().hex[:20]
    alert = Alert_log(
        alert_id=alert_id,
        alert_type=f"gas_leak: rate={drop_rate:.6f}kg/s threshold={threshold:.6f}kg/s",
        delivery_status=False,
        time_stamp=datetime.now(UTC),
        user_id=user_id,
    )
    db.add(alert)
    return alert_id


async def get_cylinder_remaining_weight(
    db: AsyncSession,
    sensor_id: str,
) -> dict | None:
    """
    Get the remaining weight of a cylinder with comprehensive metrics.
    
    Returns a dictionary containing:
    - remaining_weight: Current weight of the cylinder (kg)
    - previous_weight: Previous sensor reading weight (kg)
    - current_drop_rate: Current consumption rate (kg/s)
    - last_update: Timestamp of the latest reading
    - connection_status: Whether the sensor is connected
    """
    from models import Sensor_unit
    
    # Get the latest sensor reading
    latest_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == sensor_id)
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_query)
    latest_reading = latest_result.scalar_one_or_none()
    
    if latest_reading is None:
        return None
    
    # Get the previous sensor reading to compute drop rate
    previous_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == sensor_id)
        .order_by(Sensor_unit.timestamp.desc())
        .limit(2)
        .offset(1)
    )
    previous_result = await db.execute(previous_query)
    previous_reading = previous_result.scalar_one_or_none()
    
    current_drop_rate = None
    previous_weight = None
    
    if previous_reading is not None:
        seconds_elapsed = (latest_reading.timestamp - previous_reading.timestamp).total_seconds()
        current_drop_rate = compute_drop_rate(
            previous_weight=previous_reading.current_weight,
            current_weight=latest_reading.current_weight,
            seconds_elapsed=seconds_elapsed,
        )
        previous_weight = previous_reading.current_weight
    
    return {
        "sensor_id": sensor_id,
        "remaining_weight": latest_reading.current_weight,
        "previous_weight": previous_weight,
        "current_drop_rate": current_drop_rate,
        "last_update": latest_reading.timestamp,
        "connection_status": latest_reading.connection_status,
    }
