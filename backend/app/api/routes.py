from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, load_only

from app.db.session import get_db
from app.models import CmhcMetric, Geography, Metric
from app.schemas.responses import GeographiesListResponse, GeographyResponse
from app.services.geojson import compact_geometry
from app.services.metric_calculations import (
    CMHC_METRICS,
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

router = APIRouter(prefix="/api", tags=["civic data"])

DEFAULT_GEOGRAPHY_TYPE = "municipality"
SUPPORTED_GEOGRAPHY_TYPES = {"municipality", "census_tract"}

# Count-based CMHC metrics are municipality-level totals. In census tract views
# they are proportionally allocated by renter-household share and labeled as
# estimated; rate/average metrics such as vacancy and rents are inherited.
CMHC_COUNT_METRICS = frozenset({
    "rental_universe",
    "housing_starts_total",
    "housing_starts_single",
    "housing_starts_semi",
    "housing_starts_row",
    "housing_starts_apartment",
    "housing_completions",
    "units_under_construction",
    "unabsorbed_units",
})


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
    items = [item.strip() for item in ids.split(",") if item.strip()]
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
    tract_share: float | None = None,
) -> dict[str, Any]:
    """Serialize a CmhcMetric row to a dict.

    When ``tract_inherited`` is True the row is a municipality-level record
    being attached to a census tract.  If ``tract_share`` (0-1) is provided,
    count-based metrics are proportionally allocated to the tract based on its
    share of the municipality's renter households. Rate-based metrics
    (vacancy, rents, turnover, availability) are inherited unchanged.
    """

    def _alloc(val: int | None) -> int | None:
        if not tract_inherited or val is None:
            return val
        if tract_share is None:
            return None
        return round(val * tract_share)

    allocated = tract_inherited and tract_share is not None
    result: dict[str, Any] = {
        "year": cmhc.year,
        "vacancy_rate": cmhc.vacancy_rate,
        "average_rent_total": cmhc.average_rent_total,
        "average_rent_bachelor": cmhc.average_rent_bachelor,
        "average_rent_1br": cmhc.average_rent_1br,
        "average_rent_2br": cmhc.average_rent_2br,
        "average_rent_3br_plus": cmhc.average_rent_3br_plus,
        "turnover_rate": cmhc.turnover_rate,
        "availability_rate": cmhc.availability_rate,
        "rental_universe": _alloc(cmhc.rental_universe),
        "housing_starts_total": _alloc(cmhc.housing_starts_total),
        "housing_starts_single": _alloc(cmhc.housing_starts_single),
        "housing_starts_semi": _alloc(cmhc.housing_starts_semi),
        "housing_starts_row": _alloc(cmhc.housing_starts_row),
        "housing_starts_apartment": _alloc(cmhc.housing_starts_apartment),
        "housing_completions": _alloc(cmhc.housing_completions),
        "units_under_construction": _alloc(cmhc.units_under_construction),
        "unabsorbed_units": _alloc(cmhc.unabsorbed_units),
        "rms_surveyed": cmhc.rms_surveyed,
        "allocated": allocated,
    }
    return result


def _compute_tract_shares(records: list) -> dict[str, float]:
    """Compute each census tract's share of its municipality's renter households.

    Returns a dict mapping tract geoid to fraction (0-1) used to
    proportionally allocate municipal CMHC count metrics to tracts.
    """
    muni_renters: dict[str, int] = {}
    tract_renters: dict[str, int] = {}
    for geography, metric in records:
        if geography.county:
            r = metric.renter_households or 0
            muni_renters[geography.county] = muni_renters.get(geography.county, 0) + r
            tract_renters[geography.geoid] = r
    shares: dict[str, float] = {}
    for geography, _ in records:
        if geography.county:
            total = muni_renters.get(geography.county, 0)
            if total > 0:
                shares[geography.geoid] = tract_renters.get(geography.geoid, 0) / total
    return shares


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
    tract_shares: dict[str, float] = {}
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
        tract_shares = _compute_tract_shares(all_tract_records)

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
        share = tract_shares.get(geography.geoid) if is_tract_inherited else None
        if cmhc_row:
            item["cmhc_metrics"] = serialize_cmhc_metric(
                cmhc_row, tract_inherited=is_tract_inherited, tract_share=share,
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
    tract_shares: dict[str, float] = {}
    if normalized_type == "census_tract":
        municipality_name_to_geoid = {
            name: geoid
            for geoid, name in db.query(Geography.geoid, Geography.name)
            .filter(Geography.type == "municipality")
            .all()
        }
        tract_shares = _compute_tract_shares(records)

    if cmhc:
        if normalized_type == "census_tract" and metric_key in CMHC_COUNT_METRICS:
            # Estimate tract-level values via proportional allocation
            values = []
            for geography, _ in records:
                if not geography.county:
                    continue
                parent_geoid = municipality_name_to_geoid.get(geography.county)
                cr = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
                share = tract_shares.get(geography.geoid)
                if cr and share is not None:
                    raw = metric_value(metric_key, cr)
                    if raw is not None:
                        values.append(round(raw * share))
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
        "source": map_data_source(normalized_type, cmhc=cmhc),
        "available_years": available_cmhc_years(db),
    }

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
        # For census tracts, resolve CMHC row from parent municipality
        if normalized_type == "census_tract" and geography.county:
            parent_geoid = municipality_name_to_geoid.get(geography.county)
            cmhc_row = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
            is_tract_inherited = cmhc_row is not None
        else:
            cmhc_row = cmhc_by_geoid.get(geography.geoid)
            is_tract_inherited = False
        share = tract_shares.get(geography.geoid) if is_tract_inherited else None
        if cmhc:
            if is_tract_inherited and metric_key in CMHC_COUNT_METRICS:
                raw = metric_value(metric_key, cmhc_row) if cmhc_row else None
                props["value"] = round(raw * share) if raw is not None and share is not None else None
            else:
                props["value"] = metric_value(metric_key, cmhc_row) if cmhc_row else None
        else:
            props["value"] = metric_value(metric_key, row)
        if cmhc_row:
            props["cmhc_metrics"] = serialize_cmhc_metric(
                cmhc_row, tract_inherited=is_tract_inherited, tract_share=share,
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


def map_data_source(geography_type: str | None, cmhc: bool = False) -> str:
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
        # Rate / average metrics (vacancy, rents, turnover, availability) are
        # inherited UNCHANGED from the parent municipality — not allocated — so
        # every tract in a municipality shows the same value by design.
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
