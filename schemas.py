# schemas.py

from pydantic import BaseModel

class LocationCreate(BaseModel):
    city: str
    region: str
    country: str

class PrinterConditions(BaseModel):
    location_id: int
    min_temp: float
    max_wind: float
    max_precip: float
    print_speed: float  # например, этажей в час

class ForecastRequest(BaseModel):
    location_id: int

class ForecastPrinterRequest(BaseModel):
    location_id: int
    min_temp: float
    max_wind: float
    max_precip: float
    print_speed: float  # например, этажей в час

class WeatherRequest(BaseModel):
    location_id: int
