from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CoordinatePoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ParseRequest(BaseModel):
    points: list[CoordinatePoint]
    radius_meters: int = Field(default=100, ge=1, le=10_000)


class ParseResponse(BaseModel):
    status: str
    saved_to: Path
    created_at: datetime
    data: dict[str, Any]
