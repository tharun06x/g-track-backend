from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
db_url=os.getenv('SQLALCHEMY_DATABASE_URL')

engine=create_engine(db_url)
sessionlocal=sessionmaker(autocommit=False,autoflush=False,bind=db_url)

class Base(DeclarativeBase):
    pass

def get_db():
    with sessionlocal() as db:
        yield db
