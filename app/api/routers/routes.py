from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.enums import IssueStatus
from app.db.models.issue import Issue
from app.db.models.poi import Poi
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.route import AiRouteRequest, AiRouteResponse, MarkerPoint
from app.services.ors import build_avoid_polygons, fetch_route
from app.services.osm_poi import fetch_pois_in_bbox
from app.services.route_ai import select_avoid_categories

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/basic_route", response_model=list[list[float]])
async def basic_route(
    body: AiRouteRequest,
    _db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> list[list[float]]:
    # Same payload shape, but ignores AI and avoid_polygons.
    res = await fetch_route(body.start, body.end, avoid_polygons=None)
    return res.route_coords


@router.post("/ai_route", response_model=AiRouteResponse)
async def ai_route(
    body: AiRouteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> AiRouteResponse:
    # BBox + padding (degrees) — чуть шире, чтобы захватить POI в стороне от прямой A–B
    pad = 0.015
    min_lat = min(body.start.lat, body.end.lat) - pad
    max_lat = max(body.start.lat, body.end.lat) + pad
    min_lon = min(body.start.lon, body.end.lon) - pad
    max_lon = max(body.start.lon, body.end.lon) + pad

    envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)

    issues_stmt = (
        select(Issue)
        .where(Issue.status.in_([IssueStatus.approved, IssueStatus.in_progress]))
        .where(Issue.geom.is_not(None))
        .where(ST_Intersects(Issue.geom, envelope))
    )
    pois_stmt = select(Poi).where(ST_Intersects(Poi.geom, envelope))

    live_osm_task = asyncio.create_task(fetch_pois_in_bbox(min_lat, min_lon, max_lat, max_lon))

    issues_res = await db.execute(issues_stmt)
    pois_res = await db.execute(pois_stmt)
    issues = list(issues_res.scalars().all())
    pois = list(pois_res.scalars().all())
    live_osm = await live_osm_task

    categories: set[str] = set()
    for it in issues:
        if it.category:
            categories.add(it.category)
    for it in pois:
        categories.add(it.category)
    for lp in live_osm:
        categories.add(lp.category)
    found_categories = sorted(categories)

    avoid_categories, explanation = await select_avoid_categories(body.user_prompt, found_categories)
    avoid_set = set(avoid_categories)

    # Deterministic safety rule: infrastructure is treated as potentially unsafe (child-safety UX).
    # If user explicitly asked to not avoid it, keep LLM choice.
    if "infrastructure" in found_categories and "infrastructure" not in avoid_set:
        prompt_l = body.user_prompt.lower()
        explicitly_dont_avoid = ("не обход" in prompt_l or "не избег" in prompt_l) and (
            "infrastructure" in prompt_l or "инфраструкт" in prompt_l
        )
        if not explicitly_dont_avoid:
            avoid_categories.append("infrastructure")
            avoid_set.add("infrastructure")
            explanation = f"{explanation.strip()} Также учтена категория infrastructure как потенциально опасная."

    avoided_points: list[tuple[float, float]] = []
    markers: list[MarkerPoint] = []

    for it in issues:
        if not it.category or it.category not in avoid_set:
            continue
        avoided_points.append((float(it.latitude), float(it.longitude)))
        markers.append(
            MarkerPoint(
                kind="issue",
                id=int(it.id),
                category=it.category,
                lat=float(it.latitude),
                lon=float(it.longitude),
                title=it.title,
                image_url=it.image_url,
                priority=int(it.priority),
            )
        )

    for p in pois:
        if p.category not in avoid_set:
            continue
        avoided_points.append((float(p.lat), float(p.lon)))
        poi_title = (p.name or "").strip() or f"POI · {p.category}"
        markers.append(
            MarkerPoint(
                kind="poi",
                id=int(p.id),
                category=p.category,
                lat=float(p.lat),
                lon=float(p.lon),
                title=poi_title,
                image_url=None,
                priority=None,
                source="db",
            )
        )

    for lp in live_osm:
        if lp.category not in avoid_set:
            continue
        avoided_points.append((lp.lat, lp.lon))
        poi_title = (lp.name or "").strip() or f"OSM · {lp.category}"
        markers.append(
            MarkerPoint(
                kind="osm_poi",
                id=int(lp.osm_id),
                category=lp.category,
                lat=lp.lat,
                lon=lp.lon,
                title=poi_title[:500],
                image_url=None,
                priority=None,
                source="live_osm",
            )
        )

    avoid_polygons = build_avoid_polygons(avoided_points) if avoided_points else None
    ors = await fetch_route(body.start, body.end, avoid_polygons)

    return AiRouteResponse(
        route_coords=ors.route_coords,
        explanation=explanation,
        avoided_categories=avoid_categories,
        markers=markers,
        ors_avoid_applied=ors.avoid_polygons_applied,
    )

