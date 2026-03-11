from fastapi import FastAPI,HTTPException
from typing import Annotated
from database import Base,engine,get_db
from schemas import (Usermain,UserCreate,UserLogin,UserUpdate,Adminmain,Distributor)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from routers import dashboard, refill, settings, users

Base.metadata.create_all(bind=engine)

app=FastAPI()
app.include_router(dashboard.router)
app.include_router(refill.router)
app.include_router(settings.router)
app.include_router(users.router)

api_version=1.0

@app.get("/",include_in_schema=False,name="home")
def root():
    return{"Status":f"G-Track {api_version} API Running"}

@app.get("/health")
def health():
    return{'status':'Running',
           'version':api_version
           }





