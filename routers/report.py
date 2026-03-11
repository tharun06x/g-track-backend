from fastapi import FastAPI,APIRouter,Depends
from sqlalchemy import select,func,extract
from sqlalchemy.ext.asyncio import AsyncSession 
from database import Base,get_db
from datetime import date
from typing import Annotated,Optional,Literal
from models import Sensor_unit

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
