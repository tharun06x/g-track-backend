"""
routers/dashboard.py — Dashboard summary endpoint for G-Track.

Issues fixed:
  - Issue 10: The original code made 3 sequential DB round-trips (3 × ~30 ms =
              ~90 ms network latency minimum on Render). The queries are now
              launched concurrently with asyncio.gather(), reducing wall-clock
              time to the duration of the slowest single query.
"""

import asyncio
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenPayload, get_current_user
from database import get_db
from models import Sensor_unit

router = APIRouter(prefix="/api/v1/dashboard")


@router.get("/summary")
async def get_dashboard_summary(
    device_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return current gas status and usage statistics for a device.

    Three SQL queries are fired concurrently so total latency equals the
    slowest single query instead of the sum of all three.
    """
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    # ── Build queries ───────────────────────────────────────────────────────

    # 1. Latest weight reading
    latest_query = (
        select(Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .where(Sensor_unit.timestamp <= func.now())
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )

    # 2. Today's gas consumption (max - min weight within today)
    today_usage_query = select(
        (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
    ).where(
        Sensor_unit.sensor_id == device_id,
        func.date(Sensor_unit.timestamp) == today,
        Sensor_unit.timestamp <= func.now(),
    )

    # 3. 30-day average daily consumption (subquery → avg)
    daily_sub = (
        select(
            func.date(Sensor_unit.timestamp).label("day"),
            (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("daily_usage"),
        )
        .where(
            Sensor_unit.sensor_id == device_id,
            func.date(Sensor_unit.timestamp) >= thirty_days_ago,
            Sensor_unit.timestamp <= func.now(),
        )
        .group_by(func.date(Sensor_unit.timestamp))
        .subquery()
    )
    avg_query = select(func.avg(daily_sub.c.daily_usage).label("avg_daily_usage"))

    # ── Execute concurrently ────────────────────────────────────────────────
    # asyncio.gather() schedules all three coroutines before awaiting any,
    # so the DB driver can pipeline them where possible.
    latest_result, today_result, avg_result = await asyncio.gather(
        db.execute(latest_query),
        db.execute(today_usage_query),
        db.execute(avg_query),
    )

    remaining_gas = latest_result.scalar()
    gas_used_today = today_result.scalar() or 0.0
    avg_daily_usage = avg_result.scalar() or 0.0

    # ── Estimate depletion date ─────────────────────────────────────────────
    predicted_empty_date = None
    if avg_daily_usage > 0 and remaining_gas is not None:
        days_left = remaining_gas / avg_daily_usage
        predicted_empty_date = str(today + timedelta(days=int(days_left)))

    return {
        "remaining_gas": remaining_gas,
        "gas_used_today": round(gas_used_today, 2),
        "avg_daily_usage": round(avg_daily_usage, 2),
        "predicted_empty_date": predicted_empty_date,
    }
