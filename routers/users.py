import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    TokenPayload,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from database import get_db
from models import Distributor, Users
from schemas import UserCreate
from services.email_helper import EmailHelper

logger = logging.getLogger(__name__)


router = APIRouter(prefix='/api/v1/users')


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=20)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    phone_no: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{7,14}$")
    address: str | None = Field(default=None, min_length=10, max_length=120)
    threshold_limit: float | None = Field(default=None, ge=0.1, le=100.0)
    auto_delivery: bool | None = None


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if payload.password != payload.retrypassword:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    duplicate_filters = (
        (Users.email == payload.email)
        | (Users.phone_no == payload.mobile)
        | (Users.consumer_no == payload.consumer_number)
    )
    if payload.device_id:
        duplicate_filters = duplicate_filters | (Users.device_id == payload.device_id)

    existing_user_result = await db.execute(select(Users).where(duplicate_filters))
    existing_user = existing_user_result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    distributor_result = await db.execute(
        select(Distributor).where(Distributor.name == payload.distributor)
    )
    distributor = distributor_result.scalar_one_or_none()
    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")

    user = Users(
        user_id=uuid.uuid4().hex[:20],
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        address=payload.address,
        phone_no=payload.mobile,
        consumer_no=payload.consumer_number,
        distributor_name=payload.distributor,
        state=payload.state,
        district=payload.district,
        device_id=payload.device_id,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Send welcome email to new user
    email_sent = await EmailHelper.send_welcome_email(
        email=user.email,
        name=user.name
    )
    
    if not email_sent:
        # Log warning but don't fail registration - user account is created successfully
        logger.warning(f"Failed to send welcome email to {user.email} for new user {user.user_id}")

    access_token = create_access_token(user_id=user.user_id, email=user.email, role="user")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
    }


@router.post("/login")
async def login(
    credentials: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Users).where(Users.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user_id=user.user_id, email=user.email, role="user")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "name": user.name,
    }


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Users).where(Users.user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "device_id": user.device_id,
    }


# ==================== USER MANAGEMENT ENDPOINTS ====================


@router.get("")
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    distributor_id: str = None,
):
    """
    List all users/consumers or filter by distributor.
    """
    if distributor_id:
        result = await db.execute(
            select(Users).where(Users.distributor_name == distributor_id)
        )
    else:
        result = await db.execute(select(Users))

    users = result.scalars().all()

    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
            "phone_no": u.phone_no,
            "consumer_no": u.consumer_no,
            "address": u.address,
            "state": u.state,
            "district": u.district,
            "device_id": u.device_id,
            "distributor_id": u.distributor_name,
            "gas": u.gas,
            "threshold_limit": u.threshold_limit,
            "auto_delivery": u.auto_delivery,
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get specific user/consumer details.
    """
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "phone_no": user.phone_no,
        "consumer_no": user.consumer_no,
        "address": user.address,
        "state": user.state,
        "district": user.district,
        "device_id": user.device_id,
        "distributor_id": user.distributor_name,
        "gas": user.gas,
        "threshold_limit": user.threshold_limit,
        "auto_delivery": user.auto_delivery,
    }


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    update: UserUpdate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update user profile (user can update own profile).
    """
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only user themselves can update their profile
    if current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update fields if provided
    if update.name:
        user.name = update.name
    if update.phone_no:
        user.phone_no = update.phone_no
    if update.address:
        user.address = update.address
    if update.device_id is not None:
        if update.device_id != user.device_id:
            existing_device = await db.execute(
                select(Users).where(Users.device_id == update.device_id)
            )
            if existing_device.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Device ID already assigned")
        user.device_id = update.device_id
    if update.threshold_limit is not None:
        user.threshold_limit = update.threshold_limit
    if update.auto_delivery is not None:
        user.auto_delivery = update.auto_delivery

    await db.commit()
    await db.refresh(user)

    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "phone_no": user.phone_no,
        "device_id": user.device_id,
        "message": "User profile updated successfully",
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Deactivate a user account.
    """
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only user themselves or admin can delete account
    if current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(user)
    await db.commit()

    return {"message": "User account deleted successfully"}