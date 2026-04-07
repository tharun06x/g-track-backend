import uuid
import logging
from typing import Annotated
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenPayload, get_current_user
from database import get_db
from models import Users
from services.email_helper import EmailHelper

logger = logging.getLogger(__name__)

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
    consumer_email: EmailStr | None = None  # Optional - for sending status update emails
    consumer_name: str | None = None  # Optional - for sending status update emails


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

    complaint_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
    
    new_complaint = {
        "id": complaint_id,
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

    # Send complaint confirmation email
    email_sent = await EmailHelper.send_complaint_confirmation(
        email=complaint.consumer_email,
        name=complaint.consumer_name,
        complaint_id=complaint_id,
        status="Open"
    )
    if not email_sent:
        logger.warning(f"Failed to send complaint confirmation email to {complaint.consumer_email}")

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
    Optionally send status update email if consumer_email and consumer_name are provided.
    """
    allowed_statuses = ["Open", "In Progress", "Resolved", "Closed"]
    
    if update.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(allowed_statuses)}"
        )

    # Send status update email if consumer info is provided
    if update.consumer_email and update.consumer_name:
        email_sent = await EmailHelper.send_complaint_status_update(
            email=update.consumer_email,
            name=update.consumer_name,
            complaint_id=complaint_id,
            status=update.status,
            remark=update.remark
        )
        if not email_sent:
            logger.warning(f"Failed to send complaint status update email to {update.consumer_email}")

    return {
        "complaint_id": complaint_id,
        "status": update.status,
        "remark": update.remark,
        "updated_at": datetime.now(UTC).isoformat(),
        "message": "Complaint updated successfully",
    }


# 6. Get complaints for distributor (for distributor dashboard)
@router.get("/distributor/{distributor_id}")
async def get_distributor_complaints(
    distributor_id: str,
    status_filter: str = None,
    current_user: Annotated[TokenPayload, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Get all complaints for a specific distributor.
    Optional status filter: "Open", "In Progress", "Resolved", "Closed"
    """
    # Mock implementation - returns distributor's complaints
    complaints = [
        {
            "id": "CMP-101",
            "distributor_id": distributor_id,
            "date": "2026-03-24",
            "category": "Delivery Delay",
            "description": "Refill not delivered after 3 days of booking.",
            "status": "Open",
            "consumer_name": "John Doe",
            "consumer_phone": "+91 98765 43210",
            "consumer_email": "john@example.com",
            "remark": "",
        },
        {
            "id": "CMP-102",
            "distributor_id": distributor_id,
            "date": "2026-03-28",
            "category": "Product Quality",
            "description": "Received damaged cylinder.",
            "status": "In Progress",
            "consumer_name": "Jane Smith",
            "consumer_phone": "+91 87654 32109",
            "consumer_email": "jane@example.com",
            "remark": "Replacement scheduled for next week",
        },
        {
            "id": "CMP-103",
            "distributor_id": distributor_id,
            "date": "2026-04-02",
            "category": "Billing Issue",
            "description": "Overcharged for last refill.",
            "status": "Resolved",
            "consumer_name": "Mike Johnson",
            "consumer_phone": "+91 76543 21098",
            "consumer_email": "mike@example.com",
            "remark": "Refund processed successfully",
        },
    ]

    if status_filter:
        complaints = [c for c in complaints if c["status"] == status_filter]

    return complaints


# 7. Get complaints filed by a specific user (for user dashboard)
@router.get("/user/{user_id}")
async def get_user_complaints(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all complaints filed by a specific user.
    """
    # Get user's distributor
    result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Mock implementation - returns user's complaints
    complaints = [
        {
            "id": "CMP-201",
            "distributor_id": user.distributor_name,
            "date": "2026-03-15",
            "category": "Device Issue",
            "description": "Sensor not reading properly",
            "status": "Resolved",
            "consumer_name": user.name,
            "consumer_phone": user.phone_number or "",
            "consumer_email": user.email,
            "remark": "Device replaced",
        },
        {
            "id": "CMP-202",
            "distributor_id": user.distributor_name,
            "date": "2026-04-01",
            "category": "Service Issue",
            "description": "Late delivery for refill",
            "status": "In Progress",
            "consumer_name": user.name,
            "consumer_phone": user.phone_number or "",
            "consumer_email": user.email,
            "remark": "Driver contacted, ETA 2 hours",
        },
    ]

    return complaints
