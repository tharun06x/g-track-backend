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
from models import Users, Complaint, Distributor
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
    
    # Create complaint in database
    new_complaint = Complaint(
        complaint_id=complaint_id,
        user_id=current_user.sub,
        distributor_id=user.distributor_name,
        category=complaint.category,
        description=complaint.description,
        status="Open",
        remark="",
        consumer_name=complaint.consumer_name,
        consumer_email=complaint.consumer_email,
        consumer_phone=complaint.consumer_phone,
        created_at=datetime.now(UTC),
    )
    
    db.add(new_complaint)
    await db.commit()
    await db.refresh(new_complaint)

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
        "complaint_id": new_complaint.complaint_id,
        "status": new_complaint.status,
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
    query = select(Complaint)
    
    if distributor_id:
        query = query.where(Complaint.distributor_id == distributor_id)

    if status_filter:
        query = query.where(Complaint.status == status_filter)

    query = query.order_by(Complaint.created_at.desc())
    result = await db.execute(query)
    complaints = result.scalars().all()

    return [
        {
            "id": c.complaint_id,
            "complaint_id": c.complaint_id,
            "distributor_id": c.distributor_id,
            "date": c.created_at.strftime("%Y-%m-%d"),
            "category": c.category,
            "description": c.description,
            "status": c.status,
            "consumer_name": c.consumer_name,
            "consumer_phone": c.consumer_phone,
            "consumer_email": c.consumer_email,
            "remark": c.remark or "",
        }
        for c in complaints
    ]


@router.get("/{complaint_id}")
async def get_complaint(
    complaint_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get specific complaint details.
    """
    result = await db.execute(
        select(Complaint).where(Complaint.complaint_id == complaint_id)
    )
    complaint = result.scalar_one_or_none()

    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    return {
        "id": complaint.complaint_id,
        "complaint_id": complaint.complaint_id,
        "distributor_id": complaint.distributor_id,
        "date": complaint.created_at.strftime("%Y-%m-%d"),
        "category": complaint.category,
        "description": complaint.description,
        "status": complaint.status,
        "consumer_name": complaint.consumer_name,
        "consumer_phone": complaint.consumer_phone,
        "consumer_email": complaint.consumer_email,
        "remark": complaint.remark or "",
    }


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

    # Get complaint from database
    result = await db.execute(
        select(Complaint).where(Complaint.complaint_id == complaint_id)
    )
    complaint = result.scalar_one_or_none()

    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    # Update complaint
    complaint.status = update.status
    complaint.remark = update.remark
    complaint.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(complaint)

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
        "complaint_id": complaint.complaint_id,
        "status": complaint.status,
        "remark": complaint.remark,
        "updated_at": complaint.updated_at.isoformat() if complaint.updated_at else None,
        "message": "Complaint updated successfully",
    }


# 6. Get complaints for distributor (for distributor dashboard)
@router.get("/distributor/{distributor_id}")
async def get_distributor_complaints(
    distributor_id: str,
    status_filter: str = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Get all complaints for a specific distributor.
    Optional status filter: "Open", "In Progress", "Resolved", "Closed"
    """
    query = select(Complaint).where(Complaint.distributor_id == distributor_id)
    
    if status_filter:
        query = query.where(Complaint.status == status_filter)

    query = query.order_by(Complaint.created_at.desc())
    result = await db.execute(query)
    complaints = result.scalars().all()

    return [
        {
            "id": c.complaint_id,
            "complaint_id": c.complaint_id,
            "distributor_id": c.distributor_id,
            "date": c.created_at.strftime("%Y-%m-%d"),
            "category": c.category,
            "description": c.description,
            "status": c.status,
            "consumer_name": c.consumer_name,
            "consumer_phone": c.consumer_phone,
            "consumer_email": c.consumer_email,
            "remark": c.remark or "",
        }
        for c in complaints
    ]


# 7. Get complaints filed by a specific user (for user dashboard)
@router.get("/user/{user_id}")
async def get_user_complaints(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all complaints filed by a specific user.
    """
    # Get user's info
    user_result = await db.execute(
        select(Users).where(Users.user_id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's complaints from database
    query = select(Complaint).where(Complaint.user_id == user_id).order_by(Complaint.created_at.desc())
    result = await db.execute(query)
    complaints = result.scalars().all()

    return [
        {
            "id": c.complaint_id,
            "complaint_id": c.complaint_id,
            "distributor_id": c.distributor_id,
            "date": c.created_at.strftime("%Y-%m-%d"),
            "category": c.category,
            "description": c.description,
            "status": c.status,
            "consumer_name": c.consumer_name,
            "consumer_phone": c.consumer_phone,
            "consumer_email": c.consumer_email,
            "remark": c.remark or "",
        }
        for c in complaints
    ]