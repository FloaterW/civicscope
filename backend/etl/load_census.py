from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
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
from app.models import ETLRun, Geography, Metric
from app.services.metric_calculations import calculate_affordability_index
from etl.load_geo import GTA_MUNICIPALITIES

PROFILE_BASE_URL = "https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/data/STC_CP,DF_CSD"

# Official Statistics Canada 2021 Census Profile characteristic IDs.
OFFICIAL_CHARACTERISTIC_IDS = {
    "population": "1",
    "previous_population": "2",
    "median_income": "229",
    "renter_households": "1476",
    "rent_burden_pct": "1478",
    "median_rent": "1480",
    "dwellings_total": "41",
    "dwellings_single_detached": "42",
    "dwellings_semi_detached": "43",
    "dwellings_row_house": "44",
    "dwellings_apt_duplex": "45",
    "dwellings_apt_low_rise": "46",
    "dwellings_apt_high_rise": "47",
    "owner_households": "1406",
}

DEFAULT_CHARACTERISTIC_IDS = OFFICIAL_CHARACTERISTIC_IDS
CHARACTERISTIC_TO_FIELD = {value: key for key, value in OFFICIAL_CHARACTERISTIC_IDS.items()}
# rent_burden_pct is intentionally NOT required: Statistics Canada routinely
# suppresses it for small geographies, and it is derivable from rent and income
# as a clearly-labeled estimate at serialization time. Requiring it would crash
# the official-metrics ETL whenever a single CSD value is suppressed.
REQUIRED_OFFICIAL_FIELDS = (
    "population", "previous_population", "median_income",
    "renter_households", "median_rent",
)

FIELD_ALIASES = {
    "geoid": ("geoid", "csduid", "csd_uid", "CSDUID"),
    "year": ("year", "YEAR"),
    "median_income": ("median_income", "median_household_income", "income_median", "MEDIAN_INCOME"),
    "median_rent": ("median_rent", "median_monthly_rent", "gross_rent_median", "MEDIAN_RENT"),
    "population": ("population", "population_2021", "POPULATION"),
    "previous_population": ("previous_population", "population_2016", "PREVIOUS_POPULATION"),
    "renter_households": ("renter_households", "tenant_households", "RENTER_HOUSEHOLDS"),
    "rent_burden_pct": ("rent_burden_pct", "shelter_cost_burden_pct", "RENT_BURDEN_PCT"),
    "dwellings_total": ("dwellings_total",),
    "dwellings_single_detached": ("dwellings_single_detached",),
    "dwellings_semi_detached": ("dwellings_semi_detached",),
    "dwellings_row_house": ("dwellings_row_house",),
    "dwellings_apt_duplex": ("dwellings_apt_duplex",),
    "dwellings_apt_low_rise": ("dwellings_apt_low_rise",),
    "dwellings_apt_high_rise": ("dwellings_apt_high_rise",),
    "owner_households": ("owner_households",),
}


@dataclass(frozen=True)
class MetricInput:
    geoid: str
    year: int
    median_income: float | None
    median_rent: float | None
    population: int | None
    previous_population: int | None
    renter_households: int | None
    rent_burden_pct: float | None
    dwellings_total: int | None = None
    dwellings_single_detached: int | None = None
    dwellings_semi_detached: int | None = None
    dwellings_row_house: int | None = None
    dwellings_apt_duplex: int | None = None
    dwellings_apt_low_rise: int | None = None
    dwellings_apt_high_rise: int | None = None
    owner_households: int | None = None


def csduid_to_dguid(geoid: str) -> str:
    return f"2021A0005{geoid}"


def dguid_to_csduid(dguid: str) -> str:
    prefix = "2021A0005"
    if not dguid.startswith(prefix):
        raise ValueError(f"Unsupported CSD DGUID: {dguid}")
    return dguid.removeprefix(prefix)


def build_profile_url(csd_uids: list[str], characteristic_ids: list[str] | None = None) -> str:
    characteristics = "+".join(characteristic_ids or list(DEFAULT_CHARACTERISTIC_IDS.values()))
    geographies = "+".join(csduid_to_dguid(geoid) for geoid in csd_uids)
    key = f"A5.{geographies}.1.{characteristics}.1"
    params = urlencode({"format": "csv", "detail": "dataonly"})
    return f"{PROFILE_BASE_URL}/{key}?{params}"


def fetch_profile_csv(url: str) -> str:
    with urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def fetch_official_gta_metrics(csd_uids: list[str] | None = None) -> list[MetricInput]:
    geoids = csd_uids or list(GTA_MUNICIPALITIES)
    url = build_profile_url(geoids, list(OFFICIAL_CHARACTERISTIC_IDS.values()))
    metrics = parse_profile_csv_text(fetch_profile_csv(url))
    validate_official_metrics(metrics, geoids)
    return metrics


def validate_official_metrics(metrics: list[MetricInput], expected_geoids: list[str]) -> None:
    by_geoid = {metric.geoid: metric for metric in metrics}
    missing = sorted(set(expected_geoids) - set(by_geoid))
    if missing:
        raise ValueError(f"Statistics Canada response is missing expected CSDUIDs: {', '.join(missing)}")

    incomplete: list[str] = []
    for geoid in expected_geoids:
        metric = by_geoid[geoid]
        missing_fields = [
            field
            for field in REQUIRED_OFFICIAL_FIELDS
            if getattr(metric, field) is None
        ]
        if missing_fields:
            incomplete.append(f"{geoid} ({', '.join(missing_fields)})")

    if incomplete:
        raise ValueError(
            "Statistics Canada response is missing required official metrics for: "
            + "; ".join(incomplete)
        )


def parse_metric_csv(path: Path, default_year: int = 2021) -> list[MetricInput]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return [parse_metric_row(row, default_year) for row in rows]


def parse_profile_csv_text(text: str, default_year: int = 2021) -> list[MetricInput]:
    rows = csv.DictReader(text.splitlines())
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        field = CHARACTERISTIC_TO_FIELD.get(str(row.get("CHARACTERISTIC", "")).strip())
        if field is None:
            continue

        geoid = dguid_to_csduid(str(row["REF_AREA"]).strip())
        grouped.setdefault(geoid, {"geoid": geoid, "year": row.get("TIME_PERIOD") or default_year})
        grouped[geoid][field] = row.get("OBS_VALUE")

    return [parse_metric_row(row, default_year) for row in grouped.values()]


def parse_metric_row(row: dict[str, Any], default_year: int = 2021) -> MetricInput:
    geoid = _required_text(row, "geoid")
    return MetricInput(
        geoid=geoid,
        year=_optional_int(_first_value(row, "year")) or default_year,
        median_income=_optional_float(_first_value(row, "median_income")),
        median_rent=_optional_float(_first_value(row, "median_rent")),
        population=_optional_int(_first_value(row, "population")),
        previous_population=_optional_int(_first_value(row, "previous_population")),
        renter_households=_optional_int(_first_value(row, "renter_households")),
        rent_burden_pct=_optional_float(_first_value(row, "rent_burden_pct")),
        dwellings_total=_optional_int(_first_value(row, "dwellings_total")),
        dwellings_single_detached=_optional_int(_first_value(row, "dwellings_single_detached")),
        dwellings_semi_detached=_optional_int(_first_value(row, "dwellings_semi_detached")),
        dwellings_row_house=_optional_int(_first_value(row, "dwellings_row_house")),
        dwellings_apt_duplex=_optional_int(_first_value(row, "dwellings_apt_duplex")),
        dwellings_apt_low_rise=_optional_int(_first_value(row, "dwellings_apt_low_rise")),
        dwellings_apt_high_rise=_optional_int(_first_value(row, "dwellings_apt_high_rise")),
        owner_households=_optional_int(_first_value(row, "owner_households")),
    )


def upsert_metrics(db, metrics: list[MetricInput]) -> int:
    count = 0
    for item in metrics:
        if db.query(Geography).filter(Geography.geoid == item.geoid).one_or_none() is None:
            raise ValueError(f"Cannot load metrics for unknown geography {item.geoid}. Load geographies first.")

        metric = (
            db.query(Metric)
            .filter(Metric.geoid == item.geoid, Metric.year == item.year)
            .one_or_none()
        )
        values = {
            "geoid": item.geoid,
            "year": item.year,
            "median_income": item.median_income,
            "median_rent": item.median_rent,
            "population": item.population,
            "previous_population": item.previous_population,
            "renter_households": item.renter_households,
            # Persist the official value only (null when suppressed); rent
            # burden is estimated as a labeled fallback at serialization time.
            "rent_burden_pct": item.rent_burden_pct,
            "affordability_index": calculate_affordability_index(item.median_rent, item.median_income),
            "dwellings_total": item.dwellings_total,
            "dwellings_single_detached": item.dwellings_single_detached,
            "dwellings_semi_detached": item.dwellings_semi_detached,
            "dwellings_row_house": item.dwellings_row_house,
            "dwellings_apt_duplex": item.dwellings_apt_duplex,
            "dwellings_apt_low_rise": item.dwellings_apt_low_rise,
            "dwellings_apt_high_rise": item.dwellings_apt_high_rise,
            "owner_households": item.owner_households,
        }
        if metric is None:
            db.add(Metric(**values))
        else:
            for key, value in values.items():
                setattr(metric, key, value)
        count += 1
    return count


def load_metrics_csv(path: Path, default_year: int = 2021) -> int:
    started_at = datetime.now(UTC)
    metrics = parse_metric_csv(path, default_year)
    init_db()
    db = SessionLocal()
    try:
        row_count = upsert_metrics(db, metrics)
        db.add(
            ETLRun(
                source=f"statistics_canada_census_profile_csv:{path.name}",
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
                source=f"statistics_canada_census_profile_csv:{path.name}",
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


def load_official_gta_metrics() -> int:
    started_at = datetime.now(UTC)
    metrics = fetch_official_gta_metrics()
    init_db()
    db = SessionLocal()
    try:
        row_count = upsert_metrics(db, metrics)
        db.add(
            ETLRun(
                source="statistics_canada_2021_census_profile_api",
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
                source="statistics_canada_2021_census_profile_api",
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


def update_seed_metrics(seed_path: Path, metrics: list[MetricInput]) -> int:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    by_geoid = {metric.geoid: metric for metric in metrics}
    updated = 0

    for item in seed["geographies"]:
        metric = by_geoid.get(item["geoid"])
        if metric is None:
            continue
        item["metrics"] = [
            {
                "year": metric.year,
                "median_income": metric.median_income,
                "median_rent": metric.median_rent,
                "population": metric.population,
                "previous_population": metric.previous_population,
                "renter_households": metric.renter_households,
                "rent_burden_pct": metric.rent_burden_pct,
                "dwellings_total": metric.dwellings_total,
                "dwellings_single_detached": metric.dwellings_single_detached,
                "dwellings_semi_detached": metric.dwellings_semi_detached,
                "dwellings_row_house": metric.dwellings_row_house,
                "dwellings_apt_duplex": metric.dwellings_apt_duplex,
                "dwellings_apt_low_rise": metric.dwellings_apt_low_rise,
                "dwellings_apt_high_rise": metric.dwellings_apt_high_rise,
                "owner_households": metric.owner_households,
            }
        ]
        updated += 1

    seed["metadata"]["source"] = "statistics_canada_2021_census_profile_and_csd_boundaries"
    seed["metadata"]["year"] = 2021
    seed["metadata"]["notes"] = [
        "Municipal geometries are Statistics Canada 2021 cartographic census subdivision boundaries.",
        "Metrics are loaded from official Statistics Canada 2021 Census Profile characteristics: population 2021, population 2016, median household income, tenant households, tenant rent burden, and median monthly shelter costs for rented dwellings.",
    ]
    seed_path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return updated


def _first_value(row: dict[str, Any], field: str) -> Any:
    for alias in FIELD_ALIASES[field]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def _required_text(row: dict[str, Any], field: str) -> str:
    value = _first_value(row, field)
    if value in (None, ""):
        raise ValueError(f"Missing required field: {field}")
    return str(value).strip()


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "..", "x", "F"):
        return None
    return float(str(value).replace(",", "").replace("%", ""))


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Load GTA Census Profile metrics.")
    parser.add_argument("--csv", type=Path, help="Path to a normalized Statistics Canada metric CSV.")
    parser.add_argument("--official-gta", action="store_true", help="Fetch official 2021 Census Profile metrics for GTA municipalities.")
    parser.add_argument("--update-seed", action="store_true", help="Refresh packaged demo seed metrics from the official Census Profile API.")
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument("--print-profile-url", nargs="+", metavar="CSDUID")
    parser.add_argument("--characteristics", nargs="*", help="Statistics Canada characteristic IDs.")
    args = parser.parse_args()

    if args.print_profile_url:
        print(build_profile_url(args.print_profile_url, args.characteristics))
        return

    if args.official_gta:
        row_count = load_official_gta_metrics()
        print(f"Loaded {row_count} official Statistics Canada metric rows.")
        return

    if args.update_seed:
        row_count = update_seed_metrics(PROJECT_ROOT / "app" / "data" / "demo_seed.json", fetch_official_gta_metrics())
        print(f"Updated {row_count} packaged seed metric rows.")
        return

    if not args.csv:
        parser.error("--csv, --official-gta, or --update-seed is required unless --print-profile-url is used.")

    row_count = load_metrics_csv(args.csv, args.year)
    print(f"Loaded {row_count} metric rows.")


if __name__ == "__main__":
    main()
