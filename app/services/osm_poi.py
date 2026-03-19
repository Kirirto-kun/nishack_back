"""
Live POI fetch from Overpass API for AI routing (bars, alcohol shops, etc.).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SEC = 10.0
CACHE_TTL_SEC = 1800  # 30 minutes
_CACHE: dict[tuple[float, float, float, float], tuple[float, list["OsmPoi"]]] = {}


@dataclass(frozen=True)
class OsmPoi:
    osm_id: int
    name: str | None
    category: str
    lat: float
    lon: float


def build_overpass_query(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    *,
    timeout_sec: int = 25,
) -> str:
    """Overpass bbox order: south, west, north, east (lat, lon, lat, lon)."""
    s, w, n, e = min_lat, min_lon, max_lat, max_lon
    return f"""
[out:json][timeout:{timeout_sec}];
(
  node["amenity"~"bar|pub|nightclub|casino|gambling|hookah_lounge|stripclub"]({s},{w},{n},{e});
  node["shop"~"alcohol|tobacco|e-cigarette|gambling"]({s},{w},{n},{e});
  node["amenity"~"school|kindergarten"]({s},{w},{n},{e});
  node["leisure"~"park|garden|playground"]({s},{w},{n},{e});
);
out body tags;
"""


def map_osm_tags_to_category(tags: dict[str, str]) -> str | None:
    """Map OSM tags to internal category slug (must match LLM / frontend vocabulary)."""
    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    leisure = tags.get("leisure", "")

    if amenity in {"bar", "pub", "nightclub", "stripclub"}:
        return "bar"
    if amenity in {"casino", "gambling"} or shop == "gambling":
        return "gambling"
    if amenity == "hookah_lounge":
        return "hookah"
    if shop == "alcohol":
        return "alcohol_shop"
    if shop in {"tobacco", "e-cigarette"}:
        return "tobacco_shop"
    if amenity in {"school", "kindergarten"}:
        return "school"
    if leisure in {"park", "garden", "playground"}:
        return "park"
    return None


def _parse_overpass_elements(payload: dict[str, Any]) -> list[OsmPoi]:
    out: list[OsmPoi] = []
    for el in payload.get("elements", []):
        if el.get("type") != "node":
            continue
        tags_raw = el.get("tags") or {}
        if not isinstance(tags_raw, dict):
            continue
        tags = {str(k): str(v) for k, v in tags_raw.items()}
        if "lat" not in el or "lon" not in el:
            continue
        cat = map_osm_tags_to_category(tags)
        if not cat:
            continue
        name = tags.get("name")
        out.append(
            OsmPoi(
                osm_id=int(el["id"]),
                name=name.strip() if isinstance(name, str) and name.strip() else None,
                category=cat,
                lat=float(el["lat"]),
                lon=float(el["lon"]),
            )
        )
    return out


def _cache_key(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> tuple[float, float, float, float]:
    return (
        round(min_lat, 3),
        round(min_lon, 3),
        round(max_lat, 3),
        round(max_lon, 3),
    )


async def fetch_pois_in_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    *,
    use_cache: bool = True,
) -> list[OsmPoi]:
    """
    Fetch POI nodes from Overpass for the given WGS84 bbox.
    On failure or timeout returns [] (graceful degradation).
    """
    key = _cache_key(min_lat, min_lon, max_lat, max_lon)
    now = time.monotonic()
    if use_cache and key in _CACHE:
        exp, cached = _CACHE[key]
        if now < exp:
            return list(cached)

    query = build_overpass_query(min_lat, min_lon, max_lat, max_lon)
    headers = {"User-Agent": "nishack-ai-route/1.0 (overpass)"}
    try:
        timeout = httpx.Timeout(OVERPASS_TIMEOUT_SEC, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post(OVERPASS_URL, content=query.encode("utf-8"))
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("Overpass fetch failed (continuing without live OSM POI): %s", e)
        return []

    pois = _parse_overpass_elements(payload)
    if use_cache:
        _CACHE[key] = (now + CACHE_TTL_SEC, list(pois))
    return pois
