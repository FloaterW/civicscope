from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

from sqlalchemy.orm import Session

from app.models import CmhcMetric, CmhcTractMetric, ETLRun, Geography, Metric
from app.services.metric_calculations import calculate_affordability_index
from app.services.postgis import sync_geography_geoms


def load_demo_seed() -> dict[str, Any]:
    seed_path = files("app.data").joinpath("demo_seed.json")
    return json.loads(seed_path.read_text(encoding="utf-8"))


def load_cmhc_seed() -> dict[str, Any]:
    seed_path = files("app.data").joinpath("cmhc_seed.json")
    return json.loads(seed_path.read_text(encoding="utf-8"))


def _value_differs(seed_value: Any, db_value: Any) -> bool:
    if seed_value is None and db_value is None:
        return False
    if seed_value is None or db_value is None:
        return True
    return abs(float(seed_value) - float(db_value)) > 0.5


def _demo_seed_content_changed(db: Session, seed: dict[str, Any]) -> bool:
    """Detect a database whose census metrics no longer match the packaged seed.

    Guards against the stale-volume bug where an old Docker volume keeps
    superseded (e.g. estimated) tract metrics even though the packaged seed has
    been updated to official values.  We compare verbatim official fields
    (income, rent, population) for a deterministic spread of geographies; rent
    burden is intentionally excluded because it has a serialization-time
    estimate fallback.
    """
    geographies = seed["geographies"]
    if not geographies:
        return False
    step = max(1, len(geographies) // 40)
    # First few rows plus an even spread across the file, de-duplicated so a
    # geography is never checked twice (index 0 appears in both slices).
    sample = list({id(g): g for g in geographies[:5] + geographies[::step]}.values())
    compared_fields = ("median_income", "median_rent", "population", "previous_population")
    for item in sample:
        metrics = item.get("metrics")
        if not metrics:
            continue
        seed_metric = metrics[0]
        db_row = (
            db.query(Metric)
            .filter(Metric.geoid == item["geoid"], Metric.year == seed_metric["year"])
            .first()
        )
        if db_row is None:
            return True
        for field in compared_fields:
            if _value_differs(seed_metric.get(field), getattr(db_row, field, None)):
                return True
    return False


def seed_demo_data(db: Session, force: bool = False) -> int:
    existing = db.query(Geography).count()
    seed = load_demo_seed()

    if existing and not force:
        if not _demo_seed_content_changed(db, seed):
            return 0

    if existing:
        db.query(CmhcMetric).delete()
        db.query(Metric).delete()
        db.query(Geography).delete()
        db.flush()

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
            # Store the official value only (null when Statistics Canada
            # suppressed it).  A clearly-labeled estimate is provided at
            # serialization time instead of being silently persisted.
            rent_burden_pct = metric_item.get("rent_burden_pct")

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
                dwellings_total=metric_item.get("dwellings_total"),
                dwellings_single_detached=metric_item.get("dwellings_single_detached"),
                dwellings_semi_detached=metric_item.get("dwellings_semi_detached"),
                dwellings_row_house=metric_item.get("dwellings_row_house"),
                dwellings_apt_duplex=metric_item.get("dwellings_apt_duplex"),
                dwellings_apt_low_rise=metric_item.get("dwellings_apt_low_rise"),
                dwellings_apt_high_rise=metric_item.get("dwellings_apt_high_rise"),
                owner_households=metric_item.get("owner_households"),
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
    """Detect whether stored CMHC content no longer matches the packaged seed.

    Catches both null->value (a newly populated field) and value->value drift
    (e.g. a corrected vacancy rate) where the row count is unchanged, so a stale
    Docker volume holding superseded CMHC values is re-seeded without a manual
    FORCE_RESEED. All seed metrics and nullable fields are compared in one bulk
    read so value-to-null suppression corrections are applied as well.
    """
    if not seed_metrics:
        return False
    check_fields = [
        ("housing_starts_total", "housing_starts_total"),
        ("housing_completions", "housing_completions"),
        ("units_under_construction", "units_under_construction"),
        ("unabsorbed_units", "unabsorbed_units"),
        ("rms_surveyed", "rms_surveyed"),
        ("vacancy_rate", "vacancy_rate"),
        ("average_rent_total", "average_rent_total"),
        ("average_rent_bachelor", "average_rent_bachelor"),
        ("average_rent_1br", "average_rent_1br"),
        ("average_rent_2br", "average_rent_2br"),
        ("average_rent_3br_plus", "average_rent_3br_plus"),
        ("turnover_rate", "turnover_rate"),
        ("availability_rate", "availability_rate"),
        ("rental_universe", "rental_universe"),
        ("housing_starts_single", "housing_starts_single"),
        ("housing_starts_semi", "housing_starts_semi"),
        ("housing_starts_row", "housing_starts_row"),
        ("housing_starts_apartment", "housing_starts_apartment"),
    ]
    db_rows = {(row.geoid, row.year): row for row in db.query(CmhcMetric).all()}
    for sample in seed_metrics:
        db_row = db_rows.get((sample["geoid"], sample["year"]))
        if db_row is None:
            return True
        for seed_key, db_attr in check_fields:
            seed_val = sample.get(seed_key)
            db_val = getattr(db_row, db_attr, None)
            if _value_differs(seed_val, db_val):
                return True
        if bool(sample.get("rms_surveyed", False)) != bool(db_row.rms_surveyed):
            return True
    return False


def seed_cmhc_data(db: Session, force: bool = False) -> int:
    seed = load_cmhc_seed()
    known_geoids = {row[0] for row in db.query(Geography.geoid).all()}
    expected_count = sum(1 for row in seed["metrics"] if row["geoid"] in known_geoids)
    existing_count = db.query(CmhcMetric).count()

    # Auto-detect stale seed: trigger reseed if row count changed OR
    # if seed content has changed (e.g. new fields populated).
    needs_reseed = force or existing_count != expected_count
    if not needs_reseed and existing_count > 0:
        needs_reseed = _seed_content_changed(db, seed["metrics"])

    if existing_count and not force and not needs_reseed:
        return 0

    if existing_count:
        db.query(CmhcMetric).delete()
        db.flush()

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
            unabsorbed_units=item.get("unabsorbed_units"),
            rms_surveyed=item.get("rms_surveyed", False),
        )
        db.add(cmhc)
        row_count += 1

    db.flush()
    db.commit()
    return row_count


def load_cmhc_tract_seed() -> list[dict[str, Any]]:
    """Read the committed real CMHC census-tract CSV (geoid, year, metrics)."""
    path = files("app.data").joinpath("cmhc_ct_metrics.csv")
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(path.read_text(encoding="utf-8").splitlines()):

        def _int(key: str, row=row) -> int | None:
            v = (row.get(key) or "").strip()
            return int(v) if v != "" else None

        def _str(key: str, row=row) -> str | None:
            v = (row.get(key) or "").strip()
            return v or None

        rows.append(
            {
                "geoid": row["geoid"].strip(),
                "year": int(row["year"]),
                "housing_starts_total": _int("housing_starts_total"),
                "housing_completions": _int("housing_completions"),
                "housing_starts_total_source": _str("housing_starts_total_source"),
                "housing_completions_source": _str("housing_completions_source"),
            }
        )
    return rows


def _cmhc_tract_content_changed(
    db: Session, seed_rows: list[dict[str, Any]], known: set[str]
) -> bool:
    """Detect a stale cmhc_tract_metrics table vs the packaged CSV.

    Guards against the stale-volume bug: a regenerated cmhc_ct_metrics.csv
    (corrected/extended data) must reseed even if the row count is unchanged.
    Compares a content fingerprint over EVERY row (the table is small), so a
    single changed value cannot slip through a sparse sample.
    """
    expected = [r for r in seed_rows if r["geoid"] in known]
    db_rows = db.query(
        CmhcTractMetric.geoid,
        CmhcTractMetric.year,
        CmhcTractMetric.housing_starts_total,
        CmhcTractMetric.housing_completions,
        CmhcTractMetric.housing_starts_total_source,
        CmhcTractMetric.housing_completions_source,
    ).all()
    if len(db_rows) != len(expected):
        return True

    db_fp = {tuple(r) for r in db_rows}
    seed_fp = {
        (
            r["geoid"],
            r["year"],
            r["housing_starts_total"],
            r["housing_completions"],
            r["housing_starts_total_source"],
            r["housing_completions_source"],
        )
        for r in expected
    }
    return db_fp != seed_fp


def load_transit_scores() -> list[dict[str, Any]]:
    path = files("app.data").joinpath("transit_scores.csv")
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(path.read_text(encoding="utf-8").splitlines()):
        def _float(key: str, row=row) -> float | None:
            v = (row.get(key) or "").strip()
            if not v:
                return None
            return float(v)
        def _int(key: str, row=row) -> int | None:
            v = (row.get(key) or "").strip()
            if not v:
                return None
            return int(v)
        rows.append({
            "geoid": row["geoid"].strip(),
            "transit_route_count": _int("transit_route_count"),
            "transit_score": _float("transit_score"),
        })
    return rows


def seed_transit_scores(db: Session, force: bool = False) -> int:
    """Synchronize tract transit scores, including explicit zero-service tracts.

    Older packaged CSVs contain only tracts reached by at least one route. Missing
    tract rows therefore mean zero nearby routes, while a missing/empty CSV still
    means the dataset is unavailable and leaves database values untouched.
    """
    seed_rows = load_transit_scores()
    if not seed_rows:
        return 0

    seeded = {row["geoid"]: row for row in seed_rows}
    tract_metrics = (
        db.query(Metric)
        .join(Geography, Geography.geoid == Metric.geoid)
        .filter(Geography.type == "census_tract")
        .all()
    )

    def expected(metric: Metric) -> tuple[int, float]:
        row = seeded.get(metric.geoid)
        if row is None:
            return 0, 0.0
        return int(row["transit_route_count"] or 0), float(row["transit_score"] or 0.0)

    if not force and all(
        metric.transit_route_count == expected(metric)[0]
        and metric.transit_score == expected(metric)[1]
        for metric in tract_metrics
    ):
        return 0

    count = 0
    for metric in tract_metrics:
        route_count, score = expected(metric)
        metric.transit_route_count = route_count
        metric.transit_score = score
        count += 1
    db.flush()
    db.commit()
    return count


def seed_cmhc_tract_data(db: Session, force: bool = False) -> int:
    """Load real census-tract SCSS values from cmhc_ct_metrics.csv.

    Idempotent, but reseeds when the packaged CSV's content has changed (not just
    its row count). Only rows for known tract geoids are inserted.
    """
    seed_rows = load_cmhc_tract_seed()
    known = {row[0] for row in db.query(Geography.geoid).all()}
    existing = db.query(CmhcTractMetric).count()
    if existing and not force and not _cmhc_tract_content_changed(db, seed_rows, known):
        return 0
    if existing:
        db.query(CmhcTractMetric).delete()
        db.flush()
        # Clear the identity map so re-inserted rows that reuse autoincrement
        # ids (SQLite/StaticPool) don't collide with the just-deleted ones.
        db.expunge_all()

    count = 0
    for r in seed_rows:
        if r["geoid"] not in known:
            continue
        db.add(
            CmhcTractMetric(
                geoid=r["geoid"],
                year=r["year"],
                housing_starts_total=r["housing_starts_total"],
                housing_completions=r["housing_completions"],
                housing_starts_total_source=r["housing_starts_total_source"],
                housing_completions_source=r["housing_completions_source"],
            )
        )
        count += 1
    db.flush()
    db.commit()
    return count
