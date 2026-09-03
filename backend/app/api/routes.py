from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, load_only

from app.db.session import get_db
from app.models import CmhcMetric, CmhcTractMetric, Geography, Metric
from app.schemas.responses import GeographiesListResponse, GeographyResponse
from app.services.cmhc_allocations import (
    CMHC_COUNT_METRICS,
    CMHC_REAL_TRACT_METRICS,
    build_tract_count_allocations,
)
from app.services.geojson import compact_geometry
from app.services.metric_calculations import (
    CMHC_METRICS,
    TRANSIT_METRICS,
    VALID_METRICS,
    build_metric_quality,
    is_cmhc_metric,
    is_low_denominator_growth,
    metric_value,
    normalize_metric_name,
    resolve_rent_burden,
)
from app.services.postgis import load_postgis_map_geometries
from app.services.summary import build_summary
from app.services.transit_provenance import (
    load_transit_manifest,
    load_transit_routes,
    transit_data_quality,
    transit_data_source,
)

router = APIRouter(prefix="/api", tags=["civic data"])

DEFAULT_GEOGRAPHY_TYPE = "municipality"
SUPPORTED_GEOGRAPHY_TYPES = {"municipality", "census_tract"}

@router.get("/transit-routes")
def get_transit_routes() -> JSONResponse:
    payload = dict(load_transit_routes())
    payload["metadata"] = load_transit_manifest()
    return JSONResponse(payload)

# CMHC reports some GTA municipalities together as one combined survey zone, so
# those municipalities share identical rental values. This map lets the UI
# disclose the shared zone instead of looking like duplicated data.
CMHC_RMS_SHARED_ZONES = {
    "3519038": "Richmond Hill / Vaughan / King",
    "3519028": "Richmond Hill / Vaughan / King",
    "3519049": "Richmond Hill / Vaughan / King",
    "3519046": "Aurora / Newmarket / Whitchurch-Stouffville",
    "3519048": "Aurora / Newmarket / Whitchurch-Stouffville",
    "3519044": "Aurora / Newmarket / Whitchurch-Stouffville",
    "3518001": "Pickering / Ajax / Uxbridge",
    "3518005": "Pickering / Ajax / Uxbridge",
    "3518029": "Pickering / Ajax / Uxbridge",
    "3524009": "Milton / Halton Hills",
    "3524015": "Milton / Halton Hills",
}

# CMHC survey-zone crosswalk: maps each census-tract geoid to its CMHC survey
# zone. Built from CMHC's official HMIP_CURRENT_CAWD FeatureServer.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CMHC_ZONE_RATE_METRICS = frozenset({"vacancy_rate", "average_rent_total"})


def _load_tract_zone_crosswalk() -> dict[str, str]:
    path = _DATA_DIR / "cmhc_tract_zone_crosswalk.csv"
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            result[row["geoid"]] = row["zone_name"]
    return result


def _load_zone_rms() -> dict[str, dict[str, float | None]]:
    path = _DATA_DIR / "cmhc_zone_rms.csv"
    if not path.exists():
        return {}
    result: dict[str, dict[str, float | None]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            def _float(s: str) -> float | None:
                try:
                    return float(s) if s else None
                except ValueError:
                    return None
            result[row["zone_name"]] = {
                "vacancy_rate": _float(row["vacancy_rate"]),
                "average_rent_total": _float(row["average_rent_total"]),
                "rental_universe": _float(row["rental_universe"]),
            }
    return result


TRACT_ZONE_CROSSWALK: dict[str, str] = _load_tract_zone_crosswalk()
ZONE_RMS: dict[str, dict[str, float | None]] = _load_zone_rms()


def load_real_tract_cmhc(db: Session, year: int) -> dict[str, CmhcTractMetric]:
    """Map tract geoid -> real CMHC SCSS row for a given year (may be empty)."""
    return {
        row.geoid: row
        for row in db.query(CmhcTractMetric).filter(CmhcTractMetric.year == year).all()
    }


def real_tract_count(
    real_row: CmhcTractMetric | None, metric_key: str
) -> int | None:
    if real_row is None or metric_key not in CMHC_REAL_TRACT_METRICS:
        return None
    return getattr(real_row, metric_key, None)


def resolve_year(db: Session, year: int | None) -> int:
    if year is not None:
        return year
    latest_year = db.query(func.max(Metric.year)).scalar()
    if latest_year is None:
        raise HTTPException(status_code=404, detail="No metrics have been loaded.")
    return int(latest_year)


MAX_IDS = 500


def parse_ids(ids: str | None) -> list[str]:
    if not ids:
        return []
    items = list(dict.fromkeys(item.strip() for item in ids.split(",") if item.strip()))
    if len(items) > MAX_IDS:
        raise HTTPException(status_code=400, detail=f"Too many IDs (max {MAX_IDS}).")
    return items


def normalize_geography_type(geography_type: str | None) -> str | None:
    if geography_type is None:
        return None
    normalized = geography_type.strip().lower()
    if normalized not in SUPPORTED_GEOGRAPHY_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported geography type: {geography_type}")
    return normalized


def serialize_metric(metric: Metric) -> dict[str, Any]:
    rent_burden_value, _ = resolve_rent_burden(
        metric.median_rent, metric.median_income, metric.rent_burden_pct
    )
    return {
        "year": metric.year,
        "median_income": metric.median_income,
        "median_rent": metric.median_rent,
        "population": metric.population,
        "previous_population": metric.previous_population,
        "population_growth_pct": metric_value("population_growth_pct", metric),
        "renter_households": metric.renter_households,
        # Effective value: official when published, otherwise a labeled estimate.
        # Provenance is exposed per-field in ``data_quality`` below.
        "rent_burden_pct": rent_burden_value,
        "rent_to_income_ratio": metric_value("rent_to_income_ratio", metric),
        "affordability_index": metric.affordability_index,
        "dwellings_total": metric.dwellings_total,
        "dwellings_single_detached": metric.dwellings_single_detached,
        "dwellings_semi_detached": metric.dwellings_semi_detached,
        "dwellings_row_house": metric.dwellings_row_house,
        "dwellings_apt_duplex": metric.dwellings_apt_duplex,
        "dwellings_apt_low_rise": metric.dwellings_apt_low_rise,
        "dwellings_apt_high_rise": metric.dwellings_apt_high_rise,
        "owner_households": metric.owner_households,
        "transit_route_count": metric.transit_route_count,
        "transit_score": metric.transit_score,
        "data_quality": build_metric_quality(metric),
    }


def serialize_geography(
    geography: Geography,
    metric: Metric | None = None,
    *,
    include_geometry: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": geography.id,
        "geoid": geography.geoid,
        "name": geography.name,
        "type": geography.type,
        "county": geography.county,
        "state": geography.state,
        "bbox": geography.bbox,
        "geometry_source": geography.geometry_source,
    }
    if include_geometry:
        payload["geometry"] = geography.geometry
    if metric is not None:
        payload["metrics"] = serialize_metric(metric)
    return payload


def resolve_cmhc_year(db: Session, year: int | None) -> int:
    if year is not None:
        return year
    latest_year = db.query(func.max(CmhcMetric.year)).scalar()
    if latest_year is None:
        raise HTTPException(status_code=404, detail="No CMHC metrics have been loaded.")
    return int(latest_year)


def available_cmhc_years(db: Session) -> list[int]:
    """Return all distinct CMHC years.

    CMHC data is stored at municipality level only; census tracts inherit
    from their parent municipality, so the available years are the same
    regardless of the requested geography type.
    """
    query = db.query(CmhcMetric.year).distinct()
    years = sorted(row[0] for row in query.all())
    return years


def serialize_cmhc_metric(
    cmhc: CmhcMetric,
    *,
    tract_inherited: bool = False,
    allocated_counts: Mapping[str, int | None] | None = None,
    real_tract: "CmhcTractMetric | None" = None,
    zone_name: str | None = None,
) -> dict[str, Any]:
    """Serialize a CmhcMetric row to a dict.

    When ``tract_inherited`` is True the row is a municipality-level record
    being attached to a census tract. ``allocated_counts`` contains the
    conservative largest-remainder allocation computed for all sibling tracts.

    When ``zone_name`` is provided, rate metrics (vacancy, average rent) are
    overridden with the tract's CMHC survey-zone value instead of inheriting
    the flat municipal average.

    When ``real_tract`` is provided (a real CMHC census-tract SCSS row), its
    starts/completions REPLACE the allocation for those fields and are flagged
    ``official`` via the ``*_source`` keys; other count fields stay estimated.
    """

    def _alloc(metric_key: str, val: int | None) -> int | None:
        if not tract_inherited or val is None:
            return val
        if allocated_counts is None:
            return None
        return allocated_counts.get(metric_key)

    allocated = tract_inherited and allocated_counts is not None

    def _count_with_source(metric_key: str, allocated_val: int | None) -> tuple[int | None, str]:
        if real_tract is not None:
            real = getattr(real_tract, metric_key, None)
            if real is not None:
                stored = getattr(real_tract, f"{metric_key}_source", None) or "official"
                return real, stored
        if not tract_inherited:
            return allocated_val, "official"
        return allocated_val, "estimated"

    starts, starts_source = _count_with_source(
        "housing_starts_total", _alloc("housing_starts_total", cmhc.housing_starts_total)
    )
    completions, completions_source = _count_with_source(
        "housing_completions", _alloc("housing_completions", cmhc.housing_completions)
    )

    zone_data = ZONE_RMS.get(zone_name) if zone_name else None
    vacancy = zone_data["vacancy_rate"] if zone_data and zone_data["vacancy_rate"] is not None else cmhc.vacancy_rate
    avg_rent = zone_data["average_rent_total"] if zone_data and zone_data["average_rent_total"] is not None else cmhc.average_rent_total
    shared_municipal_zone = CMHC_RMS_SHARED_ZONES.get(cmhc.geoid)

    def _rms_source(zone_value_available: bool) -> str:
        if tract_inherited:
            return "survey_zone" if zone_value_available else "inherited_municipality"
        return "survey_zone" if shared_municipal_zone else "municipality"

    result: dict[str, Any] = {
        "year": cmhc.year,
        "vacancy_rate": vacancy,
        "average_rent_total": avg_rent,
        "average_rent_bachelor": cmhc.average_rent_bachelor,
        "average_rent_1br": cmhc.average_rent_1br,
        "average_rent_2br": cmhc.average_rent_2br,
        "average_rent_3br_plus": cmhc.average_rent_3br_plus,
        "turnover_rate": cmhc.turnover_rate,
        "availability_rate": cmhc.availability_rate,
        "rental_universe": _alloc("rental_universe", cmhc.rental_universe),
        "housing_starts_total": starts,
        "housing_starts_single": _alloc("housing_starts_single", cmhc.housing_starts_single),
        "housing_starts_semi": _alloc("housing_starts_semi", cmhc.housing_starts_semi),
        "housing_starts_row": _alloc("housing_starts_row", cmhc.housing_starts_row),
        "housing_starts_apartment": _alloc(
            "housing_starts_apartment", cmhc.housing_starts_apartment
        ),
        "housing_completions": completions,
        "units_under_construction": _alloc(
            "units_under_construction", cmhc.units_under_construction
        ),
        "unabsorbed_units": _alloc("unabsorbed_units", cmhc.unabsorbed_units),
        "rms_surveyed": cmhc.rms_surveyed,
        "allocated": allocated,
        "starts_source": starts_source,
        "completions_source": completions_source,
        "survey_zone": zone_name or CMHC_RMS_SHARED_ZONES.get(cmhc.geoid),
        "vacancy_rate_source": _rms_source(
            bool(zone_data and zone_data["vacancy_rate"] is not None)
        ),
        "average_rent_total_source": _rms_source(
            bool(zone_data and zone_data["average_rent_total"] is not None)
        ),
        "other_rms_source": _rms_source(False),
    }
    return result


def joined_records(
    db: Session,
    year: int,
    ids: list[str] | None = None,
    geography_type: str | None = None,
    include_geometry: bool = True,
):
    query = (
        db.query(Geography, Metric)
        .join(Metric, Geography.geoid == Metric.geoid)
        .filter(Metric.year == year)
    )
    if not include_geometry:
        query = query.options(
            load_only(
                Geography.id,
                Geography.geoid,
                Geography.name,
                Geography.type,
                Geography.county,
                Geography.state,
                Geography.bbox,
                Geography.geometry_source,
            )
        )
    if geography_type:
        query = query.filter(Geography.type == geography_type)
    if ids:
        query = query.filter(Geography.geoid.in_(ids))
    return query.all()


@router.get("/geographies", response_model=GeographiesListResponse)
def list_geographies(
    search: str | None = Query(default=None, min_length=1),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    metric_year = resolve_year(db, year)
    normalized_type = normalize_geography_type(geography_type)
    query = db.query(Geography)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Geography.name.ilike(like),
                Geography.county.ilike(like),
                Geography.geoid.ilike(like),
            )
        )
    if normalized_type:
        query = query.filter(Geography.type == normalized_type)

    query = query.options(
        load_only(
            Geography.id,
            Geography.geoid,
            Geography.name,
            Geography.type,
            Geography.county,
            Geography.state,
            Geography.bbox,
            Geography.geometry_source,
        )
    )
    geographies = query.order_by(Geography.name).limit(limit).all()
    geoid_set = [g.geoid for g in geographies]
    metrics = {
        m.geoid: m
        for m in db.query(Metric)
        .filter(Metric.year == metric_year, Metric.geoid.in_(geoid_set))
        .all()
    } if geoid_set else {}
    return {
        "year": metric_year,
        "items": [
            serialize_geography(
                geography,
                metrics.get(geography.geoid),
                include_geometry=False,
            )
            for geography in geographies
        ],
    }


@router.get("/geographies/{geography_id}", response_model=GeographyResponse)
def get_geography(
    geography_id: str,
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    metric_year = resolve_year(db, year)
    geography = db.query(Geography).filter(Geography.geoid == geography_id).first()
    if geography_id.isdigit():
        geography = geography or db.query(Geography).filter(Geography.id == int(geography_id)).first()
    if geography is None:
        raise HTTPException(status_code=404, detail="Geography not found.")
    metric = (
        db.query(Metric)
        .filter(Metric.geoid == geography.geoid, Metric.year == metric_year)
        .first()
    )
    return serialize_geography(geography, metric)


@router.get("/metrics")
def list_metric_values(
    metric: str = Query(default="rent_burden_pct"),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    metric_key = normalize_metric_name(metric)
    if metric_key not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")
    if is_cmhc_metric(metric_key):
        raise HTTPException(
            status_code=400,
            detail=f"CMHC metric '{metric_key}' is not available on this endpoint. Use /api/map-data instead.",
        )
    normalized_type = normalize_geography_type(geography_type)
    metric_year = resolve_year(db, year)
    records = joined_records(db, metric_year, geography_type=normalized_type, include_geometry=False)
    return {
        "metric": metric_key,
        "year": metric_year,
        "items": [
            {
                "geoid": geography.geoid,
                "name": geography.name,
                "type": geography.type,
                "county": geography.county,
                "value": metric_value(metric_key, row),
            }
            for geography, row in records
        ],
    }


@router.get("/summary")
def get_summary(
    ids: str | None = Query(default=None, description="Comma-separated GEOIDs."),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    # Census data year is always latest (2021); the year param only affects CMHC.
    metric_year = resolve_year(db, None)
    id_list = parse_ids(ids)
    normalized_type = normalize_geography_type(geography_type)
    records = joined_records(db, metric_year, id_list, normalized_type, include_geometry=False)
    if id_list and not records:
        raise HTTPException(status_code=404, detail="No selected geographies were found.")

    cmhc_year = resolve_cmhc_year(db, year)
    # CMHC data is stored at municipality level only.  For census tract mode
    # we aggregate the municipality-level rows so the summary still reports
    # meaningful GTA-wide CMHC stats.
    cmhc_query = db.query(CmhcMetric).filter(CmhcMetric.year == cmhc_year)
    cmhc_query = cmhc_query.join(Geography, Geography.geoid == CmhcMetric.geoid).filter(
        Geography.type == "municipality"
    )
    if id_list and normalized_type == "census_tract":
        # Resolve selected tracts' parent municipalities via the county name.
        parent_names = [
            name
            for (name,) in db.query(Geography.county)
            .filter(Geography.geoid.in_(id_list), Geography.county.isnot(None))
            .distinct()
            .all()
        ]
        parent_geoids = (
            [
                geoid
                for (geoid,) in db.query(Geography.geoid)
                .filter(Geography.type == "municipality", Geography.name.in_(parent_names))
                .all()
            ]
            if parent_names
            else []
        )
        # Always scope to the resolved parents. If none resolve, scope to an
        # empty set so the summary reports no CMHC aggregate rather than silently
        # falling back to ALL-municipality (GTA-wide) data attributed to one tract.
        cmhc_query = cmhc_query.filter(CmhcMetric.geoid.in_(parent_geoids))
    elif id_list:
        cmhc_query = cmhc_query.filter(CmhcMetric.geoid.in_(id_list))
    cmhc_records = cmhc_query.all()

    return build_summary(records, metric_year, cmhc_records=cmhc_records)


@router.get("/compare")
def compare_geographies(
    ids: str | None = Query(default=None, description="Comma-separated GEOIDs."),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    # Census data year is always latest (2021); the year param only affects CMHC.
    metric_year = resolve_year(db, None)
    id_list = parse_ids(ids)
    normalized_type = normalize_geography_type(geography_type)
    records = joined_records(db, metric_year, id_list, normalized_type, include_geometry=False)

    if id_list:
        record_by_geoid = {geography.geoid: (geography, metric) for geography, metric in records}
        ordered_records = [record_by_geoid[geoid] for geoid in id_list if geoid in record_by_geoid]
    else:
        ordered_records = sorted(records, key=lambda item: item[1].population or 0, reverse=True)[:6]

    cmhc_year = resolve_cmhc_year(db, year)
    cmhc_by_geoid = {
        row.geoid: row
        for row in db.query(CmhcMetric).filter(CmhcMetric.year == cmhc_year).all()
    }
    # Build name-to-geoid lookup for census tract CMHC inheritance.
    municipality_name_to_geoid: dict[str, str] = {}
    tract_count_allocations: dict[str, dict[str, int | None]] = {}
    real_tract_cmhc: dict[str, CmhcTractMetric] = {}
    if normalized_type == "census_tract":
        municipality_name_to_geoid = {
            name: geoid
            for geoid, name in db.query(Geography.geoid, Geography.name)
            .filter(Geography.type == "municipality")
            .all()
        }
        # Shares must be computed over ALL tracts (the full municipal renter
        # denominator), not just the selected `records` -- otherwise a single
        # selected tract gets share == 1.0 and is handed the whole municipal
        # total instead of its proportional allocation.
        all_tract_records = joined_records(
            db, metric_year, geography_type="census_tract", include_geometry=False
        )
        # Real published CMHC tract values for this year (same as the map uses)
        # so compare and map agree per tract instead of diverging.
        real_tract_cmhc = load_real_tract_cmhc(db, cmhc_year)
        tract_count_allocations = build_tract_count_allocations(
            all_tract_records,
            municipality_name_to_geoid,
            cmhc_by_geoid,
            real_tract_cmhc,
        )

    items = []
    for geography, metric in ordered_records:
        item: dict[str, Any] = {
            "geoid": geography.geoid,
            "name": geography.name,
            "type": geography.type,
            "county": geography.county,
            "metrics": serialize_metric(metric),
        }
        # Census tracts inherit CMHC data from parent municipality
        if normalized_type == "census_tract" and geography.county:
            parent_geoid = municipality_name_to_geoid.get(geography.county)
            cmhc_row = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
            is_tract_inherited = cmhc_row is not None
        else:
            cmhc_row = cmhc_by_geoid.get(geography.geoid)
            is_tract_inherited = False
        allocated_counts = (
            tract_count_allocations.get(geography.geoid) if is_tract_inherited else None
        )
        zone = TRACT_ZONE_CROSSWALK.get(geography.geoid) if is_tract_inherited else None
        if cmhc_row:
            item["cmhc_metrics"] = serialize_cmhc_metric(
                cmhc_row,
                tract_inherited=is_tract_inherited,
                allocated_counts=allocated_counts,
                real_tract=real_tract_cmhc.get(geography.geoid),
                zone_name=zone,
            )
        else:
            item["cmhc_metrics"] = None
        items.append(item)

    result: dict[str, Any] = {
        "year": metric_year,
        "items": items,
    }
    if cmhc_by_geoid:
        result["cmhc_year"] = cmhc_year
    return result


@router.get("/map-data")
def get_map_data(
    metric: str = Query(default="rent_burden_pct"),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    detail: Literal["full", "display"] = Query(
        default="full",
        description="Use display for map-ready simplified geometry; full returns stored geometry.",
    ),
    year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    metric_key = normalize_metric_name(metric)
    if metric_key not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")
    normalized_type = normalize_geography_type(geography_type)
    cmhc = is_cmhc_metric(metric_key)

    # Census data is a single 2021 vintage, so the census metric join always
    # uses the latest census year regardless of the requested `year` (passing a
    # non-2021 year previously emptied the map). The `year` param applies only to
    # CMHC data, resolved separately via resolve_cmhc_year below.
    metric_year = resolve_year(db, None)
    postgis_geometries = (
        load_postgis_map_geometries(
            db,
            year=metric_year,
            detail=detail,
            geography_type=normalized_type,
        )
        if detail == "display"
        else {}
    )
    records = joined_records(
        db,
        metric_year,
        geography_type=normalized_type,
        include_geometry=not postgis_geometries,
    )

    # Always load CMHC data so the detail panel can display it regardless
    # of which metric the map is colored by.  When viewing a CMHC metric the
    # user-selected year is used; otherwise the latest available CMHC year.
    cmhc_year = resolve_cmhc_year(db, year if cmhc else None)
    cmhc_by_geoid: dict[str, CmhcMetric] = {
        row.geoid: row
        for row in db.query(CmhcMetric).filter(CmhcMetric.year == cmhc_year).all()
    }
    municipality_name_to_geoid: dict[str, str] = {}
    tract_count_allocations: dict[str, dict[str, int | None]] = {}
    real_tract_cmhc: dict[str, CmhcTractMetric] = {}
    if normalized_type == "census_tract":
        municipality_name_to_geoid = {
            name: geoid
            for geoid, name in db.query(Geography.geoid, Geography.name)
            .filter(Geography.type == "municipality")
            .all()
        }
        # Always load real tract values in CMHC tract mode (not just when the
        # mapped metric is starts/completions): the detail panel serializes the
        # full cmhc_metrics for every feature, so starts/completions must keep
        # their real "official" provenance regardless of which metric colours
        # the map.
        real_tract_cmhc = load_real_tract_cmhc(db, cmhc_year)
        tract_count_allocations = build_tract_count_allocations(
            records,
            municipality_name_to_geoid,
            cmhc_by_geoid,
            real_tract_cmhc,
        )

    if cmhc:
        if normalized_type == "census_tract" and metric_key in CMHC_COUNT_METRICS:
            values = []
            for geography, _ in records:
                allocated = tract_count_allocations.get(geography.geoid, {}).get(
                    metric_key
                )
                if allocated is not None:
                    values.append(allocated)
        elif normalized_type == "census_tract" and metric_key in CMHC_ZONE_RATE_METRICS:
            values = []
            for geography, _ in records:
                zone = TRACT_ZONE_CROSSWALK.get(geography.geoid)
                zd = ZONE_RMS.get(zone) if zone else None
                if zd and zd.get(metric_key) is not None:
                    values.append(zd[metric_key])
                elif geography.county:
                    parent_geoid = municipality_name_to_geoid.get(geography.county)
                    cr = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
                    if cr:
                        v = metric_value(metric_key, cr)
                        if v is not None:
                            values.append(v)
        else:
            values = [
                v
                for cmhc_row in cmhc_by_geoid.values()
                if (v := metric_value(metric_key, cmhc_row)) is not None
            ]
    elif metric_key == "population_growth_pct":
        # Exclude growth computed off a tiny 2016 base from the color scale:
        # a handful of near-empty tracts produce absurd percentages that would
        # otherwise flatten the gradient for every other tract. The real value
        # is still returned per-feature (and flagged low_confidence) for the
        # detail panel.
        values = [
            value
            for _, row in records
            if not is_low_denominator_growth(row.previous_population)
            and (value := metric_value(metric_key, row)) is not None
        ]
    else:
        values = [
            value
            for _, row in records
            if (value := metric_value(metric_key, row)) is not None
        ]
    domain = {
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }

    metadata: dict[str, Any] = {
        "metric": metric_key,
        "year": cmhc_year if cmhc else metric_year,
        "cmhc_year": cmhc_year,
        "domain": domain,
        "geography_type": normalized_type,
        "data_quality": data_quality(normalized_type, cmhc=cmhc, metric_key=metric_key),
        "source": map_data_source(normalized_type, cmhc=cmhc, metric_key=metric_key),
        "available_years": available_cmhc_years(db),
        "metric_catalog": {
            candidate: {
                "data_quality": data_quality(
                    normalized_type,
                    cmhc=is_cmhc_metric(candidate),
                    metric_key=candidate,
                ),
                "source": map_data_source(
                    normalized_type,
                    cmhc=is_cmhc_metric(candidate),
                    metric_key=candidate,
                ),
            }
            for candidate in sorted(VALID_METRICS)
        },
    }
    if is_transit_metric(metric_key):
        metadata["transit_snapshot"] = load_transit_manifest()

    features = []
    for geography, row in records:
        props: dict[str, Any] = {
            "id": geography.id,
            "geoid": geography.geoid,
            "name": geography.name,
            "type": geography.type,
            "county": geography.county,
            "state": geography.state,
            "bbox": geography.bbox,
            "geometry_source": geography.geometry_source,
            "metric": metric_key,
            "metrics": serialize_metric(row),
        }
        if normalized_type == "census_tract" and geography.county:
            parent_geoid = municipality_name_to_geoid.get(geography.county)
            cmhc_row = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
            is_tract_inherited = cmhc_row is not None
        else:
            cmhc_row = cmhc_by_geoid.get(geography.geoid)
            is_tract_inherited = False
        allocated_counts = (
            tract_count_allocations.get(geography.geoid) if is_tract_inherited else None
        )
        zone = TRACT_ZONE_CROSSWALK.get(geography.geoid) if is_tract_inherited else None
        real_row = real_tract_cmhc.get(geography.geoid)
        if cmhc:
            if is_tract_inherited and metric_key in CMHC_COUNT_METRICS:
                props["value"] = (
                    allocated_counts.get(metric_key) if allocated_counts is not None else None
                )
            elif is_tract_inherited and metric_key in CMHC_ZONE_RATE_METRICS:
                zd = ZONE_RMS.get(zone) if zone else None
                if zd and zd.get(metric_key) is not None:
                    props["value"] = zd[metric_key]
                else:
                    props["value"] = metric_value(metric_key, cmhc_row) if cmhc_row else None
            else:
                props["value"] = metric_value(metric_key, cmhc_row) if cmhc_row else None
        else:
            props["value"] = metric_value(metric_key, row)
        if cmhc_row:
            props["cmhc_metrics"] = serialize_cmhc_metric(
                cmhc_row,
                tract_inherited=is_tract_inherited,
                allocated_counts=allocated_counts,
                real_tract=real_row,
                zone_name=zone,
            )
        props["cmhc_year"] = cmhc_year
        geometry = postgis_geometries.get(geography.geoid)
        if geometry is None:
            geometry = map_geometry(geography.geometry, detail, normalized_type)

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": props,
            }
        )

    return {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": features,
    }


def map_geometry(geometry: dict[str, Any], detail: str, geography_type: str | None) -> dict[str, Any]:
    if detail == "display":
        tolerance = 0.00035 if geography_type == "census_tract" else 0.00008
        return compact_geometry(geometry, tolerance=tolerance, precision=5)
    return geometry


def is_transit_metric(metric_key: str) -> bool:
    return metric_key in TRANSIT_METRICS


def map_data_source(geography_type: str | None, cmhc: bool = False, metric_key: str | None = None) -> str:
    if metric_key and is_transit_metric(metric_key):
        return transit_data_source()
    if cmhc:
        return (
            "CMHC Rental Market Survey and Starts & Completions Survey data "
            "from the Housing Market Information Portal."
        )
    if geography_type == "census_tract":
        return (
            "Statistics Canada 2021 census tract cartographic boundaries filtered to the GTA; "
            "tract metrics are official 2021 Census Profile values fetched via the SDMX DF_CT dataflow."
        )
    return (
        "GTA municipal metrics from the loaded database; packaged seed metrics use "
        "Statistics Canada 2021 Census Profile values."
    )


def data_quality(
    geography_type: str | None,
    cmhc: bool = False,
    metric_key: str | None = None,
) -> dict[str, str]:
    if cmhc and geography_type == "census_tract":
        if metric_key is not None and metric_key in CMHC_REAL_TRACT_METRICS:
            return {
                "metric_status": "mixed",
                "label": "CMHC tract values (official + estimated)",
                "description": (
                    "Real CMHC census-tract values are shown where CMHC publishes them "
                    "(official); tracts outside CMHC's survey coverage fall back to the parent "
                    "municipality's total allocated by renter-household share (estimated)."
                ),
            }
        if metric_key is not None and metric_key in CMHC_COUNT_METRICS:
            return {
                "metric_status": "estimated",
                "label": "CMHC (estimated tract allocation)",
                "description": (
                    "CMHC does not publish this count at the census-tract level. The parent "
                    "municipality's total is allocated to each tract by its share of municipal "
                    "renter households, so values vary per tract."
                ),
            }
        if metric_key is not None and metric_key in CMHC_ZONE_RATE_METRICS and TRACT_ZONE_CROSSWALK:
            return {
                "metric_status": "mixed",
                "label": "CMHC survey-zone values + municipal fallback",
                "description": (
                    "Matched tracts show their CMHC survey zone's value. Tracts without a zone "
                    "crosswalk use the parent municipality's value and are identified per feature."
                ),
            }
        return {
            "metric_status": "estimated",
            "label": "CMHC municipal value (inherited)",
            "description": (
                "CMHC does not survey this rate at the census-tract level, so the parent "
                "municipality's value is shown for every tract within it. All tracts in the "
                "same municipality share the same value by design."
            ),
        }
    if cmhc:
        return {
            "metric_status": "official",
            "label": "CMHC Rental Market Survey",
            "description": (
                "CMHC Rental Market Survey data "
                "from the Housing Market Information Portal."
            ),
        }
    if metric_key is not None and metric_key in TRANSIT_METRICS:
        return transit_data_quality()
    if metric_key in {"affordability_index", "rent_to_income_ratio", "population_growth_pct"}:
        return {
            "metric_status": "derived",
            "label": "Derived from official Census values",
            "description": (
                "This indicator is calculated from published Statistics Canada 2021 "
                "Census Profile inputs; it is not a separately published Census measure."
            ),
        }
    if geography_type == "census_tract":
        if metric_key == "rent_burden_pct":
            return {
                "metric_status": "mixed",
                "label": "Official + estimated tract metrics",
                "description": (
                    "Census tract geometries and metrics are official Statistics Canada 2021 "
                    "Census Profile values (SDMX DF_CT). Where Statistics Canada suppressed the "
                    "rent-burden value it is estimated from median rent and income and clearly "
                    "labeled; tracts without enough data show \"Not available\"."
                ),
            }
        return {
            "metric_status": "official",
            "label": "Official tract metrics",
            "description": (
                "Census tract geometries and metrics are official Statistics Canada 2021 "
                "Census Profile values fetched via the SDMX DF_CT dataflow. Suppressed values "
                "show as \"Not available\"; growth computed off a very small base is flagged."
            ),
        }
    return {
        "metric_status": "official",
        "label": "Official municipal metrics",
        "description": "Packaged municipal metrics use official Statistics Canada 2021 Census Profile values.",
    }
