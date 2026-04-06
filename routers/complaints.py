import uuid
from typing import Annotated
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenPayload, get_current_user
from database import get_db
from models import Users


router = APIRouter(prefix="/api/v1/complaints")


class ComplaintCreate(BaseModel):
    category: str = Field(min_length=1)
    description: str = Field(min_length=10)
    consumer_name: str
    consumer_email: EmailStr
    consumer_phone: str


class ComplaintUpdate(BaseModel):
    status: str
    remark: str = ""


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_complaint(
    complaint: ComplaintCreate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Submit a new complaint as a consumer.
    """
    # Get user info for distributor_id
    result = await db.execute(
        select(Users).where(Users.user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_complaint = {
        "id": f"CMP-{uuid.uuid4().hex[:8].upper()}",
        "distributor_id": user.distributor_name,
        "date": datetime.now(UTC).isoformat(),
        "category": complaint.category,
        "description": complaint.description,
        "status": "Open",
        "consumer_name": complaint.consumer_name,
        "consumer_email": complaint.consumer_email,
        "consumer_phone": complaint.consumer_phone,
        "remark": "",
    }

    return {
        "complaint_id": new_complaint["id"],
        "status": new_complaint["status"],
        "message": "Complaint submitted successfully",
    }


@router.get("")
async def list_complaints(
    db: Annotated[AsyncSession, Depends(get_db)],
    distributor_id: str = None,
    status_filter: str = None,
):
    """
    List complaints with optional filters.
    If distributor_id is provided, returns complaints for that distributor.
    """
    # This is a mock implementation - in production, you'd query a Complaint table
    complaints = [
        {
            "id": "CMP-101",
            "distributor_id": distributor_id or "DIST-001",
            "date": "2026-03-24",
            "category": "Delivery Delay",
            "description": "Refill not delivered after 3 days of booking.",
            "status": "Open",
            "consumer_name": "John Doe",
            "consumer_phone": "+91 98765 43210",
            "consumer_email": "john@example.com",
            "remark": "",
        }
    ]

    if distributor_id:
        complaints = [c for c in complaints if c["distributor_id"] == distributor_id]

    if status_filter:
        complaints = [c for c in complaints if c["status"] == status_filter]

    return complaints


@router.get("/{complaint_id}")
async def get_complaint(
    complaint_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get specific complaint details.
    """
    # Mock implementation
    complaints = {
        "CMP-101": {
            "id": "CMP-101",
            "distributor_id": "DIST-001",
            "date": "2026-03-24",
            "category": "Delivery Delay",
            "description": "Refill not delivered after 3 days of booking.",
            "status": "Open",
            "consumer_name": "John Doe",
            "consumer_phone": "+91 98765 43210",
            "consumer_email": "john@example.com",
            "remark": "",
        }
    }

    if complaint_id not in complaints:
        raise HTTPException(status_code=404, detail="Complaint not found")

    return complaints[complaint_id]


@router.put("/{complaint_id}")
async def update_complaint(
    complaint_id: str,
    update: ComplaintUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update complaint status and remark (typically by distributor/admin).
    """
    allowed_statuses = ["Open", "In Progress", "Resolved", "Closed"]
    
    if update.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(allowed_statuses)}"
        )

    return {
        "complaint_id": complaint_id,
        "status": update.status,
        "remark": update.remark,
        "updated_at": datetime.now(UTC).isoformat(),
        "message": "Complaint updated successfully",
    }
