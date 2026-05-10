from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import ETLRun, Geography
from app.services.geojson import geometry_bbox
from app.services.postgis import sync_geography_geoms

STATCAN_CSD_LAYER_URL = (
    "https://geo.statcan.gc.ca/geo_wa/rest/services/2021/"
    "Cartographic_boundary_files/MapServer/9/query"
)
GEOMETRY_SOURCE = (
    "Statistics Canada 2021 cartographic census subdivision boundary, "
    "filtered to GTA municipalities."
)

GTA_MUNICIPALITIES = {
    "3520005": ("Toronto", "Toronto"),
    "3521005": ("Mississauga", "Peel Region"),
    "3521010": ("Brampton", "Peel Region"),
    "3521024": ("Caledon", "Peel Region"),
    "3519028": ("Vaughan", "York Region"),
    "3519036": ("Markham", "York Region"),
    "3519038": ("Richmond Hill", "York Region"),
    "3519046": ("Aurora", "York Region"),
    "3519048": ("Newmarket", "York Region"),
    "3519049": ("King", "York Region"),
    "3519044": ("Whitchurch-Stouffville", "York Region"),
    "3519054": ("East Gwillimbury", "York Region"),
    "3519070": ("Georgina", "York Region"),
    "3518001": ("Pickering", "Durham Region"),
    "3518005": ("Ajax", "Durham Region"),
    "3518009": ("Whitby", "Durham Region"),
    "3518013": ("Oshawa", "Durham Region"),
    "3518017": ("Clarington", "Durham Region"),
    "3518029": ("Uxbridge", "Durham Region"),
    "3518020": ("Scugog", "Durham Region"),
    "3518039": ("Brock", "Durham Region"),
    "3524001": ("Oakville", "Halton Region"),
    "3524002": ("Burlington", "Halton Region"),
    "3524009": ("Milton", "Halton Region"),
    "3524015": ("Halton Hills", "Halton Region"),
}


def build_statcan_query_url(csd_uids: list[str]) -> str:
    quoted_ids = ",".join(f"'{geoid}'" for geoid in csd_uids)
    params = {
        "where": f"CSDUID IN ({quoted_ids})",
        "outFields": "CSDUID,CSDNAME,CSDTYPE,PRUID,DGUID",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    return f"{STATCAN_CSD_LAYER_URL}?{urlencode(params)}"


def fetch_geojson(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_feature(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geoid = str(properties.get("CSDUID") or properties.get("csduid") or "")
    if not geoid:
        raise ValueError("Boundary feature is missing CSDUID.")

    fallback_name, fallback_region = GTA_MUNICIPALITIES.get(geoid, (geoid, None))
    geometry = feature.get("geometry")
    if not geometry:
        raise ValueError(f"Boundary feature {geoid} is missing geometry.")

    return {
        "geoid": geoid,
        "name": str(properties.get("CSDNAME") or fallback_name),
        "type": "municipality",
        "county": str(properties.get("CDNAME") or fallback_region or ""),
        "state": "ON",
        "geometry": geometry,
        "bbox": geometry_bbox(geometry),
        "geometry_source": GEOMETRY_SOURCE,
    }


def upsert_geographies(db, geographies: list[dict[str, Any]]) -> int:
    count = 0
    for item in geographies:
        geography = db.query(Geography).filter(Geography.geoid == item["geoid"]).one_or_none()
        if geography is None:
            geography = Geography(**item)
            db.add(geography)
        else:
            for key, value in item.items():
                setattr(geography, key, value)
        count += 1
    return count


def update_seed_file(seed_path: Path, geographies: list[dict[str, Any]]) -> int:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in geographies}
    updated = 0

    for item in seed["geographies"]:
        geography = by_name.get(item["name"])
        if geography is None:
            continue
        item["geoid"] = geography["geoid"]
        item["type"] = geography["type"]
        item["county"] = geography["county"]
        item["state"] = geography["state"]
        item["geometry"] = geography["geometry"]
        item["bbox"] = geography["bbox"]
        item["geometry_source"] = geography["geometry_source"]
        updated += 1

    seed["metadata"]["source"] = "demo_seed_gta_municipalities_statcan_csd_cartographic"
    seed["metadata"]["year"] = 2021
    seed_path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return updated


def fetch_gta_geographies(url: str | None = None) -> list[dict[str, Any]]:
    source_url = url or build_statcan_query_url(list(GTA_MUNICIPALITIES))
    payload = fetch_geojson(source_url)
    geographies = [normalize_feature(feature) for feature in payload.get("features", [])]
    returned = {geography["geoid"] for geography in geographies}
    missing = sorted(set(GTA_MUNICIPALITIES) - returned)
    if missing:
        raise ValueError(f"Statistics Canada response is missing expected CSDUIDs: {', '.join(missing)}")
    return geographies


def load_gta_geographies(url: str | None = None) -> int:
    started_at = datetime.now(UTC)
    init_db()
    db = SessionLocal()
    try:
        geographies = fetch_gta_geographies(url)
        if not geographies:
            raise ValueError("No geography features returned by Statistics Canada.")
        row_count = upsert_geographies(db, geographies)
        db.flush()
        sync_geography_geoms(db)
        db.add(
            ETLRun(
                source="statistics_canada_2021_csd_boundaries",
                status="success",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                row_count=row_count,
            )
        )
        db.commit()
        return row_count
    except Exception as exc:
        db.rollback()
        db.add(
            ETLRun(
                source="statistics_canada_2021_csd_boundaries",
                status="failed",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                row_count=0,
                error_message=str(exc),
            )
        )
        db.commit()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load GTA municipal boundaries from Statistics Canada.")
    parser.add_argument("--print-url", action="store_true", help="Print the Statistics Canada query URL and exit.")
    parser.add_argument("--update-seed", action="store_true", help="Refresh packaged demo seed geometries.")
    parser.add_argument("--url", help="Override the Statistics Canada GeoJSON query URL.")
    args = parser.parse_args()

    url = args.url or build_statcan_query_url(list(GTA_MUNICIPALITIES))
    if args.print_url:
        print(url)
        return

    if args.update_seed:
        row_count = update_seed_file(PROJECT_ROOT / "app" / "data" / "demo_seed.json", fetch_gta_geographies(url))
        print(f"Updated {row_count} packaged seed geography rows.")
        return

    row_count = load_gta_geographies(url)
    print(f"Loaded {row_count} GTA geography rows.")


if __name__ == "__main__":
    main()
