from sqlalchemy import select,func,extract
from models import Sensor_unit

async def get_gas_usage()