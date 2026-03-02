from fastapi import FastAPI,HTTPException
from typing import Annotated
from database import Base,engine,get_db
from schemas import (Usermain,UserCreate,UserLogin,UserUpdate,Adminmain,Distributor)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import session

Base.metadata.create_all(bind=engine)


