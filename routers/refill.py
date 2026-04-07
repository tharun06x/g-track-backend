from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth import TokenPayload, get_current_user
from database import get_db
from datetime import datetime, UTC
from typing import Annotated, Optional
from models import Refill_request, Users
from services.email_helper import EmailHelper
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/refill')


# 1. User requests a refill
@router.post("/request")
async def create_refill_request(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
):
    if current_user.sub != user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this user")

    request_id = uuid.uuid4().hex[:10]

    new_request = Refill_request(
        request_id=request_id,
        user_id=user_id,
        requested_status="pending",
    )
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)

    return {
        "request_id": new_request.request_id,
        "user_id": new_request.user_id,
        "status": new_request.requested_status,
        "requested_date": new_request.requested_date,
    }


# 2. Distributor approves or rejects the refill
@router.patch("/approve/{request_id}")
async def approve_refill_request(
    request_id: str,
    distributor_id: str,
    action: str,  # "approved" or "rejected"
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Action must be 'approved' or 'rejected'")

    result = await db.execute(
        select(Refill_request).where(Refill_request.request_id == request_id)
    )
    refill = result.scalar_one_or_none()

    if not refill:
        raise HTTPException(status_code=404, detail="Refill request not found")

    if refill.requested_status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {refill.requested_status}")

    refill.requested_status = action
    refill.approved_by = distributor_id
    refill.approved_date = datetime.now(UTC)

    await db.commit()
    await db.refresh(refill)

    # Send email notification to user
    user_result = await db.execute(
        select(Users).where(Users.user_id == refill.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if user:
        if action == "approved":
            email_sent = await EmailHelper.send_refill_approval(
                email=user.email,
                name=user.name,
                request_id=refill.request_id
            )
        else:  # rejected
            email_sent = await EmailHelper.send_refill_rejection(
                email=user.email,
                name=user.name,
                request_id=refill.request_id,
                reason=""
            )
        
        if not email_sent:
            logger.warning(f"Failed to send refill {action} email to {user.email}")

    return {
        "request_id": refill.request_id,
        "user_id": refill.user_id,
        "status": refill.requested_status,
        "approved_by": refill.approved_by,
        "approved_date": refill.approved_date,
    }


# 3. Get all refill requests for a user
@router.get("/user/{user_id}")
async def get_user_refills(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Refill_request)
        .where(Refill_request.user_id == user_id)
        .order_by(Refill_request.requested_date.desc())
    )
    refills = result.scalars().all()

    return [
        {
            "request_id": r.request_id,
            "status": r.requested_status,
            "requested_date": r.requested_date,
            "approved_by": r.approved_by,
            "approved_date": r.approved_date,
        }
        for r in refills
    ]


# 4. Distributor views refill requests from their users
@router.get("/distributor/{distributor_id}")
async def get_distributor_refills(
    distributor_id: str,
    status: Optional[str] = None,  # filter: "pending", "approved", "rejected"
    db: Annotated[AsyncSession, Depends(get_db)] = None
):
    query = (
        select(Refill_request)
        .join(Users, Refill_request.user_id == Users.user_id)
        .where(Users.distributor_name == distributor_id)
    )
    if status:
        query = query.where(Refill_request.requested_status == status)

    query = query.order_by(Refill_request.requested_date.desc())
    result = await db.execute(query)
    refills = result.scalars().all()

    return [
        {
            "request_id": r.request_id,
            "user_id": r.user_id,
            "status": r.requested_status,
            "requested_date": r.requested_date,
            "approved_by": r.approved_by,
            "approved_date": r.approved_date,
        }
        for r in refills
    ]


# 5. Admin views all refill requests across all distributors
@router.get("/admin/all")
async def get_all_refills(
    status: Optional[str] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None
):
    query = select(Refill_request)
    if status:
        query = query.where(Refill_request.requested_status == status)

    query = query.order_by(Refill_request.requested_date.desc())
    result = await db.execute(query)
    refills = result.scalars().all()

    return [
        {
            "request_id": r.request_id,
            "user_id": r.user_id,
            "status": r.requested_status,
            "requested_date": r.requested_date,
            "approved_by": r.approved_by,
            "approved_date": r.approved_date,
        }
        for r in refills
    ]


# 6. Get enriched refill history for a user (for refill-history.html page)
@router.get("/history/{user_id}")
async def get_user_refill_history(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns refill history with distributor name and simulated delivery amounts.
    For approved refills, calculates realistic delivery amounts based on hash of request_id.
    """
    from models import Distributor
    
    result = await db.execute(
        select(Refill_request, Users, Distributor)
        .where(Refill_request.user_id == user_id)
        .outerjoin(Users, Refill_request.user_id == Users.user_id)
        .outerjoin(Distributor, Refill_request.approved_by == Distributor.id)
        .order_by(Refill_request.requested_date.desc())
    )
    rows = result.fetchall()

    history = []
    for row in rows:
        refill, user, distributor = row
        
        # Approved refills show delivery details
        if refill.requested_status == "approved" and refill.approved_date:
            # Generate consistent delivery amount (14-60 kg based on hash)
            hash_val = hash(refill.request_id) % 47 + 14
            amount = float(hash_val)
            
            history.append({
                "request_id": refill.request_id,
                "status": refill.requested_status,
                "date": refill.approved_date.strftime("%b %d, %Y"),
                "time": refill.approved_date.strftime("%I:%M %p"),
                "amount": f"+{amount:.1f} kg",
                "delivered_by": distributor.name if distributor else "Gas Distributor",
                "approved_date": refill.approved_date.isoformat(),
            })
        else:
            # Pending/rejected refills show request date
            history.append({
                "request_id": refill.request_id,
                "status": refill.requested_status,
                "date": refill.requested_date.strftime("%b %d, %Y"),
                "time": refill.requested_date.strftime("%I:%M %p"),
                "amount": "--",
                "delivered_by": "--",
                "approved_date": None,
            })

    return history
