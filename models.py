# models.py

from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base
from datetime import datetime
from sqlalchemy import ForeignKey


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String)
    region = Column(String)
    country = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"))
    datetime = Column(DateTime)
    temperature = Column(Float)
    wind_speed = Column(Float)
    precipitation = Column(Float)
    source = Column(String, default="open-meteo")