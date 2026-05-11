"""Fetch CMHC Rental Market Survey and Starts & Completions data from the HMIP portal.

The HMIP portal serves data via internal endpoints that return CSV.
No authentication required. Endpoint structure reverse-engineered from
the cmhc R package (github.com/mountainMath/cmhc).

Usage:
    python etl/load_cmhc.py --update-seed       # Fetch from HMIP and write seed file
    python etl/load_cmhc.py --from-seed          # Load packaged seed into database
    python etl/load_cmhc.py --print-url          # Print HMIP endpoint URLs
    python etl/load_cmhc.py --year 2023          # Fetch specific year
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HMIP_EXPORT_URL = "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable"

# Toronto CMA geography ID in HMIP
TORONTO_CMA_GEO_ID = 2270

# HMIP GeographyTypeIds
GEO_TYPE_CMA = 3
GEO_TYPE_CSD = 4
GEO_TYPE_CT = 7

# TableIds — these map to specific CMHC survey tables in the HMIP portal.
# Verify against HMIP network requests or the cmhc R package if they change.
# Rental Market Survey tables
TABLE_VACANCY_RATE = "2.1.31.3"
TABLE_AVERAGE_RENT = "2.1.31.2"
TABLE_TURNOVER_RATE = "2.1.31.7"
TABLE_AVAILABILITY_RATE = "2.1.31.5"
TABLE_RENTAL_UNIVERSE = "2.1.31.1"

# Starts & Completions tables
TABLE_HOUSING_STARTS = "1.1.4.7"
TABLE_HOUSING_COMPLETIONS = "1.1.5.7"
TABLE_UNDER_CONSTRUCTION = "1.1.6.7"

SEED_PATH = PROJECT_ROOT / "app" / "data" / "cmhc_seed.json"

REQUEST_DELAY = 0.5  # seconds between requests


@dataclass
class CmhcRow:
    geoid: str
    year: int
    vacancy_rate: float | None = None
    average_rent_total: float | None = None
    average_rent_bachelor: float | None = None
    average_rent_1br: float | None = None
    average_rent_2br: float | None = None
    average_rent_3br_plus: float | None = None
    turnover_rate: float | None = None
    availability_rate: float | None = None
    rental_universe: int | None = None
    housing_starts_total: int | None = None
    housing_starts_single: int | None = None
    housing_starts_semi: int | None = None
    housing_starts_row: int | None = None
    housing_starts_apartment: int | None = None
    housing_completions: int | None = None
    units_under_construction: int | None = None


def build_export_url(
    table_id: str,
    geography_id: int,
    geography_type_id: int,
    breakdown_geography_type_id: int | None = None,
) -> str:
    params = {
        "TableId": table_id,
        "GeographyId": geography_id,
        "GeographyTypeId": geography_type_id,
        "DisplayAs": "Table",
        "GeographyName": "Toronto",
    }
    if breakdown_geography_type_id is not None:
        params["BreakdownGeographyTypeId"] = str(breakdown_geography_type_id)
    return f"{HMIP_EXPORT_URL}?{urlencode(params)}"


def fetch_csv(url: str) -> str:
    try:
        request = Request(url, headers={"Accept": "text/csv"})
        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as exc:
        print(f"  Warning: HTTP {exc.code} fetching {url}", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"  Warning: {exc} fetching {url}", file=sys.stderr)
        return ""


def _optional_float(value: str | None) -> float | None:
    if not value or value.strip() in ("", "**", "N/A", "--", ".."):
        return None
    try:
        return float(value.strip().replace(",", ""))
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def load_geoids_from_seed() -> list[str]:
    demo_seed_path = PROJECT_ROOT / "app" / "data" / "demo_seed.json"
    seed = json.loads(demo_seed_path.read_text(encoding="utf-8"))
    return sorted(item["geoid"] for item in seed["geographies"])


def write_seed(metrics: list[CmhcRow], years: list[int]) -> int:
    seed = {
        "metadata": {
            "source": "cmhc_hmip_rental_market_and_starts_completions",
            "years": sorted(years),
            "fetched_at": datetime.now(UTC).isoformat(),
            "notes": [
                "Rental Market Survey data from CMHC Housing Market Information Portal.",
                "Starts and Completions Survey data from CMHC HMIP.",
                "Census tract rental market data covers tracts within the Toronto CMA.",
                "Starts and completions are available at municipal level only.",
            ],
        },
        "metrics": [asdict(m) for m in metrics],
    }
    SEED_PATH.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return len(metrics)


def load_from_seed() -> int:
    from app.db.init_db import init_db
    from app.db.session import SessionLocal
    from app.models import CmhcMetric, Geography

    init_db()
    db = SessionLocal()
    try:
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        count = 0
        for item in seed["metrics"]:
            geoid = item["geoid"]
            if db.query(Geography).filter(Geography.geoid == geoid).one_or_none() is None:
                continue
            existing = (
                db.query(CmhcMetric)
                .filter(CmhcMetric.geoid == geoid, CmhcMetric.year == item["year"])
                .one_or_none()
            )
            values = {k: v for k, v in item.items() if k not in ("geoid", "year")}
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                db.add(CmhcMetric(geoid=geoid, year=item["year"], **values))
            count += 1
        db.commit()
        return count
    finally:
        db.close()


def print_urls() -> None:
    print("CMHC HMIP Export URLs:")
    print(f"  Vacancy rate (CSD): {build_export_url(TABLE_VACANCY_RATE, TORONTO_CMA_GEO_ID, GEO_TYPE_CMA, GEO_TYPE_CSD)}")
    print(f"  Average rent (CSD): {build_export_url(TABLE_AVERAGE_RENT, TORONTO_CMA_GEO_ID, GEO_TYPE_CMA, GEO_TYPE_CSD)}")
    print(f"  Housing starts (CSD): {build_export_url(TABLE_HOUSING_STARTS, TORONTO_CMA_GEO_ID, GEO_TYPE_CMA, GEO_TYPE_CSD)}")
    print(f"  Vacancy rate (CT): {build_export_url(TABLE_VACANCY_RATE, TORONTO_CMA_GEO_ID, GEO_TYPE_CMA, GEO_TYPE_CT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch CMHC housing market data from HMIP portal.")
    parser.add_argument("--update-seed", "--fetch-all", action="store_true", help="Fetch from HMIP and write seed file.")
    parser.add_argument("--from-seed", action="store_true", help="Load packaged seed into database.")
    parser.add_argument("--print-url", action="store_true", help="Print HMIP endpoint URLs.")
    parser.add_argument("--year", type=int, help="Fetch a specific year (default: latest available).")
    args = parser.parse_args()

    if args.print_url:
        print_urls()
        return

    if args.from_seed:
        count = load_from_seed()
        print(f"Loaded {count} CMHC metric rows from seed.")
        return

    if args.update_seed:
        print("Fetching CMHC data from HMIP portal...")
        print("NOTE: This script requires verified HMIP TableIds.")
        print("Run --print-url first and verify the endpoints return valid CSV.")
        print("If endpoints have changed, update TABLE_* constants in this script.")
        print()
        print("For initial seed, use the placeholder in app/data/cmhc_seed.json")
        print("and update it manually or via --update-seed once endpoints are verified.")
        return

    parser.error("--update-seed, --from-seed, or --print-url is required.")


if __name__ == "__main__":
    main()
