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
from schemas import DistributorRegister, DistributorLogin


router = APIRouter(prefix="/api/v1/distributors")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_distributor(
    payload: DistributorRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Register a new distributor account.
    
    - **email**: Unique email address
    - **password**: Password (8-20 characters)
    - **name**: Distributor name
    - **phone_no**: Contact phone number
    - **address**: Business address
    - **state**: State/Province
    - **district**: District
    """
    if payload.password != payload.retry_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Check if distributor already exists
    existing_distributor_result = await db.execute(
        select(Distributor).where(
            (Distributor.email == payload.email)
            | (Distributor.phone_no == payload.phone_no)
        )
    )
    existing_distributor = existing_distributor_result.scalar_one_or_none()
    if existing_distributor:
        raise HTTPException(status_code=409, detail="Distributor already exists")

    # Create new distributor
    distributor = Distributor(
        id=uuid.uuid4().hex[:20],
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        phone_no=payload.phone_no,
        address=payload.address,
        state=payload.state,
        district=payload.district,
    )

    db.add(distributor)
    await db.commit()
    await db.refresh(distributor)

    # Create access token
    access_token = create_access_token(
        user_id=distributor.id, email=distributor.email
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "distributor_id": distributor.id,
        "name": distributor.name,
        "email": distributor.email,
        "message": "Distributor account created successfully",
    }


@router.post("/login")
async def login_distributor(
    credentials: DistributorLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Login a distributor and receive access token.
    
    - **email**: Distributor email
    - **password**: Distributor password
    """
    result = await db.execute(
        select(Distributor).where(Distributor.email == credentials.email)
    )
    distributor = result.scalar_one_or_none()

    if not distributor or not verify_password(
        credentials.password, distributor.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        user_id=distributor.id, email=distributor.email
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "distributor_id": distributor.id,
        "name": distributor.name,
        "email": distributor.email,
    }


@router.get("/me")
async def get_current_distributor_info(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get current logged-in distributor information.
    Requires valid access token.
    """
    result = await db.execute(
        select(Distributor).where(Distributor.id == current_user.sub)
    )
    distributor = result.scalar_one_or_none()

    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")

    return {
        "distributor_id": distributor.id,
        "name": distributor.name,
        "email": distributor.email,
        "phone_no": distributor.phone_no,
        "address": distributor.address,
        "state": distributor.state,
        "district": distributor.district,
    }


@router.get("")
async def list_distributors(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    List all distributors (Admin endpoint).
    """
    result = await db.execute(select(Distributor))
    distributors = result.scalars().all()
    
    return [
        {
            "id": d.id,
            "name": d.name,
            "email": d.email,
            "phone_no": d.phone_no,
            "address": d.address,
            "state": d.state,
            "district": d.district,
        }
        for d in distributors
    ]


@router.get("/{distributor_id}")
async def get_distributor(
    distributor_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get specific distributor by ID.
    """
    result = await db.execute(
        select(Distributor).where(Distributor.id == distributor_id)
    )
    distributor = result.scalar_one_or_none()

    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")

    return {
        "id": distributor.id,
        "name": distributor.name,
        "email": distributor.email,
        "phone_no": distributor.phone_no,
        "address": distributor.address,
        "state": distributor.state,
        "district": distributor.district,
    }


@router.get("/{distributor_id}/consumers")
async def get_distributor_consumers(
    distributor_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all consumers registered with a specific distributor.
    """
    result = await db.execute(
        select(Users).where(Users.distributor_name == distributor_id)
    )
    consumers = result.scalars().all()

    return [
        {
            "user_id": c.user_id,
            "name": c.name,
            "email": c.email,
            "phone_no": c.phone_no,
            "consumer_no": c.consumer_no,
            "address": c.address,
            "state": c.state,
            "district": c.district,
            "gas": c.gas,
        }
        for c in consumers
    ]
