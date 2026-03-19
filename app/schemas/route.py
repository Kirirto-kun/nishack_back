from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.parse import CoordinatePoint


class AiRouteRequest(BaseModel):
    start: CoordinatePoint
    end: CoordinatePoint
    user_prompt: str = Field(min_length=1, max_length=1000)


class MarkerPoint(BaseModel):
    kind: str = Field(pattern=r"^(issue|poi)$")
    id: int
    category: str
    lat: float
    lon: float


class AiRouteResponse(BaseModel):
    route_coords: list[list[float]]  # [lat, lon]
    explanation: str
    avoided_categories: list[str]
    markers: list[MarkerPoint]
    ors_avoid_applied: bool | None = None
    """None — зоны избегания не отправлялись; True — ORS принял avoid_polygons; False — отклонил, маршрут без обхода."""

