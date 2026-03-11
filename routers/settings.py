from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from models import Users
from auth import get_current_user

router = APIRouter(prefix='/api/v1/settings')


class SettingsUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=30)
    address: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone_no: Optional[str] = Field(default=None, max_length=15)
    threshold_limit: Optional[float] = Field(default=None, gt=0)
    auto_delivery: Optional[bool] = None


# GET current settings for a user
@router.get("/{user_id}")
async def get_settings(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "name": user.name,
        "address": user.address,
        "phone_no": user.phone_no,
        "threshold_limit": user.threshold_limit,
        "auto_delivery": user.auto_delivery,
    }


# UPDATE settings
@router.patch("/{user_id}")
async def update_settings(
    user_id: str,
    updates: SettingsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = updates.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return {
        "name": user.name,
        "address": user.address,
        "phone_no": user.phone_no,
        "threshold_limit": user.threshold_limit,
        "auto_delivery": user.auto_delivery,
    }
