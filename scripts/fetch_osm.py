from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select

# Make `app` importable when running as a script.
_BACK_ROOT = Path(__file__).resolve().parent.parent
if str(_BACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACK_ROOT))

from app.db.models.poi import Poi  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@dataclass(frozen=True)
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


def _overpass_q(bbox: BBox) -> str:
    # NOTE: Overpass bbox order is: south,west,north,east (lat,lon,lat,lon)
    s, w, n, e = bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon
    return f"""
[out:json][timeout:60];
(
  node["amenity"~"bar|pub|nightclub|school|kindergarten"]( {s},{w},{n},{e} );
  node["leisure"~"park|garden"]( {s},{w},{n},{e} );
  node["shop"~"alcohol|convenience"]( {s},{w},{n},{e} );
);
out body tags;
"""


def _map_category(tags: dict[str, str]) -> str | None:
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")
    shop = tags.get("shop")

    if amenity in {"bar", "pub", "nightclub"}:
        return "liquor_store"
    if shop == "alcohol":
        return "liquor_store"
    if amenity in {"school", "kindergarten"}:
        return "school"
    if leisure in {"park", "garden"}:
        return "park"
    if shop == "convenience":
        return "convenience"
    return None


async def fetch_overpass(client: httpx.AsyncClient, bbox: BBox) -> dict[str, Any]:
    query = _overpass_q(bbox)
    resp = await client.post(OVERPASS_URL, content=query.encode("utf-8"))
    resp.raise_for_status()
    return resp.json()


async def upsert_pois(payload: dict[str, Any]) -> int:
    elements = payload.get("elements", [])
    inserted_or_updated = 0

    async with AsyncSessionLocal() as db:
        for el in elements:
            if el.get("type") != "node":
                continue
            tags = el.get("tags") or {}
            if not isinstance(tags, dict):
                continue
            if "lat" not in el or "lon" not in el:
                continue

            category = _map_category({str(k): str(v) for k, v in tags.items()})
            if not category:
                continue

            osm_id = int(el["id"])
            lat = float(el["lat"])
            lon = float(el["lon"])
            name = tags.get("name")

            # Manual upsert to stay DB-agnostic with async SQLAlchemy.
            existing = await db.execute(select(Poi).where(Poi.osm_id == osm_id))
            poi = existing.scalar_one_or_none()
            if poi is None:
                poi = Poi(
                    osm_id=osm_id,
                    name=name,
                    category=category,
                    lat=lat,
                    lon=lon,
                    geom=from_shape(Point(lon, lat), srid=4326),
                )
                db.add(poi)
            else:
                poi.name = name
                poi.category = category
                poi.lat = lat
                poi.lon = lon
                poi.geom = from_shape(Point(lon, lat), srid=4326)

            inserted_or_updated += 1

        await db.commit()

    return inserted_or_updated


async def run(bbox: BBox) -> int:
    headers = {
        "User-Agent": "nishack-osm-fetcher/1.0 (local-dev)",
        "Accept": "application/json",
    }
    timeout = httpx.Timeout(60.0, connect=20.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        payload = await fetch_overpass(client, bbox)
    return await upsert_pois(payload)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch OSM POIs via Overpass and upsert into DB table `pois`.")
    ap.add_argument(
        "--bbox",
        required=True,
        metavar="MIN_LAT,MIN_LON,MAX_LAT,MAX_LON",
        help="Bounding box to fetch, e.g. 43.15,76.75,43.35,77.05",
    )
    args = ap.parse_args()

    parts = [p.strip() for p in str(args.bbox).split(",")]
    if len(parts) != 4:
        ap.error("bbox must have 4 comma-separated numbers: MIN_LAT,MIN_LON,MAX_LAT,MAX_LON")
    try:
        bbox = BBox(
            min_lat=float(parts[0]),
            min_lon=float(parts[1]),
            max_lat=float(parts[2]),
            max_lon=float(parts[3]),
        )
    except ValueError:
        ap.error("bbox values must be numbers")

    count = asyncio.run(run(bbox))
    print(f"Upserted POIs: {count}")


if __name__ == "__main__":
    main()

