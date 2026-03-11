from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from typing import Annotated
from pydantic import BaseModel, EmailStr, Field
from models import Users
from auth import verify_password, create_access_token, get_current_user

router = APIRouter(prefix='/api/v1/users')


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=20)


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

    token = create_access_token({"user_id": user.user_id, "email": user.email})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "name": user.name,
    }


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Users).where(Users.user_id == current_user["user_id"])
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
    }