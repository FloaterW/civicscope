from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.geojson import compact_geometry, geometry_bbox

STATCAN_CT_LAYER_URL = (
    "https://geo.statcan.gc.ca/geo_wa/rest/services/2021/"
    "Cartographic_boundary_files/MapServer/11/query"
)
DEFAULT_CMA_PREFIXES = ("535", "532", "537")
GEOMETRY_SOURCE = (
    "Statistics Canada 2021 cartographic census tract boundary; filtered to GTA "
    "municipalities by tract centroid."
)


def build_statcan_ct_query_url(cma_prefixes: tuple[str, ...] = DEFAULT_CMA_PREFIXES) -> str:
    where = " OR ".join(f"CTUID LIKE '{prefix}%'" for prefix in cma_prefixes)
    params = {
        "where": where,
        "outFields": "CTUID,DGUID,CTNAME,PRUID",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": "2000",
    }
    return f"{STATCAN_CT_LAYER_URL}?{urlencode(params)}"


def fetch_geojson(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def load_geojson(path_or_url: str | None = None) -> dict[str, Any]:
    if path_or_url and path_or_url.startswith(("http://", "https://")):
        return fetch_geojson(path_or_url)
    if path_or_url:
        return json.loads(Path(path_or_url).read_text(encoding="utf-8"))
    return fetch_geojson(build_statcan_ct_query_url())


def update_seed_file(
    seed_path: Path,
    source: str | None = None,
    *,
    replace_metrics_with_estimates: bool = False,
) -> int:
    """Refresh tract boundaries without silently replacing official metrics."""
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    tract_payload = load_geojson(source)
    tract_rows = build_tract_rows(seed["geographies"], tract_payload.get("features", []))

    existing_tracts = {
        item["geoid"]: item
        for item in seed["geographies"]
        if item.get("type") == "census_tract"
    }
    if not replace_metrics_with_estimates:
        refreshed_geoids = {item["geoid"] for item in tract_rows}
        missing_metrics = refreshed_geoids - set(existing_tracts)
        missing_boundaries = set(existing_tracts) - refreshed_geoids
        if missing_metrics or missing_boundaries:
            raise ValueError(
                "Tract boundary identifiers do not match the packaged metric rows "
                f"(new={len(missing_metrics)}, missing={len(missing_boundaries)}). "
                "Refresh official tract Census metrics before publishing the seed, or "
                "pass --replace-metrics-with-estimates explicitly for demo-only data."
            )

        preserved_rows = []
        geography_fields = (
            "name", "type", "county", "state", "geometry", "bbox", "geometry_source"
        )
        for refreshed in tract_rows:
            preserved = dict(existing_tracts[refreshed["geoid"]])
            for field in geography_fields:
                preserved[field] = refreshed[field]
            preserved_rows.append(preserved)
        tract_rows = preserved_rows

    seed["geographies"] = [
        item for item in seed["geographies"] if item.get("type") != "census_tract"
    ] + tract_rows
    seed["metadata"]["tract_geometry_source"] = GEOMETRY_SOURCE
    seed["metadata"]["tract_geometry_refreshed_at"] = datetime.now(UTC).isoformat()
    if replace_metrics_with_estimates:
        seed["metadata"]["source"] = "statistics_canada_2021_census_profile_csd_and_estimated_ct_seed"
        seed["metadata"]["notes"] = [
            "Municipal geometries and metrics use official Statistics Canada 2021 sources.",
            "Census tract geometries use official 2021 cartographic boundaries.",
            "Census tract metrics are demo-only estimates derived from parent municipalities.",
        ]

    temporary_path = seed_path.with_suffix(f"{seed_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(seed, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(seed_path)
    return len(tract_rows)


def build_tract_rows(parent_geographies: list[dict[str, Any]], tract_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parents = [
        {
            "geoid": item["geoid"],
            "name": item["name"],
            "county": item.get("county"),
            "geometry": item["geometry"],
            "metrics": item["metrics"][0],
        }
        for item in parent_geographies
        if item.get("type") == "municipality" and item.get("metrics")
    ]
    assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for feature in tract_features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        point = representative_point(geometry)
        parent = next((item for item in parents if point_in_geometry(point, item["geometry"])), None)
        if parent is None:
            continue
        assignments[parent["geoid"]].append(feature)

    tract_rows: list[dict[str, Any]] = []
    for parent in parents:
        features = sorted(
            assignments[parent["geoid"]],
            key=lambda feature: str(feature.get("properties", {}).get("CTUID", "")),
        )
        tract_rows.extend(build_parent_tract_rows(parent, features))

    return sorted(tract_rows, key=lambda item: item["geoid"])


def build_parent_tract_rows(parent: dict[str, Any], features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not features:
        return []

    metrics = parent["metrics"]
    population_values = allocate_total(metrics.get("population"), features, "population")
    previous_population_values = allocate_total(metrics.get("previous_population"), features, "previous")
    renter_values = allocate_total(metrics.get("renter_households"), features, "renters")
    rows: list[dict[str, Any]] = []

    for index, feature in enumerate(features):
        properties = feature.get("properties", {})
        ctuid = str(properties.get("CTUID") or properties.get("ctuid"))
        ctname = str(properties.get("CTNAME") or ctuid)
        income = scaled_metric(metrics.get("median_income"), ctuid, "income", spread=0.18, round_to=100)
        rent = scaled_metric(metrics.get("median_rent"), ctuid, "rent", spread=0.13, round_to=10)
        burden = shifted_metric(metrics.get("rent_burden_pct"), ctuid, "burden", spread=7.5, low=18.0, high=62.0)
        geometry = compact_geometry(feature["geometry"], precision=5)

        rows.append(
            {
                "geoid": ctuid,
                "name": f"{parent['name']} census tract {ctname}",
                "type": "census_tract",
                "county": parent["name"],
                "state": "ON",
                "geometry": geometry,
                "bbox": geometry_bbox(geometry),
                "geometry_source": GEOMETRY_SOURCE,
                "metrics": [
                    {
                        "year": metrics.get("year", 2021),
                        "median_income": income,
                        "median_rent": rent,
                        "population": population_values[index],
                        "previous_population": previous_population_values[index],
                        "renter_households": renter_values[index],
                        "rent_burden_pct": burden,
                    }
                ],
            }
        )

    return rows


def allocate_total(total: int | float | None, features: list[dict[str, Any]], salt: str) -> list[int | None]:
    if total is None:
        return [None for _ in features]
    weights = [1 + stable_variation(str(feature["properties"]["CTUID"]), salt, 0.55) for feature in features]
    weight_total = sum(weights)
    raw_values = [int(total * weight / weight_total) for weight in weights]
    remainder = int(total) - sum(raw_values)
    for index in range(abs(remainder)):
        target = index % len(raw_values)
        raw_values[target] += 1 if remainder > 0 else -1
    return [max(0, value) for value in raw_values]


def scaled_metric(
    value: float | int | None,
    geoid: str,
    salt: str,
    *,
    spread: float,
    round_to: int,
) -> float | None:
    if value is None:
        return None
    scaled = float(value) * (1 + stable_variation(geoid, salt, spread))
    return round(scaled / round_to) * round_to


def shifted_metric(
    value: float | int | None,
    geoid: str,
    salt: str,
    *,
    spread: float,
    low: float,
    high: float,
) -> float | None:
    if value is None:
        return None
    shifted = float(value) + stable_variation(geoid, salt, spread)
    return round(min(max(shifted, low), high), 1)


def stable_variation(geoid: str, salt: str, spread: float) -> float:
    digest = hashlib.sha1(f"{geoid}:{salt}".encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return (value * 2 - 1) * spread


def representative_point(geometry: dict[str, Any]) -> tuple[float, float]:
    rings = exterior_rings(geometry)
    if not rings:
        bbox = geometry_bbox(geometry)
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    ring = max(rings, key=abs_polygon_area)
    return polygon_centroid(ring)


def exterior_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return [coordinates[0]] if coordinates else []
    if geometry_type == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    return []


def polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for current, next_point in zip(ring, ring[1:], strict=False):
        cross = current[0] * next_point[1] - next_point[0] * current[1]
        area += cross
        centroid_x += (current[0] + next_point[0]) * cross
        centroid_y += (current[1] + next_point[1]) * cross
    if abs(area) < 1e-12:
        bbox = geometry_bbox({"type": "Polygon", "coordinates": [ring]})
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    area *= 0.5
    return (centroid_x / (6 * area), centroid_y / (6 * area))


def abs_polygon_area(ring: list[list[float]]) -> float:
    return abs(
        sum(
            current[0] * next_point[1] - next_point[0] * current[1]
            for current, next_point in zip(ring, ring[1:], strict=False)
        )
        / 2
    )


def point_in_geometry(point: tuple[float, float], geometry: dict[str, Any]) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return point_in_polygon(point, coordinates)
    if geometry_type == "MultiPolygon":
        return any(point_in_polygon(point, polygon) for polygon in coordinates)
    return False


def point_in_polygon(point: tuple[float, float], rings: list[list[list[float]]]) -> bool:
    if not rings or not point_in_ring(point, rings[0]):
        return False
    return not any(point_in_ring(point, ring) for ring in rings[1:])


def point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for start, end in zip(ring, ring[1:], strict=False):
        x1, y1 = start
        x2, y2 = end
        intersects = (y1 > y) != (y2 > y) and x < ((x2 - x1) * (y - y1) / (y2 - y1) + x1)
        if intersects:
            inside = not inside
    return inside


def upsert_tracts(db, tract_rows: list[dict[str, Any]]) -> int:
    from app.models import Geography, Metric
    from app.services.metric_calculations import calculate_affordability_index

    count = 0
    for item in tract_rows:
        metric_item = item["metrics"][0]
        geography_values = {key: value for key, value in item.items() if key != "metrics"}
        geography = db.query(Geography).filter(Geography.geoid == item["geoid"]).one_or_none()
        if geography is None:
            geography = Geography(**geography_values)
            db.add(geography)
        else:
            for key, value in geography_values.items():
                setattr(geography, key, value)

        metric = (
            db.query(Metric)
            .filter(Metric.geoid == item["geoid"], Metric.year == metric_item["year"])
            .one_or_none()
        )
        median_rent = metric_item.get("median_rent")
        median_income = metric_item.get("median_income")
        values = {
            "geoid": item["geoid"],
            "year": metric_item["year"],
            "median_income": median_income,
            "median_rent": median_rent,
            "population": metric_item.get("population"),
            "previous_population": metric_item.get("previous_population"),
            "renter_households": metric_item.get("renter_households"),
            # Passed through verbatim from the caller. The seed path provides
            # official values (null when suppressed). The legacy geometry-refresh
            # path (build_parent_tract_rows) provides disclosed placeholder
            # estimates that are meant to be overwritten by official values from
            # load_tract_census.py; its geometry_source states the metrics are
            # estimated. No estimation is introduced here.
            "rent_burden_pct": metric_item.get("rent_burden_pct"),
            "affordability_index": calculate_affordability_index(median_rent, median_income),
        }
        if metric is None:
            db.add(Metric(**values))
        else:
            for key, value in values.items():
                setattr(metric, key, value)
        count += 1
    return count


def upsert_tract_geometries(db, tract_rows: list[dict[str, Any]]) -> int:
    """Update boundary fields for existing tracts while preserving metric rows."""
    from app.models import Geography

    existing = {
        row.geoid: row
        for row in db.query(Geography).filter(Geography.type == "census_tract").all()
    }
    incoming_geoids = [item["geoid"] for item in tract_rows]
    incoming = set(incoming_geoids)
    new_geoids = incoming - set(existing)
    missing_boundaries = set(existing) - incoming
    duplicate_count = len(incoming_geoids) - len(incoming)
    if new_geoids or missing_boundaries or duplicate_count:
        raise ValueError(
            "Boundary refresh identifiers do not match existing tract metrics "
            f"(new={len(new_geoids)}, missing={len(missing_boundaries)}, "
            f"duplicates={duplicate_count}). Load official tract metrics first or "
            "explicitly replace metrics with estimates."
        )

    fields = ("name", "type", "county", "state", "geometry", "bbox", "geometry_source")
    for item in tract_rows:
        geography = existing[item["geoid"]]
        for field in fields:
            setattr(geography, field, item[field])
    return len(tract_rows)


def load_tracts(
    source: str | None = None, *, replace_metrics_with_estimates: bool = False
) -> int:
    from app.db.init_db import init_db
    from app.db.session import SessionLocal
    from app.models import ETLRun, Geography
    from app.services.postgis import sync_geography_geoms

    started_at = datetime.now(UTC)
    init_db()
    db = SessionLocal()
    try:
        parent_rows = [
            {
                "geoid": geography.geoid,
                "name": geography.name,
                "county": geography.county,
                "type": geography.type,
                "geometry": geography.geometry,
                "metrics": [
                    {
                        "year": metric.year,
                        "median_income": metric.median_income,
                        "median_rent": metric.median_rent,
                        "population": metric.population,
                        "previous_population": metric.previous_population,
                        "renter_households": metric.renter_households,
                        "rent_burden_pct": metric.rent_burden_pct,
                    }
                    for metric in geography.metrics
                ],
            }
            for geography in db.query(Geography).filter(Geography.type == "municipality").all()
        ]
        tract_rows = build_tract_rows(parent_rows, load_geojson(source).get("features", []))
        row_count = (
            upsert_tracts(db, tract_rows)
            if replace_metrics_with_estimates
            else upsert_tract_geometries(db, tract_rows)
        )
        db.flush()
        sync_geography_geoms(db)
        db.add(
            ETLRun(
                source=(
                    "statistics_canada_2021_ct_boundaries_estimated_metrics"
                    if replace_metrics_with_estimates
                    else "statistics_canada_2021_ct_boundaries_geometry_only"
                ),
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
                source=(
                    "statistics_canada_2021_ct_boundaries_estimated_metrics"
                    if replace_metrics_with_estimates
                    else "statistics_canada_2021_ct_boundaries_geometry_only"
                ),
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


def load_tracts_from_seed(seed_path: Path | None = None) -> int:
    from app.db.init_db import init_db
    from app.db.session import SessionLocal
    from app.models import ETLRun
    from app.services.postgis import sync_geography_geoms

    started_at = datetime.now(UTC)
    seed = json.loads((seed_path or PROJECT_ROOT / "app" / "data" / "demo_seed.json").read_text(encoding="utf-8"))
    tract_rows = [item for item in seed["geographies"] if item.get("type") == "census_tract"]
    init_db()
    db = SessionLocal()
    try:
        row_count = upsert_tracts(db, tract_rows)
        db.flush()
        sync_geography_geoms(db)
        db.add(
            ETLRun(
                source="packaged_seed_census_tracts_estimated_metrics",
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
                source="packaged_seed_census_tracts_estimated_metrics",
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
    parser = argparse.ArgumentParser(description="Refresh GTA census tract boundaries safely.")
    parser.add_argument("--print-url", action="store_true", help="Print the Statistics Canada CT query URL and exit.")
    parser.add_argument("--geojson", help="Path or URL to a Statistics Canada CT GeoJSON response.")
    parser.add_argument("--update-seed", action="store_true", help="Refresh packaged demo seed tract rows.")
    parser.add_argument("--from-seed", action="store_true", help="Load packaged seed tract rows into the database.")
    parser.add_argument(
        "--replace-metrics-with-estimates",
        action="store_true",
        help="Demo-only: replace tract metrics with parent-municipality estimates.",
    )
    args = parser.parse_args()

    if args.print_url:
        print(build_statcan_ct_query_url())
        return

    if args.update_seed:
        row_count = update_seed_file(
            PROJECT_ROOT / "app" / "data" / "demo_seed.json",
            args.geojson,
            replace_metrics_with_estimates=args.replace_metrics_with_estimates,
        )
        print(f"Updated {row_count} packaged seed census tract rows.")
        return

    if args.from_seed:
        row_count = load_tracts_from_seed()
        print(f"Loaded {row_count} packaged seed census tract rows.")
        return

    row_count = load_tracts(
        args.geojson,
        replace_metrics_with_estimates=args.replace_metrics_with_estimates,
    )
    print(f"Loaded {row_count} census tract rows.")


if __name__ == "__main__":
    main()
