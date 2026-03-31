from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from datetime import date, timedelta
from typing import Annotated
from models import Sensor_unit


router = APIRouter(prefix='/api/v1/dashboard')

@router.get("/summary")
async def get_dashboard_summary(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    today = date.today()
    latest_query = (
        select(Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.date.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_query)
    remaining_gas = latest_result.scalar()

    today_usage_query = select(
        (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
    ).where(
        Sensor_unit.sensor_id == device_id,
        func.date(Sensor_unit.date) == today,
    )
    today_result = await db.execute(today_usage_query)
    gas_used_today = today_result.scalar() or 0.0

    thirty_days_ago = today - timedelta(days=30)

    daily_sub = (
        select(
            func.date(Sensor_unit.date).label("day"),
            (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("daily_usage"),
        )
        .where(
            Sensor_unit.sensor_id == device_id,
            func.date(Sensor_unit.date) >= thirty_days_ago,
        )
        .group_by(func.date(Sensor_unit.date))
        .subquery()
    )

    avg_query = select(func.avg(daily_sub.c.daily_usage).label("avg_daily_usage"))
    avg_result = await db.execute(avg_query)
    avg_daily_usage = avg_result.scalar() or 0.0

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
