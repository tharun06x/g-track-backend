from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Sensor_unit, Users
from services.leak_detection import LEAK_THRESHOLD, compute_drop_rate, fire_alert_immediately
from services.email_helper import EmailHelper
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sensor")


class SensorReadingIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=20)
    weight: float = Field(gt=0)
    user_id: str | None = Field(default=None, min_length=1, max_length=20)
    connection_status: bool | None = None
    timestamp: datetime | None = None


@router.post("/readings", status_code=status.HTTP_201_CREATED)
async def ingest_sensor_reading(
    payload: SensorReadingIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    reading_time = payload.timestamp or datetime.now(UTC)

    latest_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == payload.device_id)
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_query)
    previous = latest_result.scalar_one_or_none()

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
            
            # Send leak detection alert email
            if alert_id and previous.user_id:
                user_result = await db.execute(
                    select(Users).where(Users.user_id == previous.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    email_sent = await EmailHelper.send_leak_detection_alert(
                        email=user.email,
                        name=user.name,
                        drop_rate=current_drop_rate,
                        threshold=LEAK_THRESHOLD
                    )
                    if not email_sent:
                        logger.warning(f"Failed to send leak detection email to {user.email}")
                        

    # Persist reading after leak check.
    if previous is None:
        if payload.user_id is None:
            raise HTTPException(
                status_code=400,
                detail="user_id is required for first reading of a device",
            )

        reading = Sensor_unit(
            sensor_id=payload.device_id,
            current_weight=payload.weight,
            connection_status=payload.connection_status,
            timestamp=reading_time,
            user_id=payload.user_id,
        )
        db.add(reading)
    else:
        previous.current_weight = payload.weight
        previous.connection_status = payload.connection_status
        previous.timestamp = reading_time
        if payload.user_id is not None:
            previous.user_id = payload.user_id
        reading = previous

    await db.commit()
    await db.refresh(reading)

    # Check if gas level is below threshold and send alert if needed
    if reading.user_id:
        user_result = await db.execute(
            select(Users).where(Users.user_id == reading.user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if user and payload.weight is not None:
            # Convert weight percentage to 0-100 scale for threshold comparison
            gas_percentage = payload.weight  # Assuming weight is already in percentage
            
            if gas_percentage <= user.threshold_limit:
                # Send threshold alert email
                email_sent = await EmailHelper.send_refill_reminder(
                    email=user.email,
                    name=user.name,
                    gas_level=gas_percentage,
                    threshold=user.threshold_limit
                )
                if not email_sent:
                    logger.warning(f"Failed to send threshold alert email to {user.email}")

    return {
        "device_id": payload.device_id,
        "saved_at": reading.timestamp,
        "current_weight": reading.current_weight,
        "leak_detected": leak_detected,
        "drop_rate_kg_per_sec": current_drop_rate,
        "leak_threshold_kg_per_sec": LEAK_THRESHOLD,
        "alert_id": alert_id,
    }
