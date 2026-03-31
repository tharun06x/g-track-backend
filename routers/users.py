import uuid
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


router = APIRouter(prefix='/api/v1/users')


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=20)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if payload.password != payload.retrypassword:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    existing_user_result = await db.execute(
        select(Users).where(
            (Users.email == payload.email)
            | (Users.phone_no == payload.mobile)
            | (Users.consumer_no == payload.consumer_number)
        )
    )
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
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user_id=user.user_id, email=user.email)

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

    token = create_access_token(user_id=user.user_id, email=user.email)

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
    }