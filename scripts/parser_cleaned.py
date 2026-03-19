import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.schemas import CoordinatePoint, ParseRequest, ParseResponse


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OPENWEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall"


async def fetch_osm_reverse_geocode(
    client: httpx.AsyncClient, lat: float, lon: float
) -> dict[str, Any]:
    response = await client.get(
        NOMINATIM_URL,
        params={
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "zoom": 18,
        },
    )
    response.raise_for_status()
    return response.json()


async def fetch_osm_nearby_objects(
    client: httpx.AsyncClient, lat: float, lon: float, radius_meters: int
) -> dict[str, Any]:
    query = f"""
    [out:json][timeout:25];
    (
      node(around:{radius_meters},{lat},{lon});
      way(around:{radius_meters},{lat},{lon});
      relation(around:{radius_meters},{lat},{lon});
    );
    out body center tags;
    """
    response = await client.post(OVERPASS_URL, content=query.encode("utf-8"))
    response.raise_for_status()
    return response.json()


def filter_osm_elements(payload: dict[str, Any]) -> dict[str, Any]:
    elements = payload.get("elements", [])
    filtered_elements = [
        element
        for element in elements
        if not (element.get("type") == "node" and "tags" not in element)
    ]

    filtered_payload = dict(payload)
    filtered_payload["elements"] = filtered_elements
    return filtered_payload


async def fetch_openweather(
    client: httpx.AsyncClient, lat: float, lon: float
) -> dict[str, Any] | None:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return None

    response = await client.get(
        OPENWEATHER_URL,
        params={
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric",
            "lang": "ru",
        },
    )
    response.raise_for_status()
    return response.json()


def build_output_path_for_route() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_DIR / f"osm_weather_route_{timestamp}.json"


async def parse_point(
    client: httpx.AsyncClient,
    point: CoordinatePoint,
    radius_meters: int,
) -> dict[str, Any]:
    osm_reverse, osm_nearby, openweather = await asyncio.gather(
        fetch_osm_reverse_geocode(client, point.lat, point.lon),
        fetch_osm_nearby_objects(client, point.lat, point.lon, radius_meters),
        fetch_openweather(client, point.lat, point.lon),
    )
    filtered_osm_nearby = filter_osm_elements(osm_nearby)

    return {
        "point": {
            "lat": point.lat,
            "lon": point.lon,
        },
        "openstreetmap": {
            "reverse_geocode": osm_reverse,
            "nearby_objects_count": len(filtered_osm_nearby.get("elements", [])),
            "raw_nearby_response": filtered_osm_nearby,
        },
        "openweather": openweather,
    }


async def parse_and_store_location_data(payload: ParseRequest) -> ParseResponse:
    headers = {
        "User-Agent": "geo-parser-fastapi/1.0 (contact: local-dev)",
        "Accept": "application/json",
    }

    timeout = httpx.Timeout(40.0, connect=20.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        try:
            point_results = await asyncio.gather(
                *[
                    parse_point(client, point, payload.radius_meters)
                    for point in payload.points
                ]
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(
                f"External API request failed with status {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Network error while fetching data: {exc}") from exc

    created_at = datetime.now(UTC)
    result: dict[str, Any] = {
        "route": {
            "points_count": len(payload.points),
            "radius_meters": payload.radius_meters,
        },
        "created_at": created_at.isoformat(),
        "points": point_results,
    }

    output_path = build_output_path_for_route()
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ParseResponse(
        status="success",
        saved_to=output_path,
        created_at=created_at,
        data=result,
    )
