from pydantic import BaseModel,EmailStr,Field
from datetime import datetime

class Usermain(BaseModel):
    email:EmailStr=Field(max_length=120)
    password:str=Field(min_length=8,max_lenght=20)

class UserCreate(Usermain):
    name:str=Field(min_length=1,max_length=50)
    consumer_number:str
    mobile: str=Field(pattern=r"^\+?[1-9]\d{7,14}$")
    address:str=Field(min_length=10,max_length=120)
    state:str
    district:str
    distributor:str
    retrypassword:str

class UserLogin(Usermain):
    pass

class UserUpdate(BaseModel):
    name:str|None=Field(default=None,min_length=1,max_length=50)
    email:EmailStr|None=Field(max_length=120)

class AdminBase(BaseModel):
    email: EmailStr = Field(max_length=120)


class AdminLogin(AdminBase):
    password: str = Field(min_length=8, max_length=20)


class AdminRegister(AdminLogin):
    admin_id: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=30)
    phone_no: str | None = Field(default=None, max_length=15)

class DistributorRegister(BaseModel):
    email: EmailStr = Field(max_length=120)
    password: str = Field(min_length=8, max_length=20)
    name: str = Field(min_length=1, max_length=50)
    phone_no: str = Field(pattern=r"^\+?[1-9]\d{7,14}$")
    address: str = Field(min_length=10, max_length=120)
    state: str
    district: str
    retry_password: str

class DistributorLogin(BaseModel):
    email: EmailStr = Field(max_length=120)
    password: str = Field(min_length=8, max_length=20)

class Distributor(BaseModel):
    distributor_id:str=Field(max_length=20)
    password:str=Field(min_length=8,max_lenght=20)


class DistributorRequestCreate(BaseModel):
    """Schema for submitting a distributor account request."""
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)
    phone_no: str = Field(pattern=r"^\+?[1-9]\d{7,14}$")
    company_name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=5, max_length=150)
    state: str = Field(min_length=2, max_length=30)
    district: str = Field(min_length=2, max_length=30)
    reason: str | None = Field(default=None, max_length=500)


class DistributorRequestResponse(BaseModel):
    """Response for distributor request."""
    request_id: str
    name: str
    email: str
    company_name: str
    status: str
    requested_at: datetime
    review_comment: str | None = None


class DistributorRequestReview(BaseModel):
    """Schema for admin to approve/reject distributor requests."""
    status: str = Field(pattern="^(approved|rejected)$")
    review_comment: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=20)  # Password for approved requests
