from sqlalchemy import DateTime,Float,ForeignKey,String,DateTime,Boolean
from sqlalchemy.orm import Mapped,mapped_column,relationship
from database import Base
from datetime import UTC, datetime


class Users(Base):
    __tablename__="users"
    user_id:Mapped[str]=mapped_column(String(20),index=True,primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True,nullable=False)
    password_hash:Mapped[str]=mapped_column(String(255),nullable=False)
    name:Mapped[str]=mapped_column(String(30),nullable=False)
    address:Mapped[str]=mapped_column(String(100),nullable=False)
    phone_no:Mapped[str]=mapped_column(String(15),unique=True,nullable=False)
    consumer_no:Mapped[str]=mapped_column(String(20),unique=True,nullable=False)
    distributor_name:Mapped[str]=mapped_column(ForeignKey("distributor.name"),nullable=False)
    state:Mapped[str]=mapped_column(String(20),nullable=False)
    district:Mapped[str]=mapped_column(String(20),nullable=False)
    threshold_limit:Mapped[float]=mapped_column(Float,nullable=False,default=1.0)
    auto_delivery:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    reports:Mapped[list['Sensor_unit']]=relationship(back_populates='users')
    distributor=relationship("Distributor")

class Distributor(Base):
    __tablename__="distributor"
    id:Mapped[str]=mapped_column(String(20),index=True,primary_key=True)
    name:Mapped[str]=mapped_column(String(30),nullable=False)
    address:Mapped[str]=mapped_column(String(100),nullable=False)
    phone_no:Mapped[str]=mapped_column(String(15),unique=True,nullable=False)
    state:Mapped[str]=mapped_column(String(20),nullable=False)
    district:Mapped[str]=mapped_column(String(20),nullable=False)
    
class Admin(Base):
    __tablename__='admin'
    id:Mapped[str]=mapped_column(String(20),index=True,primary_key=True)

class Alert_log(Base):
    __tablename__="alert_log"
    alert_id:Mapped[str]=mapped_column(String(20),index=True,primary_key=True)
    alert_type:Mapped[str]=mapped_column(String(20),nullable=False)
    delivery_status:Mapped[bool]=mapped_column(bool,nullable=True)
    time_stamp:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(UTC))
    user_id:Mapped[str]=mapped_column(ForeignKey("users.name"),nullable=False)

    users=relationship("Users")

class Sensor_unit(Base):
    __tablename__="sensor_unit"
    sensor_id:Mapped[str]=mapped_column(String(20),primary_key=True,index=True)
    current_weight:Mapped[float]=mapped_column(float,nullable=False)
    connection_status:Mapped[bool]=mapped_column(bool,nullable=True)
    date:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(UTC))
    id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    user:Mapped[list['Users']]=relationship(back_populates='sensor_unit')
    users=relationship('Users')


class Refill_request(Base):
    __tablename__="refill_request"
    request_id:Mapped[str]=mapped_column(String(10),primary_key=True,index=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.user_id'),nullable=False)
    requested_status:Mapped[str]=mapped_column(String(15),nullable=False,default='pending')
    requested_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(UTC))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('distributor.id'),nullable=True)
    approved_date:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

    user=relationship('Users')
    distributor=relationship('Distributor')

