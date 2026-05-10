from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

from sqlalchemy.orm import Session

from app.models import ETLRun, Geography, Metric
from app.services.metric_calculations import (
    calculate_affordability_index,
    estimate_rent_burden_pct,
)
from app.services.postgis import sync_geography_geoms


def load_demo_seed() -> dict[str, Any]:
    seed_path = files("app.data").joinpath("demo_seed.json")
    return json.loads(seed_path.read_text(encoding="utf-8"))


def seed_demo_data(db: Session, force: bool = False) -> int:
    existing = db.query(Geography).count()
    if existing and not force:
        return 0

    if force:
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
