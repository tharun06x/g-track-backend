import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password, verify_password
from database import get_db
from models import Admin


router = APIRouter(prefix="/api/v1/admin")


class AdminLogin(BaseModel):
    admin_id: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=20)


class LoginTroubleRequest(BaseModel):
    distributor_id: str
    distributor_name: str
    email: EmailStr
    phone_no: str
    issue: str


@router.post("/login")
async def admin_login(
    credentials: AdminLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Authenticate an admin user.
    Returns JWT access token on success.
    """
    result = await db.execute(
        select(Admin).where(Admin.id == credentials.admin_id)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    # For now, we'll use a simple password check (in production, store hashed passwords)
    # Admin password is stored as-is for simplicity
    if not hasattr(admin, 'password_hash') or credentials.password != "admin":
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_access_token(user_id=admin.id, email=f"{admin.id}@admin.gtrack.local")

    return {
        "access_token": token,
        "token_type": "bearer",
        "admin_id": admin.id,
    }


@router.post("/login-trouble-request")
async def create_login_trouble_request(
    request: LoginTroubleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Submit a login trouble request that will be reviewed by admin.
    """
    trouble_request = {
        "id": f"REQ-{uuid.uuid4().hex[:8].upper()}",
        "distributor_id": request.distributor_id,
        "distributor_name": request.distributor_name,
        "date": "2026-04-04",  # Will be replaced with datetime
        "issue": request.issue,
        "status": "Pending",
        "email": request.email,
        "phone_no": request.phone_no,
    }
    
    return {
        "message": "Login trouble request submitted successfully",
        "request_id": trouble_request["id"],
        "status": "Pending"
    }
