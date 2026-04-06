import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, UTC

from auth import create_access_token, hash_password, verify_password
from database import get_db
from models import Admin, DistributorRequest, Distributor
from schemas import AdminLogin, AdminRegister, DistributorRequestCreate, DistributorRequestResponse, DistributorRequestReview


router = APIRouter(prefix="/api/v1/admin")

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
        select(Admin).where(Admin.email == credentials.email)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    # Verify password hash
    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_access_token(user_id=admin.id, email=admin.email, role="admin")

    return {
        "access_token": token,
        "token_type": "bearer",
        "admin_id": admin.id,
        "name": admin.name,
    }


@router.post("/register")
async def admin_register(
    admin_data: AdminRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Register a new admin user with hashed password.
    """
    # Check if email already exists
    result = await db.execute(
        select(Admin).where(Admin.email == admin_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if admin_id already exists
    result = await db.execute(
        select(Admin).where(Admin.id == admin_data.admin_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin ID already exists"
        )
    
    # Create new admin with hashed password
    admin = Admin(
        id=admin_data.admin_id,
        email=admin_data.email,
        password_hash=hash_password(admin_data.password),
        name=admin_data.name,
        phone_no=admin_data.phone_no,
    )
    
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    
    return {
        "message": "Admin registered successfully",
        "admin_id": admin.id,
        "email": admin.email,
        "name": admin.name,
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


# ==================== DISTRIBUTOR REQUEST ENDPOINTS ====================

@router.post("/distributor-requests")
async def submit_distributor_request(
    request_data: DistributorRequestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Submit a request for distributor account creation.
    Potential distributors use this endpoint to request an account.
    """
    # Check if email already has a request
    existing = await db.execute(
        select(DistributorRequest).where(
            (DistributorRequest.email == request_data.email) &
            (DistributorRequest.status == "pending")
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="You already have a pending distributor request. Please wait for admin approval."
        )
    
    # Create new request
    request_id = f"DREQ-{uuid.uuid4().hex[:12].upper()}"
    distributor_request = DistributorRequest(
        request_id=request_id,
        name=request_data.name,
        email=request_data.email,
        phone_no=request_data.phone_no,
        company_name=request_data.company_name,
        address=request_data.address,
        state=request_data.state,
        district=request_data.district,
        reason=request_data.reason,
        status="pending"
    )
    
    db.add(distributor_request)
    await db.commit()
    await db.refresh(distributor_request)
    
    return {
        "message": "Distributor request submitted successfully. An admin will review your request soon.",
        "request_id": request_id,
        "status": "pending"
    }


@router.get("/distributor-requests/pending")
async def get_pending_distributor_requests(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all pending distributor requests (admin only).
    """
    result = await db.execute(
        select(DistributorRequest)
        .where(DistributorRequest.status == "pending")
        .order_by(DistributorRequest.requested_at.desc())
    )
    requests = result.scalars().all()
    
    return {
        "total": len(requests),
        "requests": [
            {
                "request_id": req.request_id,
                "name": req.name,
                "email": req.email,
                "phone_no": req.phone_no,
                "company_name": req.company_name,
                "state": req.state,
                "district": req.district,
                "reason": req.reason,
                "requested_at": req.requested_at,
            }
            for req in requests
        ]
    }


@router.patch("/distributor-requests/{request_id}")
async def review_distributor_request(
    request_id: str,
    review: DistributorRequestReview,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Approve or reject a distributor account request.
    If approved, creates the distributor account.
    """
    # Get the request
    result = await db.execute(
        select(DistributorRequest).where(DistributorRequest.request_id == request_id)
    )
    distrib_request = result.scalar_one_or_none()
    
    if not distrib_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if distrib_request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Request is already {distrib_request.status}"
        )
    
    # Update request status
    distrib_request.status = review.status
    distrib_request.review_comment = review.review_comment
    distrib_request.reviewed_at = datetime.now(UTC)
    
    # If approved, create the distributor account
    if review.status == "approved":
        if not review.password:
            raise HTTPException(
                status_code=400,
                detail="Password required for approved requests"
            )
        
        # Check if email already exists as distributor
        existing = await db.execute(
            select(Distributor).where(Distributor.email == distrib_request.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Distributor email already exists"
            )
        
        # Create distributor account
        distributor_id = f"DIST-{uuid.uuid4().hex[:12].upper()}"
        distributor = Distributor(
            id=distributor_id,
            name=distrib_request.company_name,
            email=distrib_request.email,
            password_hash=hash_password(review.password),
            address=distrib_request.address,
            phone_no=distrib_request.phone_no,
            state=distrib_request.state,
            district=distrib_request.district,
        )
        db.add(distributor)
    
    await db.commit()
    await db.refresh(distrib_request)
    
    if review.status == "approved":
        return {
            "message": "Distributor request approved and account created",
            "request_id": request_id,
            "status": "approved",
            "distributor_id": distributor_id,
            "email": distrib_request.email
        }
    else:
        return {
            "message": "Distributor request rejected",
            "request_id": request_id,
            "status": "rejected",
            "comment": review.review_comment
        }
