from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, load_only

from app.db.session import get_db
from app.models import CmhcMetric, Geography, Metric
from app.services.geojson import compact_geometry
from app.services.metric_calculations import (
    CMHC_METRICS,
    VALID_METRICS,
    is_cmhc_metric,
    metric_value,
    normalize_metric_name,
)
from app.services.postgis import load_postgis_map_geometries
from app.services.summary import build_summary

router = APIRouter(prefix="/api", tags=["civic data"])

DEFAULT_GEOGRAPHY_TYPE = "municipality"
SUPPORTED_GEOGRAPHY_TYPES = {"municipality", "census_tract"}


def resolve_year(db: Session, year: int | None) -> int:
    if year is not None:
        return year
    latest_year = db.query(func.max(Metric.year)).scalar()
    if latest_year is None:
        raise HTTPException(status_code=404, detail="No metrics have been loaded.")
    return int(latest_year)


def parse_ids(ids: str | None) -> list[str]:
    if not ids:
        return []
    return [item.strip() for item in ids.split(",") if item.strip()]


def normalize_geography_type(geography_type: str | None) -> str | None:
    if geography_type is None:
        return None
    normalized = geography_type.strip().lower()
    if normalized not in SUPPORTED_GEOGRAPHY_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported geography type: {geography_type}")
    return normalized


def serialize_metric(metric: Metric) -> dict[str, Any]:
    return {
        "year": metric.year,
        "median_income": metric.median_income,
        "median_rent": metric.median_rent,
        "population": metric.population,
        "previous_population": metric.previous_population,
        "population_growth_pct": metric_value("population_growth_pct", metric),
        "renter_households": metric.renter_households,
        "rent_burden_pct": metric.rent_burden_pct,
        "rent_to_income_ratio": metric_value("rent_to_income_ratio", metric),
        "affordability_index": metric.affordability_index,
    }


def serialize_geography(geography: Geography, metric: Metric | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": geography.id,
        "geoid": geography.geoid,
        "name": geography.name,
        "type": geography.type,
        "county": geography.county,
        "state": geography.state,
        "bbox": geography.bbox,
        "geometry": geography.geometry,
        "geometry_source": geography.geometry_source,
    }
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


def available_cmhc_years(db: Session, geography_type: str | None = None) -> list[int]:
    query = db.query(CmhcMetric.year).distinct()
    if geography_type:
        query = query.join(Geography, Geography.geoid == CmhcMetric.geoid).filter(
            Geography.type == geography_type
        )
    years = sorted(row[0] for row in query.all())
    return years


def serialize_cmhc_metric(cmhc: CmhcMetric) -> dict[str, Any]:
    return {
        "year": cmhc.year,
        "vacancy_rate": cmhc.vacancy_rate,
        "average_rent_total": cmhc.average_rent_total,
        "average_rent_bachelor": cmhc.average_rent_bachelor,
        "average_rent_1br": cmhc.average_rent_1br,
        "average_rent_2br": cmhc.average_rent_2br,
        "average_rent_3br_plus": cmhc.average_rent_3br_plus,
        "turnover_rate": cmhc.turnover_rate,
        "availability_rate": cmhc.availability_rate,
        "rental_universe": cmhc.rental_universe,
        "housing_starts_total": cmhc.housing_starts_total,
        "housing_starts_single": cmhc.housing_starts_single,
        "housing_starts_semi": cmhc.housing_starts_semi,
        "housing_starts_row": cmhc.housing_starts_row,
        "housing_starts_apartment": cmhc.housing_starts_apartment,
        "housing_completions": cmhc.housing_completions,
        "units_under_construction": cmhc.units_under_construction,
    }


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


@router.get("/geographies")
def list_geographies(
    search: str | None = Query(default=None, min_length=1),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    year: int | None = None,
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
    metrics = {
        metric.geoid: metric
        for metric in db.query(Metric).filter(Metric.year == metric_year).all()
    }
    return {
        "year": metric_year,
        "items": [
            serialize_geography(geography, metrics.get(geography.geoid))
            for geography in geographies
        ],
    }


@router.get("/geographies/{geography_id}")
def get_geography(
    geography_id: str,
    year: int | None = None,
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
    year: int | None = None,
    db: Session = Depends(get_db),
):
    metric_key = normalize_metric_name(metric)
    if metric_key not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")
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
    year: int | None = None,
    db: Session = Depends(get_db),
):
    metric_year = resolve_year(db, year)
    id_list = parse_ids(ids)
    normalized_type = normalize_geography_type(geography_type)
    records = joined_records(db, metric_year, id_list, normalized_type, include_geometry=False)
    if id_list and not records:
        raise HTTPException(status_code=404, detail="No selected geographies were found.")

    cmhc_query = db.query(CmhcMetric)
    cmhc_latest = db.query(func.max(CmhcMetric.year)).scalar()
    if cmhc_latest:
        cmhc_query = cmhc_query.filter(CmhcMetric.year == cmhc_latest)
        if normalized_type:
            cmhc_query = cmhc_query.join(Geography, Geography.geoid == CmhcMetric.geoid).filter(
                Geography.type == normalized_type
            )
        if id_list:
            cmhc_query = cmhc_query.filter(CmhcMetric.geoid.in_(id_list))
        cmhc_records = cmhc_query.all()
    else:
        cmhc_records = []

    return build_summary(records, metric_year, cmhc_records=cmhc_records)


@router.get("/compare")
def compare_geographies(
    ids: str | None = Query(default=None, description="Comma-separated GEOIDs."),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    year: int | None = None,
    db: Session = Depends(get_db),
):
    metric_year = resolve_year(db, year)
    id_list = parse_ids(ids)
    normalized_type = normalize_geography_type(geography_type)
    records = joined_records(db, metric_year, id_list, normalized_type, include_geometry=False)

    if id_list:
        record_by_geoid = {geography.geoid: (geography, metric) for geography, metric in records}
        ordered_records = [record_by_geoid[geoid] for geoid in id_list if geoid in record_by_geoid]
    else:
        ordered_records = sorted(records, key=lambda item: item[1].population or 0, reverse=True)[:6]

    cmhc_year = resolve_cmhc_year(db, None) if db.query(CmhcMetric).count() > 0 else metric_year
    cmhc_by_geoid = {
        row.geoid: row
        for row in db.query(CmhcMetric).filter(CmhcMetric.year == cmhc_year).all()
    }

    items = []
    for geography, metric in ordered_records:
        item: dict[str, Any] = {
            "geoid": geography.geoid,
            "name": geography.name,
            "type": geography.type,
            "county": geography.county,
            "metrics": serialize_metric(metric),
        }
        cmhc_row = cmhc_by_geoid.get(geography.geoid)
        if cmhc_row:
            item["cmhc_metrics"] = serialize_cmhc_metric(cmhc_row)
        else:
            item["cmhc_metrics"] = None
        items.append(item)

    return {
        "year": metric_year,
        "items": items,
    }


@router.get("/map-data")
def get_map_data(
    metric: str = Query(default="rent_burden_pct"),
    geography_type: str | None = Query(default=DEFAULT_GEOGRAPHY_TYPE, alias="type"),
    detail: Literal["full", "display"] = Query(
        default="full",
        description="Use display for map-ready simplified geometry; full returns stored geometry.",
    ),
    year: int | None = None,
    db: Session = Depends(get_db),
):
    metric_key = normalize_metric_name(metric)
    if metric_key not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")
    normalized_type = normalize_geography_type(geography_type)
    cmhc = is_cmhc_metric(metric_key)

    metric_year = resolve_year(db, year)
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

    # CMHC metric handling
    cmhc_by_geoid: dict[str, CmhcMetric] = {}
    cmhc_year = metric_year
    if cmhc:
        cmhc_year = resolve_cmhc_year(db, year)
        cmhc_by_geoid = {
            row.geoid: row
            for row in db.query(CmhcMetric).filter(CmhcMetric.year == cmhc_year).all()
        }

    if cmhc:
        values = [
            metric_value(metric_key, cmhc_row)
            for cmhc_row in cmhc_by_geoid.values()
            if metric_value(metric_key, cmhc_row) is not None
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
        "domain": domain,
        "geography_type": normalized_type,
        "data_quality": data_quality(normalized_type, cmhc=cmhc),
        "source": map_data_source(normalized_type, cmhc=cmhc),
    }
    if cmhc:
        metadata["available_years"] = available_cmhc_years(db, normalized_type)

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
        cmhc_row = cmhc_by_geoid.get(geography.geoid)
        if cmhc:
            props["value"] = metric_value(metric_key, cmhc_row) if cmhc_row else None
        else:
            props["value"] = metric_value(metric_key, row)
        if cmhc_row:
            props["cmhc_metrics"] = serialize_cmhc_metric(cmhc_row)
            props["cmhc_year"] = cmhc_year
        features.append(
            {
                "type": "Feature",
                "geometry": postgis_geometries.get(
                    geography.geoid,
                    map_geometry(geography.geometry, detail, normalized_type),
                ),
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


def data_quality(geography_type: str | None, cmhc: bool = False) -> dict[str, str]:
    if cmhc:
        return {
            "metric_status": "official",
            "label": "CMHC Rental Market Survey",
            "description": (
                "CMHC Rental Market Survey and Starts & Completions Survey data "
                "from the Housing Market Information Portal."
            ),
        }
    if geography_type == "census_tract":
        return {
            "metric_status": "official",
            "label": "Official tract metrics",
            "description": (
                "Census tract geometries and metrics are official Statistics Canada 2021 "
                "Census Profile values fetched via the SDMX DF_CT dataflow."
            ),
        }
    return {
        "metric_status": "official",
        "label": "Official municipal metrics",
        "description": "Packaged municipal metrics use official Statistics Canada 2021 Census Profile values.",
    }
