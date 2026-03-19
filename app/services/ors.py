from __future__ import annotations

import logging
from dataclasses import dataclass
from math import cos, radians
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.parse import CoordinatePoint

logger = logging.getLogger(__name__)

# ~111.32 km per degree latitude; longitude shrinks with cos(latitude).
_M_PER_DEG_LAT = 111_320.0


def _half_extent_deg(lat: float, buffer_meters: float) -> tuple[float, float]:
    """Half-side of avoid square in degrees (delta_lon, delta_lat) for ~buffer_meters from center."""
    m_lon = _M_PER_DEG_LAT * max(0.2, cos(radians(lat)))
    return buffer_meters / m_lon, buffer_meters / _M_PER_DEG_LAT


def _square_polygon_lonlat(lon: float, lat: float, buffer_meters: float) -> list[list[float]]:
    # Ring in [lon, lat]; closed. Buffer is half edge length in meters (~square side 2*buffer).
    dlon, dlat = _half_extent_deg(lat, buffer_meters)
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def build_avoid_polygons(
    points_latlon: list[tuple[float, float]],
    *,
    buffer_meters: float = 90.0,
) -> dict[str, Any]:
    """
    GeoJSON Polygon/MultiPolygon for ORS options.avoid_polygons.

    Small degree-based boxes (~5 m) often do not intersect OSM graph edges, so ORS
    returns the same path as without avoidance. Use a real buffer in meters.
    """
    rings: list[list[list[float]]] = []
    for lat, lon in points_latlon:
        rings.append(_square_polygon_lonlat(lon=lon, lat=lat, buffer_meters=buffer_meters))

    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    # MultiPolygon: one polygon per obstacle, each polygon is [exterior_ring]
    return {"type": "MultiPolygon", "coordinates": [[[r]] for r in rings]}


@dataclass(frozen=True)
class OrsRouteResult:
    """ORS foot-walking route as [lat, lon] plus whether avoid_polygons was honored."""

    route_coords: list[list[float]]
    avoid_polygons_sent: bool
    """True if the first request included options.avoid_polygons."""
    avoid_polygons_applied: bool | None
    """
    None — avoid_polygons was not sent.
    True — first response OK with avoid_polygons.
    False — ORS rejected options (e.g. 400); retried without avoidance (same as basic).
    """


async def fetch_route(
    start: CoordinatePoint,
    end: CoordinatePoint,
    avoid_polygons: dict[str, Any] | None,
) -> OrsRouteResult:
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
    sent = bool(avoid_polygons and avoid_polygons.get("coordinates"))
    applied: bool | None = None
    if sent:
        body["options"] = {"avoid_polygons": avoid_polygons}

    timeout = httpx.Timeout(40.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        # Some ORS plans reject large/complex avoid geometries with 400.
        # In that case degrade gracefully to baseline route instead of 500.
        if resp.status_code == 400 and "options" in body:
            logger.warning(
                "ORS rejected avoid_polygons (400), retrying without options. Body snippet: %s",
                (resp.text or "")[:500],
            )
            applied = False
            body.pop("options", None)
            resp = await client.post(url, headers=headers, json=body)
        elif sent and resp.is_success:
            applied = True
        resp.raise_for_status()
        data = resp.json()

    coords_lonlat: list[list[float]] = data["features"][0]["geometry"]["coordinates"]
    # flip to [lat, lon] for frontend convenience
    coords = [[lat, lon] for lon, lat in coords_lonlat]
    return OrsRouteResult(
        route_coords=coords,
        avoid_polygons_sent=sent,
        avoid_polygons_applied=applied,
    )

