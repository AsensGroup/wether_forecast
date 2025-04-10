from fastapi.responses import FileResponse
from threading import Thread
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_
from collections import defaultdict
from datetime import datetime, timedelta
import time

from database import Base, engine, SessionLocal
from models import Location, WeatherData
from schemas import (
    LocationCreate,
    PrinterConditions,
    ForecastRequest,
    ForecastPrinterRequest,
    WeatherRequest
)

app = FastAPI()
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def geocode_location(city: str, region: str, country: str):
    query = f"{city}, {region}, {country}"
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": "GeoApp/1.0"}

    response = requests.get(url, params=params, headers=headers)
    data = response.json()

    if not data:
        raise HTTPException(status_code=404, detail="Локация не найдена")

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    return lat, lon

@app.post("/location/")
def add_location(location: LocationCreate):
    db = SessionLocal()

    existing = db.query(Location).filter_by(
        city=location.city.strip().lower(),
        region=location.region.strip().lower(),
        country=location.country.strip().lower()
    ).first()

    if existing:
        db.close()
        return {
            "id": existing.id,
            "city": existing.city,
            "region": existing.region,
            "country": existing.country,
            "latitude": existing.latitude,
            "longitude": existing.longitude
        }

    lat, lon = geocode_location(location.city, location.region, location.country)

    loc = Location(
        city=location.city.strip().lower(),
        region=location.region.strip().lower(),
        country=location.country.strip().lower(),
        latitude=lat,
        longitude=lon
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    db.close()

    load_weather(loc.id)

    return {
        "id": loc.id,
        "city": loc.city,
        "region": loc.region,
        "country": loc.country,
        "latitude": loc.latitude,
        "longitude": loc.longitude
    }

def fetch_hourly_weather(lat, lon, start_date, end_date):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,wind_speed_10m,precipitation",
        "timezone": "auto"
    }

    response = requests.get(url, params=params)
    data = response.json()

    if "hourly" not in data:
        raise HTTPException(status_code=500, detail="Ошибка получения данных погоды")

    return data["hourly"]

def load_weather(location_id: int):
    db = SessionLocal()
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        db.close()
        raise HTTPException(status_code=404, detail="Локация не найдена")

    start_date = "2014-01-01"
    end_date = "2023-12-31"
    weather = fetch_hourly_weather(loc.latitude, loc.longitude, start_date, end_date)

    for i in range(len(weather["time"])):
        w = WeatherData(
            location_id=loc.id,
            datetime=datetime.fromisoformat(weather["time"][i]),
            temperature=weather["temperature_2m"][i],
            wind_speed=weather["wind_speed_10m"][i],
            precipitation=weather["precipitation"][i]
        )
        db.add(w)
        if i % 500 == 0:
            db.commit()
            time.sleep(0.2)
    db.commit()
    db.close()

@app.post("/weather/fetch/")
def weather_fetch_api(request: WeatherRequest):
    load_weather(request.location_id)
    return {"status": "ok"}

@app.post("/printer/working-hours/")
def get_working_hours(conditions: PrinterConditions):
    db = SessionLocal()
    weather_data = db.query(WeatherData).filter(WeatherData.location_id == conditions.location_id).all()

    working_hours = []
    day_summary = defaultdict(int)

    for w in weather_data:
        if (
            w.temperature >= conditions.min_temp and
            w.wind_speed <= conditions.max_wind and
            w.precipitation <= conditions.max_precip
        ):
            working_hours.append(w.datetime.isoformat())
            day = w.datetime.date()
            day_summary[day] += 1

    total_hours = len(working_hours)
    total_output = total_hours * conditions.print_speed
    calendar = [{"date": str(day), "hours": hours} for day, hours in day_summary.items()]
    db.close()
    return {
        "total_hours": total_hours,
        "total_output": total_output,
        "calendar": calendar
    }

@app.post("/weather/forecast/")
def generate_forecast(request: ForecastRequest):
    db = SessionLocal()
    data = db.query(WeatherData).filter(WeatherData.location_id == request.location_id).all()
    if not data:
        raise HTTPException(status_code=404, detail="Нет погодных данных по этой локации")

    hourly_groups = {}
    count_groups = {}

    for entry in data:
        key = entry.datetime.strftime("%m-%d %H")
        if key not in hourly_groups:
            hourly_groups[key] = {"temperature": 0.0, "wind": 0.0, "precip": 0.0}
            count_groups[key] = 0
        hourly_groups[key]["temperature"] += entry.temperature
        hourly_groups[key]["wind"] += entry.wind_speed
        hourly_groups[key]["precip"] += entry.precipitation
        count_groups[key] += 1

    year = 2025
    base_date = datetime(year, 1, 1, 0, 0)
    forecast = []

    for i in range(365 * 24):
        dt = base_date + timedelta(hours=i)
        key = dt.strftime("%m-%d %H")

        if key in hourly_groups:
            count = count_groups[key]
            avg = hourly_groups[key]
            forecast.append({
                "datetime": dt.isoformat(),
                "temperature": round(avg["temperature"] / count, 2),
                "wind": round(avg["wind"] / count, 2),
                "precipitation": round(avg["precip"] / count, 2)
            })

    db.close()
    return {
        "location_id": request.location_id,
        "forecast": forecast
    }

@app.post("/printer/forecast-hours/")
def forecast_working_hours(params: ForecastPrinterRequest):
    db = SessionLocal()
    data = db.query(WeatherData).filter(WeatherData.location_id == params.location_id).all()

    if not data:
        try:
            load_weather(params.location_id)
            data = db.query(WeatherData).filter(WeatherData.location_id == params.location_id).all()
        except Exception:
            db.close()
            raise HTTPException(status_code=500, detail="Не удалось загрузить погодные данные")

    if not data:
        db.close()
        raise HTTPException(status_code=404, detail="Нет данных для прогноза")

    hourly_groups = {}
    count_groups = {}

    for entry in data:
        key = entry.datetime.strftime("%m-%d %H")
        if key not in hourly_groups:
            hourly_groups[key] = {"temperature": 0.0, "wind": 0.0, "precip": 0.0}
            count_groups[key] = 0
        hourly_groups[key]["temperature"] += entry.temperature
        hourly_groups[key]["wind"] += entry.wind_speed
        hourly_groups[key]["precip"] += entry.precipitation
        count_groups[key] += 1

    # ⏱️ Отладка ключей:
    print(f"🔍 Пример ключей из погодных данных: {list(hourly_groups.keys())[:5]}")

    year = 2025
    base_date = datetime(year, 1, 1, 0, 0)
    working_hours = []
    day_summary = defaultdict(int)

    for i in range(365 * 24):
        dt = base_date + timedelta(hours=i)
        key = dt.strftime("%m-%d %H")

        if i < 5:
            print(f"🔧 Генерация ключа {i}: {key}")

        if key in hourly_groups:
            count = count_groups[key]
            avg = hourly_groups[key]
            temp = avg["temperature"] / count
            wind = avg["wind"] / count
            precip = avg["precip"] / count

            if (
                temp >= params.min_temp and
                wind <= params.max_wind and
                precip <= params.max_precip
            ):
                working_hours.append(dt.isoformat())
                day_summary[dt.date()] += 1

    total_hours = len(working_hours)
    total_output = total_hours * params.print_speed
    calendar = [{"date": str(day), "hours": hours} for day, hours in day_summary.items()]

    print(f"✅ Всего подходящих рабочих часов: {total_hours}")
    db.close()

    return {
        "location_id": params.location_id,
        "total_hours": total_hours,
        "total_output": total_output,
        "calendar": calendar
    }

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
