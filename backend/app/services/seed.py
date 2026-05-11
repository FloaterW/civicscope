from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

from sqlalchemy.orm import Session

from app.models import CmhcMetric, ETLRun, Geography, Metric
from app.services.metric_calculations import (
    calculate_affordability_index,
    estimate_rent_burden_pct,
)
from app.services.postgis import sync_geography_geoms


def load_demo_seed() -> dict[str, Any]:
    seed_path = files("app.data").joinpath("demo_seed.json")
    return json.loads(seed_path.read_text(encoding="utf-8"))


def load_cmhc_seed() -> dict[str, Any]:
    seed_path = files("app.data").joinpath("cmhc_seed.json")
    return json.loads(seed_path.read_text(encoding="utf-8"))


def seed_demo_data(db: Session, force: bool = False) -> int:
    existing = db.query(Geography).count()
    if existing and not force:
        return 0

    if force:
        db.query(CmhcMetric).delete()
        db.query(Metric).delete()
        db.query(Geography).delete()
        db.flush()

    seed = load_demo_seed()
    row_count = 0
    started_at = datetime.now(UTC)

    for item in seed["geographies"]:
        geography = Geography(
            geoid=item["geoid"],
            name=item["name"],
            type=item["type"],
            county=item.get("county"),
            state=item.get("state", "ON"),
            geometry=item["geometry"],
            bbox=item["bbox"],
            geometry_source=item["geometry_source"],
        )
        db.add(geography)
        row_count += 1

        for metric_item in item["metrics"]:
            median_rent = metric_item.get("median_rent")
            median_income = metric_item.get("median_income")
            rent_burden_pct = metric_item.get("rent_burden_pct")
            if rent_burden_pct is None:
                rent_burden_pct = estimate_rent_burden_pct(median_rent, median_income)

            metric = Metric(
                geoid=item["geoid"],
                year=metric_item["year"],
                median_income=median_income,
                median_rent=median_rent,
                population=metric_item.get("population"),
                previous_population=metric_item.get("previous_population"),
                renter_households=metric_item.get("renter_households"),
                rent_burden_pct=rent_burden_pct,
                affordability_index=metric_item.get("affordability_index")
                or calculate_affordability_index(median_rent, median_income),
            )
            db.add(metric)
            row_count += 1

    db.flush()
    sync_geography_geoms(db)
    db.add(
        ETLRun(
            source=seed["metadata"]["source"],
            status="success",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            row_count=row_count,
            error_message=None,
        )
    )
    db.commit()
    return row_count


def _seed_content_changed(db: Session, seed_metrics: list[dict[str, Any]]) -> bool:
    """Spot-check whether seed content has changed beyond just row count.

    Compares a sample of fields from the seed file against the DB to detect
    updates where the row count stays the same but values changed (e.g.
    housing_starts_total going from NULL to a real value).
    """
    if not seed_metrics:
        return False
    sample = seed_metrics[0]
    db_row = (
        db.query(CmhcMetric)
        .filter(CmhcMetric.geoid == sample["geoid"], CmhcMetric.year == sample["year"])
        .first()
    )
    if db_row is None:
        return True
    # Check fields that may have been added or updated
    check_fields = [
        ("housing_starts_total", "housing_starts_total"),
        ("housing_completions", "housing_completions"),
        ("units_under_construction", "units_under_construction"),
        ("vacancy_rate", "vacancy_rate"),
    ]
    for seed_key, db_attr in check_fields:
        seed_val = sample.get(seed_key)
        db_val = getattr(db_row, db_attr, None)
        if seed_val is not None and db_val is None:
            return True
    return False


def seed_cmhc_data(db: Session, force: bool = False) -> int:
    seed = load_cmhc_seed()
    expected_count = len(seed["metrics"])
    existing_count = db.query(CmhcMetric).count()

    # Auto-detect stale seed: trigger reseed if row count changed OR
    # if seed content has changed (e.g. new fields populated).
    needs_reseed = force or (existing_count > 0 and existing_count < expected_count)
    if not needs_reseed and existing_count > 0:
        needs_reseed = _seed_content_changed(db, seed["metrics"])

    if existing_count and not force and not needs_reseed:
        return 0

    if existing_count:
        db.query(CmhcMetric).delete()
        db.flush()

    # Build set of known geoids for fast lookup
    known_geoids = {row[0] for row in db.query(Geography.geoid).all()}

    row_count = 0

    for item in seed["metrics"]:
        if item["geoid"] not in known_geoids:
            continue
        cmhc = CmhcMetric(
            geoid=item["geoid"],
            year=item["year"],
            vacancy_rate=item.get("vacancy_rate"),
            average_rent_total=item.get("average_rent_total"),
            average_rent_bachelor=item.get("average_rent_bachelor"),
            average_rent_1br=item.get("average_rent_1br"),
            average_rent_2br=item.get("average_rent_2br"),
            average_rent_3br_plus=item.get("average_rent_3br_plus"),
            turnover_rate=item.get("turnover_rate"),
            availability_rate=item.get("availability_rate"),
            rental_universe=item.get("rental_universe"),
            housing_starts_total=item.get("housing_starts_total"),
            housing_starts_single=item.get("housing_starts_single"),
            housing_starts_semi=item.get("housing_starts_semi"),
            housing_starts_row=item.get("housing_starts_row"),
            housing_starts_apartment=item.get("housing_starts_apartment"),
            housing_completions=item.get("housing_completions"),
            units_under_construction=item.get("units_under_construction"),
        )
        db.add(cmhc)
        row_count += 1

    db.flush()
    db.commit()
    return row_count
