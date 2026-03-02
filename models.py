from sqlalchemy import DateTime,ForeignKey,Integer,String,Text
from sqlalchemy.orm import Mapped,mapped_column,relationship,DateTime
from database import Base
from datetime import UTC, datetime


class Users(Base):
    __tablename__="users"
    id:Mapped[str]=mapped_column(String(20),index=True,primary_key=True)
    name:Mapped[str]=mapped_column(String(30),nullable=False)
    address:Mapped[str]=mapped_column(String(100),nullable=False)
    phone_no:Mapped[str]=mapped_column(String(15),unique=True,nullable=False)
    consumer_no:Mapped[str]=mapped_column(String(20),unique=True,nullable=False)
    distributor_name:Mapped[str]=mapped_column(ForeignKey("distributor.name"),nullable=False)
    state:Mapped[str]=mapped_column(String(20),nullable=False)
    district:Mapped[str]=mapped_column(String(20),nullable=False)

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
    threshold_value:Mapped[float]=mapped_column(float,nullable=False)
    id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)

    users=relationship('Users')

class Refill_request(Base):
    request_id:Mapped[str]=mapped_column(String(10),primary_key=True,index=True)
    requested_status:Mapped[str]=mapped_column(String(10),nullable=False)
    requested_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(UTC))

    