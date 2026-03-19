from __future__ import annotations

from pydantic import BaseModel, Field


class CurrentWeatherRead(BaseModel):
    temp: float = Field(description="Temperature, °C")
    wind: float = Field(description="Wind speed, m/s")
    humidity: float = Field(description="Relative humidity, %")


class HeatmapPointRead(BaseModel):
    lat: float
    lon: float
    intensity: float = Field(ge=0.0, le=1.0)


class ViewportBBoxRead(BaseModel):
    """Область карты, под которую построена сетка heatmap."""

    south: float
    west: float
    north: float
    east: float


class WeatherSampleRead(BaseModel):
    """Точка, для которой запрошена погода (центр области просмотра)."""

    lat: float
    lon: float


class FireRiskHeatmapRead(BaseModel):
    current_weather: CurrentWeatherRead
    base_risk: float = Field(ge=0.0, le=1.0)
    heatmap: list[HeatmapPointRead]
    viewport_bbox: ViewportBBoxRead | None = None
    weather_sample: WeatherSampleRead | None = None
