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

class Adminmain(BaseModel):
    email:EmailStr=Field(max_length=120)
    password:str=Field(min_length=8,max_lenght=20)

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
