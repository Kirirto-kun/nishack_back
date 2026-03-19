from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.parse import CoordinatePoint


def _square_polygon_lonlat(lon: float, lat: float, delta: float = 0.00005) -> list[list[float]]:
    # returns ring coordinates (closed) in [lon,lat]
    return [
        [lon - delta, lat - delta],
        [lon + delta, lat - delta],
        [lon + delta, lat + delta],
        [lon - delta, lat + delta],
        [lon - delta, lat - delta],
    ]


def build_avoid_polygons(points_latlon: list[tuple[float, float]]) -> dict[str, Any]:
    features = []
    for lat, lon in points_latlon:
        ring = _square_polygon_lonlat(lon=lon, lat=lat)
        features.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


async def fetch_route(
    start: CoordinatePoint,
    end: CoordinatePoint,
    avoid_polygons: dict[str, Any] | None,
) -> list[list[float]]:
    settings = get_settings()
    if not settings.ors_api_key:
        raise RuntimeError("ORS_API_KEY is not set")
    url = f"{settings.ors_base_url.rstrip('/')}/v2/directions/foot-walking/geojson"
    headers = {"Authorization": settings.ors_api_key, "Content-Type": "application/json"}

    body: dict[str, Any] = {
        "coordinates": [
            [start.lon, start.lat],
            [end.lon, end.lat],
        ],
    }
    if avoid_polygons and avoid_polygons.get("features"):
        body["options"] = {"avoid_polygons": avoid_polygons}

    timeout = httpx.Timeout(40.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    coords_lonlat: list[list[float]] = data["features"][0]["geometry"]["coordinates"]
    # flip to [lat, lon] for frontend convenience
    return [[lat, lon] for lon, lat in coords_lonlat]

