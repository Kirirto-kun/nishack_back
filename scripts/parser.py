"""
Гео-парсер: Nominatim (reverse) + Overpass (объекты рядом) + опционально OpenWeather.

Запуск из корня бэкенда (с активированным venv):

  python scripts/parser.py --point 43.2380,76.9454 --radius 150

Несколько точек:

  python scripts/parser.py --point 43.24,76.95 --point 43.25,76.96

Из JSON-файла (формат как у ParseRequest):

  {"points": [{"lat": 43.24, "lon": 76.95}], "radius_meters": 200}

  python scripts/parser.py --json my_route.json

Погода: в окружении задай OPENWEATHER_API_KEY (иначе блок openweather в ответе будет null).

Результат: JSON в каталоге nishack_back/output/ (имя с timestamp).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# При `python scripts/parser.py` cwd может быть любым — пакет `app` лежит в корне бэкенда.
_BACK_ROOT = Path(__file__).resolve().parent.parent
if str(_BACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACK_ROOT))

import httpx
from pydantic import ValidationError

from app.schemas import CoordinatePoint, ParseRequest, ParseResponse


OUTPUT_DIR = _BACK_ROOT / "output"
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

    return {
        "point": {
            "lat": point.lat,
            "lon": point.lon,
        },
        "openstreetmap": {
            "reverse_geocode": osm_reverse,
            "nearby_objects_count": len(osm_nearby.get("elements", [])),
            "raw_nearby_response": osm_nearby,
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


def _parse_cli_points(raw_points: list[str]) -> list[CoordinatePoint]:
    out: list[CoordinatePoint] = []
    for p in raw_points:
        parts = p.split(",", 1)
        if len(parts) != 2:
            raise ValueError(f"ожидалось LAT,LON, получено: {p!r}")
        lat_s, lon_s = parts[0].strip(), parts[1].strip()
        out.append(CoordinatePoint(lat=float(lat_s), lon=float(lon_s)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Сборка OSM + погоды по точкам, сохранение в output/*.json",
    )
    ap.add_argument(
        "--point",
        action="append",
        dest="points",
        metavar="LAT,LON",
        help="координаты (можно несколько раз), напр. --point 43.2380,76.9454",
    )
    ap.add_argument(
        "--radius",
        type=int,
        default=100,
        help="радиус Overpass в метрах (default: 100)",
    )
    ap.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        help='путь к JSON: {"points": [{"lat","lon"},...], "radius_meters": 100}',
    )
    args = ap.parse_args()

    if args.json_path is not None:
        if not args.json_path.is_file():
            print(f"Файл не найден: {args.json_path}", file=sys.stderr)
            raise SystemExit(1)
        raw_json = args.json_path.read_text(encoding="utf-8").strip()
        if not raw_json:
            print(
                f"Файл пустой: {args.json_path.resolve()}\n"
                'Нужен JSON, например:\n'
                '  {"points": [{"lat": 43.24, "lon": 76.95}], "radius_meters": 150}',
                file=sys.stderr,
            )
            raise SystemExit(1)
        try:
            payload = ParseRequest.model_validate_json(raw_json)
        except ValidationError as e:
            print(f"Неверный формат в {args.json_path}:\n{e}", file=sys.stderr)
            raise SystemExit(1) from e
    elif args.points:
        try:
            coords = _parse_cli_points(args.points)
        except ValueError as e:
            ap.error(str(e))
        payload = ParseRequest(points=coords, radius_meters=args.radius)
    else:
        ap.print_help()
        print("\nНужно указать --point LAT,LON (один или несколько) либо --json <файл>.", file=sys.stderr)
        raise SystemExit(2)

    try:
        result = asyncio.run(parse_and_store_location_data(payload))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1) from e

    print(f"Готово: {result.saved_to}")


if __name__ == "__main__":
    main()
