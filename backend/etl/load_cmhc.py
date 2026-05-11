"""Fetch CMHC Rental Market Survey data from the HMIP portal.

The HMIP portal serves data via internal POST endpoints that return CSV.
No authentication required. The ExportTable endpoint requires POST with
specific parameters including Survey type, time period, and export type.

Data is returned at the CMHC "survey zone" level, which requires mapping
and aggregation to align with census subdivision (municipality) geoids.

Usage:
    python etl/load_cmhc.py --update-seed       # Fetch from HMIP and write seed file
    python etl/load_cmhc.py --from-seed          # Load packaged seed into database
    python etl/load_cmhc.py --print-url          # Print HMIP endpoint URLs
    python etl/load_cmhc.py --year 2023          # Fetch specific year only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
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
GEO_TYPE_ZONE = 5  # Survey zone breakdown (used by RMS)

# The RMS Summary table (2.1.31.3) returns vacancy rate, availability rate,
# average rent, median rent, rent % change, and rental universe in one CSV.
TABLE_RMS_SUMMARY = "2.1.31.3"

# RMS survey month — the Rental Market Survey is conducted in October each year.
RMS_SURVEY_MONTH = 10

SEED_PATH = PROJECT_ROOT / "app" / "data" / "cmhc_seed.json"

REQUEST_DELAY = 0.5  # seconds between requests to be polite

# Default year range: 2018-2025 (8 years of RMS data)
DEFAULT_START_YEAR = 2018
DEFAULT_END_YEAR = 2025

# ---------------------------------------------------------------------------
# Survey zone → municipality geoid mapping
# ---------------------------------------------------------------------------
# CMHC breaks the Toronto CMA into ~31 survey zones. These don't align 1:1
# with census subdivisions. We map them as follows:
#
# - Toronto: 17 internal zones (former boroughs) → aggregate to 3520005
# - Mississauga: 3 zones → aggregate to 3521005
# - Brampton: 2 zones → aggregate to 3521010
# - Single-municipality zones: direct mapping
# - Combined zones: assign the same values to each constituent municipality
#
# Municipalities without CMHC survey zone coverage get no CMHC data.
# ---------------------------------------------------------------------------

# Maps survey zone name (as it appears in the CSV) → list of geoids
ZONE_TO_GEOIDS: dict[str, list[str]] = {
    # City of Toronto — 17 internal survey zones
    "Toronto (Central)": ["3520005"],
    "Toronto (East)": ["3520005"],
    "Toronto (North)": ["3520005"],
    "Toronto (West)": ["3520005"],
    "Etobicoke (South)": ["3520005"],
    "Etobicoke (Central)": ["3520005"],
    "Etobicoke (North)": ["3520005"],
    "York": ["3520005"],
    "East York": ["3520005"],
    "Scarborough (Central)": ["3520005"],
    "Scarborough (North)": ["3520005"],
    "Scarborough (East)": ["3520005"],
    "North York (Southeast)": ["3520005"],
    "North York (Northeast)": ["3520005"],
    "North York (Southwest)": ["3520005"],
    "North York (N.Central)": ["3520005"],
    "North York (Northwest)": ["3520005"],
    # Mississauga — 3 zones
    "Mississauga (South)": ["3521005"],
    "Mississauga (Northwest)": ["3521005"],
    "Mississauga (Northeast)": ["3521005"],
    # Brampton — 2 zones
    "Brampton (West)": ["3521010"],
    "Brampton (East)": ["3521010"],
    # Single-municipality zones
    "Oakville": ["3524001"],
    "Caledon": ["3521024"],
    "Markham": ["3519036"],
    # Combined zones — data shared across constituent municipalities
    "Richmond Hill/Vaughan/King": ["3519038", "3519028", "3519049"],
    "Aurora, Newmkt, Whit-St.": ["3519046", "3519048", "3519044"],
    "Pickering/Ajax/Uxbridge": ["3518001", "3518005", "3518029"],
    "Milton/Halton Hills": ["3524009", "3524015"],
    # These zones are outside our GTA-25 municipality set — skip
    # "Orangeville/Mono", "Bradford/West Gwillimbury/New Tecumseth"
}

# Reverse: which geoids need multi-zone aggregation?
# Build set of geoids that appear in multiple zone entries.
_geoid_zone_count: dict[str, int] = {}
for _zones_geoids in ZONE_TO_GEOIDS.values():
    for _gid in _zones_geoids:
        _geoid_zone_count[_gid] = _geoid_zone_count.get(_gid, 0) + 1

AGGREGATED_GEOIDS = {gid for gid, count in _geoid_zone_count.items() if count > 1}
# Expected: {"3520005", "3521005", "3521010"}


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


@dataclass
class ZoneData:
    """Parsed data for a single CMHC survey zone from the RMS Summary CSV."""

    zone_name: str
    vacancy_rate: float | None = None
    availability_rate: float | None = None
    average_rent: float | None = None
    median_rent: float | None = None
    rent_change_pct: float | None = None
    rental_universe: int | None = None


# ---------------------------------------------------------------------------
# HMIP API
# ---------------------------------------------------------------------------


def _optional_float(value: str | None) -> float | None:
    """Parse a float from CMHC CSV, handling suppressed/missing values."""
    if not value or value.strip() in ("", "**", "N/A", "--", "..", "++"):
        return None
    try:
        return float(value.strip().replace(",", ""))
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def fetch_rms_summary_csv(year: int) -> str:
    """Fetch the RMS Summary CSV from HMIP via POST.

    The ExportTable endpoint requires POST with specific form parameters.
    Returns the raw CSV text, or empty string on failure.
    """
    params = {
        "TableId": TABLE_RMS_SUMMARY,
        "GeographyId": str(TORONTO_CMA_GEO_ID),
        "GeographyTypeId": str(GEO_TYPE_CMA),
        "BreakdownGeographyTypeId": str(GEO_TYPE_ZONE),
        "DisplayAs": "Table",
        "Ytd": "False",
        "DefaultDataField": "vacancy_rate_pct",
        "Survey": "Rms",
        "ForTimePeriod.Year": str(year),
        "ForTimePeriod.Month": str(RMS_SURVEY_MONTH),
        "ExportType": "csv",
    }
    data = urlencode(params).encode("utf-8")
    try:
        request = Request(
            HMIP_EXPORT_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/Table",
            },
        )
        with urlopen(request, timeout=60) as response:
            raw = response.read()
            # HMIP returns cp1252-encoded CSV
            return raw.decode("cp1252")
    except HTTPError as exc:
        print(f"  Warning: HTTP {exc.code} fetching RMS summary for {year}", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"  Warning: {exc} fetching RMS summary for {year}", file=sys.stderr)
        return ""


def parse_rms_summary_csv(csv_text: str) -> list[ZoneData]:
    """Parse the RMS Summary CSV into ZoneData records.

    CSV format (cp1252, no standard header — first 2 lines are title rows):
      Line 1: " — Rental Market Statistics Summary by Zone"
      Line 2: "October 2025 Row / Apartment Bedroom Type - Total"
      Line 3: ",Vacancy Rate (%),,Availability Rate (%),,Average Rent ($),,..."
      Line 4+: zone data rows

    Each data row has 13 comma-separated fields:
      zone_name, vacancy, quality, availability, quality, avg_rent, quality,
      median_rent, quality, pct_change, quality, units, (trailing comma)
    """
    zones: list[ZoneData] = []
    lines = csv_text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip header/title lines and notes
        if line.startswith(",") or line.startswith(" ") or line.startswith("\x97"):
            continue
        if any(kw in line.lower() for kw in ["notes", "source", "cmhc", "archived", "definitions"]):
            continue

        # Parse CSV-like format with possible quoted fields
        fields = _parse_csv_line(line)
        if len(fields) < 11:
            continue

        zone_name = fields[0].strip().strip('"')
        if not zone_name or zone_name.startswith("Toronto CMA"):
            continue

        zones.append(
            ZoneData(
                zone_name=zone_name,
                vacancy_rate=_optional_float(fields[1]),
                # fields[2] = quality code
                availability_rate=_optional_float(fields[3]),
                # fields[4] = quality code
                average_rent=_optional_float(fields[5]),
                # fields[6] = quality code
                median_rent=_optional_float(fields[7]),
                # fields[8] = quality code
                rent_change_pct=_optional_float(fields[9]),
                # fields[10] = quality code
                rental_universe=_optional_int(fields[11]) if len(fields) > 11 else None,
            )
        )

    return zones


def _parse_csv_line(line: str) -> list[str]:
    """Parse a CSV line handling quoted fields with commas."""
    fields: list[str] = []
    current = ""
    in_quotes = False
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            fields.append(current)
            current = ""
        else:
            current += char
    fields.append(current)
    return fields


# ---------------------------------------------------------------------------
# Aggregation: survey zones → municipality-level metrics
# ---------------------------------------------------------------------------


def aggregate_zones_to_municipalities(
    zones: list[ZoneData], year: int
) -> list[CmhcRow]:
    """Map and aggregate survey zone data to municipality-level CmhcRow records.

    For municipalities that span multiple zones (Toronto, Mississauga, Brampton):
    - Rates (vacancy, availability): weighted average by rental universe
    - Dollar amounts (rent): weighted average by rental universe
    - Counts (rental universe): simple sum

    For combined zones (Richmond Hill/Vaughan/King):
    - All constituent municipalities get the same zone-level values

    For single-municipality zones (Oakville, Markham, Caledon):
    - Direct assignment
    """
    # Collect zone data per geoid for aggregation
    geoid_zones: dict[str, list[ZoneData]] = {}
    unmatched: list[str] = []

    for zone in zones:
        geoids = ZONE_TO_GEOIDS.get(zone.zone_name)
        if geoids is None:
            unmatched.append(zone.zone_name)
            continue
        for geoid in geoids:
            geoid_zones.setdefault(geoid, []).append(zone)

    if unmatched:
        print(f"  Unmatched zones for {year}: {unmatched}", file=sys.stderr)

    rows: list[CmhcRow] = []
    for geoid, zone_list in sorted(geoid_zones.items()):
        if geoid in AGGREGATED_GEOIDS and len(zone_list) > 1:
            row = _aggregate_zones(geoid, year, zone_list)
        else:
            # Single zone or combined-zone: use the zone data directly
            z = zone_list[0]
            row = CmhcRow(
                geoid=geoid,
                year=year,
                vacancy_rate=z.vacancy_rate,
                average_rent_total=z.average_rent,
                availability_rate=z.availability_rate,
                rental_universe=z.rental_universe,
            )
        rows.append(row)

    return rows


def _aggregate_zones(geoid: str, year: int, zones: list[ZoneData]) -> CmhcRow:
    """Compute weighted averages across multiple zones for a single municipality."""
    total_units = 0
    weighted_vacancy = 0.0
    weighted_availability = 0.0
    weighted_rent = 0.0

    vacancy_units = 0
    availability_units = 0
    rent_units = 0

    for z in zones:
        units = z.rental_universe or 0
        total_units += units
        if z.vacancy_rate is not None and units > 0:
            weighted_vacancy += z.vacancy_rate * units
            vacancy_units += units
        if z.availability_rate is not None and units > 0:
            weighted_availability += z.availability_rate * units
            availability_units += units
        if z.average_rent is not None and units > 0:
            weighted_rent += z.average_rent * units
            rent_units += units

    return CmhcRow(
        geoid=geoid,
        year=year,
        vacancy_rate=round(weighted_vacancy / vacancy_units, 1) if vacancy_units > 0 else None,
        average_rent_total=round(weighted_rent / rent_units) if rent_units > 0 else None,
        availability_rate=(
            round(weighted_availability / availability_units, 1)
            if availability_units > 0
            else None
        ),
        rental_universe=total_units if total_units > 0 else None,
    )


# ---------------------------------------------------------------------------
# Seed file I/O
# ---------------------------------------------------------------------------


def load_geoids_from_seed() -> list[str]:
    demo_seed_path = PROJECT_ROOT / "app" / "data" / "demo_seed.json"
    seed = json.loads(demo_seed_path.read_text(encoding="utf-8"))
    return sorted(item["geoid"] for item in seed["geographies"])


def write_seed(metrics: list[CmhcRow], years: list[int]) -> int:
    seed = {
        "metadata": {
            "source": "cmhc_hmip_rental_market_survey",
            "years": sorted(years),
            "fetched_at": datetime.now(UTC).isoformat(),
            "notes": [
                "Rental Market Survey data from CMHC Housing Market Information Portal.",
                "Data fetched from HMIP ExportTable POST endpoint (RMS Summary table 2.1.31.3).",
                "Survey zones aggregated to municipality level using unit-weighted averages.",
                "Combined zones (e.g. Richmond Hill/Vaughan/King) share the same values.",
                "Starts & Completions data series archived by CMHC — fields set to null.",
                "Bedroom-specific rents and turnover rate not available from summary endpoint.",
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


# ---------------------------------------------------------------------------
# Update seed: fetch from HMIP, parse, aggregate, write
# ---------------------------------------------------------------------------


def update_seed(years: list[int] | None = None) -> int:
    """Fetch RMS data from HMIP for the given years and write the seed file."""
    if years is None:
        years = list(range(DEFAULT_START_YEAR, DEFAULT_END_YEAR + 1))

    all_metrics: list[CmhcRow] = []
    known_geoids = set(load_geoids_from_seed())

    for year in years:
        print(f"  Fetching RMS Summary for {year}...")
        csv_text = fetch_rms_summary_csv(year)
        if not csv_text:
            print(f"  Skipping {year} — no data returned.")
            continue

        zones = parse_rms_summary_csv(csv_text)
        print(f"    Parsed {len(zones)} survey zones.")

        rows = aggregate_zones_to_municipalities(zones, year)
        # Filter to only known geoids
        rows = [r for r in rows if r.geoid in known_geoids]
        print(f"    Mapped to {len(rows)} municipalities.")

        all_metrics.extend(rows)
        time.sleep(REQUEST_DELAY)

    if not all_metrics:
        print("No data fetched. Seed file not updated.")
        return 0

    count = write_seed(all_metrics, years)
    print(f"\nWrote {count} metric rows to {SEED_PATH}")
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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


def print_urls() -> None:
    print("CMHC HMIP Export URLs (reference only — use POST for actual fetching):")
    print(f"  RMS Summary (zone): {build_export_url(TABLE_RMS_SUMMARY, TORONTO_CMA_GEO_ID, GEO_TYPE_CMA, GEO_TYPE_ZONE)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch CMHC Rental Market Survey data from HMIP portal."
    )
    parser.add_argument(
        "--update-seed",
        "--fetch-all",
        action="store_true",
        help="Fetch from HMIP and write seed file.",
    )
    parser.add_argument(
        "--from-seed",
        action="store_true",
        help="Load packaged seed into database.",
    )
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print HMIP endpoint URLs.",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Fetch a specific year only (default: 2018-2025).",
    )
    args = parser.parse_args()

    if args.print_url:
        print_urls()
        return

    if args.from_seed:
        count = load_from_seed()
        print(f"Loaded {count} CMHC metric rows from seed.")
        return

    if args.update_seed:
        print("Fetching CMHC Rental Market Survey data from HMIP portal...")
        years = [args.year] if args.year else None
        count = update_seed(years)
        if count:
            print(f"Done. {count} rows written to seed file.")
        return

    parser.error("--update-seed, --from-seed, or --print-url is required.")


if __name__ == "__main__":
    main()
