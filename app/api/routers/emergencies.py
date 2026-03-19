from __future__ import annotations

import math
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import get_settings
from app.schemas.emergency import (
    CurrentWeatherRead,
    FireRiskHeatmapRead,
    HeatmapPointRead,
    ViewportBBoxRead,
    WeatherSampleRead,
)

router = APIRouter(prefix="/api/emergencies", tags=["emergencies"])

# Центр Алматы (как на карте заявок)
ALMATY_LAT = 43.238293
ALMATY_LON = 76.945465

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

GRID_SIZE = 7
# ~1.2 км между узлами по широте (дефолтный bbox вокруг Алматы)
GRID_STEP_DEG = 0.011

# Лимиты bbox от клиента (защита от слишком больших запросов)
MAX_VIEW_SPAN_DEG = 1.35  # ~150 км по диагонали
MIN_VIEW_SPAN_DEG = 0.002
# Целевой шаг сетки в градусах (~1 км); итог 5…16 узлов на ось
GRID_CELL_TARGET_DEG = 0.009


def calculate_fire_risk(temp: float, wind_speed: float, humidity: float) -> float:
    """Упрощённый индекс риска 0..1: жара, ветер, сухой воздух."""
    temp_n = max(0.0, min(1.0, (temp - 5.0) / 40.0))
    wind_n = max(0.0, min(1.0, wind_speed / 15.0))
    humidity_n = max(0.0, min(1.0, (100.0 - humidity) / 100.0))
    risk = 0.45 * temp_n + 0.30 * wind_n + 0.25 * humidity_n
    return round(max(0.0, min(1.0, risk)), 4)


def _spatial_intensity(
    base_risk: float,
    i: int,
    j: int,
    n_lat: int,
    n_lon: int,
) -> float:
    """Центр кадра — ниже; края видимой области (часто загород) — выше."""
    cx = (n_lat - 1) / 2.0
    cy = (n_lon - 1) / 2.0
    # Нормируем по полуоси, чтобы углы кадра давали t≈1
    dist = math.hypot(
        (i - cx) / max(cx, 1e-6),
        (j - cy) / max(cy, 1e-6),
    )
    max_corner = math.hypot(1.0, 1.0)
    t = min(1.0, dist / max_corner)
    raw = base_risk * (0.58 + 0.52 * t)
    return round(max(0.05, min(1.0, raw)), 4)


def _default_viewport_bbox() -> tuple[float, float, float, float]:
    half = (GRID_SIZE - 1) / 2.0 * GRID_STEP_DEG
    return (
        ALMATY_LAT - half,
        ALMATY_LON - half,
        ALMATY_LAT + half,
        ALMATY_LON + half,
    )


def _grid_dims_for_span(span_lat: float, span_lon: float) -> tuple[int, int]:
    n_lat = int(round(span_lat / GRID_CELL_TARGET_DEG)) + 1
    n_lon = int(round(span_lon / GRID_CELL_TARGET_DEG)) + 1
    n_lat = max(5, min(16, n_lat))
    n_lon = max(5, min(16, n_lon))
    return n_lat, n_lon


def _build_heatmap_for_viewport(
    base_risk: float,
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    n_lat: int,
    n_lon: int,
) -> list[HeatmapPointRead]:
    span_lat = north - south
    span_lon = east - west
    out: list[HeatmapPointRead] = []
    for i in range(n_lat):
        for j in range(n_lon):
            if n_lat > 1:
                lat = south + span_lat * (i / (n_lat - 1))
            else:
                lat = (south + north) / 2.0
            if n_lon > 1:
                lon = west + span_lon * (j / (n_lon - 1))
            else:
                lon = (west + east) / 2.0
            intensity = _spatial_intensity(base_risk, i, j, n_lat, n_lon)
            out.append(HeatmapPointRead(lat=lat, lon=lon, intensity=intensity))
    return out


def _resolve_viewport(
    south: float | None,
    west: float | None,
    north: float | None,
    east: float | None,
) -> tuple[float, float, float, float, int, int]:
    """Возвращает south, west, north, east, n_lat, n_lon."""
    provided = sum(1 for x in (south, west, north, east) if x is not None)
    if provided not in (0, 4):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Укажите все четыре границы области (south, west, north, east) или не передавайте их — тогда используется вид по умолчанию вокруг Алматы.",
        )

    if provided == 0:
        s, w, n, e = _default_viewport_bbox()
        return s, w, n, e, GRID_SIZE, GRID_SIZE

    assert south is not None and west is not None and north is not None and east is not None
    if south >= north:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный bbox: south должно быть меньше north.",
        )
    if west >= east:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный bbox: west должно быть меньше east.",
        )

    span_lat = north - south
    span_lon = east - west
    if span_lat < MIN_VIEW_SPAN_DEG or span_lon < MIN_VIEW_SPAN_DEG:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Область слишком мелкая — отдалите карту чуть дальше.",
        )
    if span_lat > MAX_VIEW_SPAN_DEG or span_lon > MAX_VIEW_SPAN_DEG:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Область слишком большая — приблизьте карту (максимум ~1.3° по широте или долготе).",
        )

    n_lat, n_lon = _grid_dims_for_span(span_lat, span_lon)
    return south, west, north, east, n_lat, n_lon


@router.get("/fire_risk_heatmap", response_model=FireRiskHeatmapRead)
async def fire_risk_heatmap(
    south: float | None = Query(None, description="Южная граница видимой карты (широта)"),
    west: float | None = Query(None, description="Западная граница (долгота)"),
    north: float | None = Query(None, description="Северная граница (широта)"),
    east: float | None = Query(None, description="Восточная граница (долгота)"),
) -> FireRiskHeatmapRead:
    settings = get_settings()
    if not settings.openweather_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenWeather API key is not configured. Set OPENWEATHER_API_KEY in the backend environment.",
        )

    s, w, n, e, n_lat, n_lon = _resolve_viewport(south, west, north, east)
    weather_lat = (s + n) / 2.0
    weather_lon = (w + e) / 2.0

    params = {
        "lat": weather_lat,
        "lon": weather_lon,
        "appid": settings.openweather_api_key,
        "units": "metric",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(OPENWEATHER_URL, params=params)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenWeather service unreachable: {e!s}",
        ) from e

    if resp.status_code == 401 or resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenWeather rejected the API key (invalid or inactive). Check OPENWEATHER_API_KEY.",
        )

    if resp.status_code != 200:
        try:
            body: Any = resp.json()
            msg = body.get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenWeather error ({resp.status_code}): {msg}",
        )

    data = resp.json()
    try:
        temp = float(data["main"]["temp"])
        humidity = float(data["main"]["humidity"])
        wind_speed = float(data.get("wind", {}).get("speed", 0.0))
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenWeather returned an unexpected payload (missing temp/humidity/wind).",
        ) from e

    base_risk = calculate_fire_risk(temp, wind_speed, humidity)
    current = CurrentWeatherRead(temp=temp, wind=wind_speed, humidity=humidity)

    heatmap = _build_heatmap_for_viewport(base_risk, s, w, n, e, n_lat=n_lat, n_lon=n_lon)

    return FireRiskHeatmapRead(
        current_weather=current,
        base_risk=base_risk,
        heatmap=heatmap,
        viewport_bbox=ViewportBBoxRead(south=s, west=w, north=n, east=e),
        weather_sample=WeatherSampleRead(lat=weather_lat, lon=weather_lon),
    )
