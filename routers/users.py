"""
routers/users.py — User account management for G-Track.

Issues fixed:
  - Issue 4:  GET /api/v1/users was completely unauthenticated and returned
              all user PII (name, email, phone, address, device_id) to any
              anonymous caller.  Now requires role "admin" or "distributor".
  - Issue 17: GET /api/v1/users now accepts ?page=&page_size= query params
              and returns a paginated response with a total count, preventing
              unbounded result sets as the user base grows.
  - Issue 13: Added POST /api/v1/users/refresh for refresh-token flow.
"""

import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from database import get_db
from models import Distributor, Users
from schemas import UserCreate
from services.notification_service import INotificationService, get_notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users")


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    phone_no: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{7,14}$")
    address: str | None = Field(default=None, min_length=10, max_length=120)
    threshold_limit: float | None = Field(default=None, ge=0.1, le=100.0)
    auto_delivery: bool | None = None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    notifier: Annotated[INotificationService, Depends(get_notification_service)],
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

    # Fire-and-forget welcome email — we don't block registration on SMTP
    try:
        await notifier.send_welcome_email(email=user.email, name=user.name)
    except Exception:
        logger.warning("Failed to send welcome email to %s", user.email)

    access_token = create_access_token(user_id=user.user_id, email=user.email, role="user")
    refresh_token = create_refresh_token(user_id=user.user_id, email=user.email, role="user")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

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

    access_token = create_access_token(user_id=user.user_id, email=user.email, role="user")
    refresh_token = create_refresh_token(user_id=user.user_id, email=user.email, role="user")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "name": user.name,
    }


# ---------------------------------------------------------------------------
# Refresh token  (Issue 13)
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh_access_token(body: RefreshRequest):
    """Exchange a valid refresh token for a new access token.

    The refresh token is a signed JWT with token_type="refresh".  It is
    validated against the same secret — no database lookup is needed.
    If the refresh token is expired or tampered, a 401 is returned.
    """
    payload = decode_token(body.refresh_token, expected_type="refresh")
    new_access = create_access_token(
        user_id=payload.sub,
        email=payload.email,
        role=payload.role,
    )
    return {
        "access_token": new_access,
        "token_type": "bearer",
    }


# ---------------------------------------------------------------------------
# Current user profile
# ---------------------------------------------------------------------------

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
        "phone_no": user.phone_no,
        "address": user.address,
        "state": user.state,
        "district": user.district,
        "device_id": user.device_id,
        "distributor_name": user.distributor_name,
    }


# ---------------------------------------------------------------------------
# User listing — admin/distributor only with pagination  (Issues 4 + 17)
# ---------------------------------------------------------------------------

@router.get("")
async def list_users(
    # Issue 4: require admin or distributor role — was completely unauthenticated
    current_user: Annotated[TokenPayload, Depends(require_role("admin", "distributor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    distributor_id: str | None = None,
    # Issue 17: pagination — was returning unbounded full table
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
):
    """List users/consumers.  Requires admin or distributor role.

    Distributors should always pass their own distributor_id to see only
    their consumers.  Admins may omit it to see all users.
    """
    base_query = select(Users)
    count_query = select(func.count()).select_from(Users)

    if distributor_id:
        base_query = base_query.where(Users.distributor_name == distributor_id)
        count_query = count_query.where(Users.distributor_name == distributor_id)

    offset = (page - 1) * page_size

    users_result, count_result = await __import__("asyncio").gather(
        db.execute(base_query.offset(offset).limit(page_size)),
        db.execute(count_query),
    )
    users = users_result.scalars().all()
    total = count_result.scalar() or 0

    return {
        "items": [
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
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


# ---------------------------------------------------------------------------
# Individual user CRUD
# ---------------------------------------------------------------------------

@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get specific user/consumer details.  Users can only view their own profile."""
    # Users can fetch their own profile; admins/distributors can fetch any
    if current_user.role == "user" and current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

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
    """Update user profile. Users can only update their own profile."""
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if update.name:
        user.name = update.name
    if update.phone_no:
        user.phone_no = update.phone_no
    if update.address:
        user.address = update.address
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
        "message": "User profile updated successfully",
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Deactivate a user account."""
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(user)
    await db.commit()

    return {"message": "User account deleted successfully"}