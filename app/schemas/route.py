from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.parse import CoordinatePoint


class AiRouteRequest(BaseModel):
    start: CoordinatePoint
    end: CoordinatePoint
    user_prompt: str = Field(min_length=1, max_length=1000)


class MarkerPoint(BaseModel):
    kind: str = Field(pattern=r"^(issue|poi|osm_poi)$")
    id: int
    category: str
    lat: float
    lon: float
    title: str = Field(min_length=1, max_length=500, description="Название заявки или POI для карты")
    image_url: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5, description="Только для issue")
    source: str | None = Field(
        default=None,
        description="db — POI из БД; live_osm — точка из Overpass при построении маршрута",
    )


class AiRouteResponse(BaseModel):
    route_coords: list[list[float]]  # [lat, lon]
    explanation: str
    avoided_categories: list[str]
    markers: list[MarkerPoint]
    ors_avoid_applied: bool | None = None
    """None — зоны избегания не отправлялись; True — ORS принял avoid_polygons; False — отклонил, маршрут без обхода."""

