from datetime import datetime
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession 

from database import get_db
from models import Sensor_unit
from services.depletion_prediction import (
    latest_depletion_features,
    load_trained_model,
    predict_days_remaining_ml,
    rule_based_days_remaining,
)
from services.feature_pipeline import build_features

router=APIRouter(prefix='/api/v1/reports')

@router.get("/gas-usage/stats")
async def get_gas_stats(
    device_id: str,
    granularity: Literal["daily", "monthly", "yearly"],
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = None,
    month: Optional[int] = None):
    if granularity == "daily":
        time_label = func.date(Sensor_unit.date).label("period")
    elif granularity == "monthly":
        time_label = func.extract('month', Sensor_unit.date).label("period")
    else: # yearly
        time_label = func.extract('year', Sensor_unit.date).label("period")

    usage_calc = (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
    query = select(time_label, usage_calc).where(Sensor_unit.sensor_id == device_id)
    if year:
        query = query.where(func.extract('year', Sensor_unit.date) == year)
    if month and granularity == "daily":
        query = query.where(func.extract('month', Sensor_unit.date) == month)

    query = query.group_by(time_label).order_by(time_label)
    result = await db.execute(query)
    return result.mappings().all()


@router.get('/gas-usage/features')
async def get_gas_usage_features(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
):
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.date.asc())
    )
    if start is not None:
        query = query.where(Sensor_unit.date >= start)
    if end is not None:
        query = query.where(Sensor_unit.date <= end)

    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows
    ]
    return build_features(records)


@router.get('/gas-usage/depletion-prediction')
async def get_depletion_prediction(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.date.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    feature_rows = build_features(records)
    latest = latest_depletion_features(feature_rows)
    if latest is None:
        return {
            "device_id": device_id,
            "message": "No readings available for depletion prediction",
        }

    baseline_days = rule_based_days_remaining(
        current_weight=latest["current_weight"],
        rolling_7day_avg_consumption=latest["rolling_7day_avg"],
    )

    model = load_trained_model()
    ml_days = None
    if model is not None:
        ml_days = predict_days_remaining_ml(model, latest)

    return {
        "device_id": device_id,
        "features": latest,
        "rule_based_days_remaining": baseline_days,
        "ml_days_remaining": ml_days,
        "model_loaded": model is not None,
    }
