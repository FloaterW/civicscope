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
GEO_TYPE_CSD = 4  # Census subdivision (municipality-level Scss queries)
GEO_TYPE_ZONE = 5  # Survey zone breakdown (used by RMS)

# The RMS Summary table (2.1.31.3) returns vacancy rate, availability rate,
# average rent, median rent, rent % change, and rental universe in one CSV.
TABLE_RMS_SUMMARY = "2.1.31.3"

# Scss (Starts & Completions Survey) tables, queried per CSD
TABLE_SCSS_STARTS = "1.1.1"  # Housing starts by dwelling type
TABLE_SCSS_COMPLETIONS = "1.2.2"  # Historical completions by dwelling type
TABLE_SCSS_UNDER_CONSTRUCTION = "1.2.3"  # Historical under-construction inventory
TABLE_SCSS_UNABSORBED = "1.2.4"  # Historical completed-and-unabsorbed inventory

# RMS survey month, the Rental Market Survey is conducted in October each year.
RMS_SURVEY_MONTH = 10

SEED_PATH = PROJECT_ROOT / "app" / "data" / "cmhc_seed.json"

REQUEST_DELAY = 0.3  # seconds between requests to be polite

# All 25 GTA municipalities, used for per-CSD Scss queries
ALL_GTA_GEOIDS: dict[str, str] = {
    "3518001": "Pickering",
    "3518005": "Ajax",
    "3518009": "Whitby",
    "3518013": "Oshawa",
    "3518017": "Clarington",
    "3518020": "Scugog",
    "3518029": "Uxbridge",
    "3518039": "Brock",
    "3519028": "Vaughan",
    "3519036": "Markham",
    "3519038": "Richmond Hill",
    "3519044": "Whitchurch-Stouffville",
    "3519046": "Aurora",
    "3519048": "Newmarket",
    "3519049": "King",
    "3519054": "East Gwillimbury",
    "3519070": "Georgina",
    "3520005": "Toronto",
    "3521005": "Mississauga",
    "3521010": "Brampton",
    "3521024": "Caledon",
    "3524001": "Oakville",
    "3524002": "Burlington",
    "3524009": "Milton",
    "3524015": "Halton Hills",
}

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
    # City of Toronto, 17 internal survey zones
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
    # Mississauga, 3 zones
    "Mississauga (South)": ["3521005"],
    "Mississauga (Northwest)": ["3521005"],
    "Mississauga (Northeast)": ["3521005"],
    # Brampton, 2 zones
    "Brampton (West)": ["3521010"],
    "Brampton (East)": ["3521010"],
    # Single-municipality zones
    "Oakville": ["3524001"],
    "Caledon": ["3521024"],
    "Markham": ["3519036"],
    # Combined zones, data shared across constituent municipalities
    "Richmond Hill/Vaughan/King": ["3519038", "3519028", "3519049"],
    "Aurora, Newmkt, Whit-St.": ["3519046", "3519048", "3519044"],
    "Pickering/Ajax/Uxbridge": ["3518001", "3518005", "3518029"],
    "Milton/Halton Hills": ["3524009", "3524015"],
    # These zones are outside our GTA-25 municipality set, skip
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
    unabsorbed_units: int | None = None
    rms_surveyed: bool = False


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
    average_rent_bachelor: float | None = None
    average_rent_1br: float | None = None
    average_rent_2br: float | None = None
    average_rent_3br_plus: float | None = None


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


BEDROOM_TYPES: dict[str, str] = {
    "Studio": "average_rent_bachelor",
    "1 Bedroom": "average_rent_1br",
    "2 Bedroom": "average_rent_2br",
    "3 Bedroom +": "average_rent_3br_plus",
}


def fetch_rms_bedroom_csv(year: int, bedroom_type: str) -> str:
    """Fetch RMS Summary CSV filtered by bedroom type."""
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
        "AppliedFilters[0].Key": "dwelling_type_desc_en",
        "AppliedFilters[0].Value": "Row / Apartment",
        "AppliedFilters[1].Key": "bedroom_count_type_desc_en",
        "AppliedFilters[1].Value": bedroom_type,
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
            return response.read().decode("cp1252")
    except Exception as exc:
        print(f"  Warning: {exc} fetching RMS {bedroom_type} for {year}", file=sys.stderr)
        return ""


def fetch_bedroom_rents_for_year(year: int) -> dict[str, dict[str, float | None]]:
    """Fetch average rent by bedroom type for all zones in a given year.

    Returns: {zone_name: {average_rent_bachelor: ..., average_rent_1br: ..., ...}}
    """
    result: dict[str, dict[str, float | None]] = {}

    for bedroom_label, field_name in BEDROOM_TYPES.items():
        csv_text = fetch_rms_bedroom_csv(year, bedroom_label)
        if not csv_text:
            continue
        zones = parse_rms_summary_csv(csv_text)
        for zone in zones:
            result.setdefault(zone.zone_name, {})[field_name] = zone.average_rent
        time.sleep(REQUEST_DELAY)

    return result


def merge_bedroom_rents(
    zones: list[ZoneData], bedroom_rents: dict[str, dict[str, float | None]]
) -> None:
    """Merge bedroom-specific rents into ZoneData objects in-place."""
    for zone in zones:
        rents = bedroom_rents.get(zone.zone_name, {})
        zone.average_rent_bachelor = rents.get("average_rent_bachelor")
        zone.average_rent_1br = rents.get("average_rent_1br")
        zone.average_rent_2br = rents.get("average_rent_2br")
        zone.average_rent_3br_plus = rents.get("average_rent_3br_plus")


# ---------------------------------------------------------------------------
# Scss (Starts & Completions Survey), per-CSD queries
# ---------------------------------------------------------------------------

# Month abbreviations used in HMIP historical CSV rows (e.g. "Jan 2024", "Dec 2025")
_MONTH_ABBREVS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def fetch_scss_csv(
    geoid: str,
    table_id: str,
    year: int,
    month: int = 12,
    ytd: bool = True,
) -> str:
    """Fetch an Scss CSV from HMIP for one CSD.

    For starts (table 1.1.1): use Ytd=True, Month=12 for annual totals.
    For completions (1.2.2) / under construction (1.2.3): use Ytd=False,
    Month=1 to get historical monthly rows from Jan of that year forward.
    """
    params = {
        "TableId": table_id,
        "GeographyId": geoid,
        "GeographyTypeId": str(GEO_TYPE_CSD),
        "DisplayAs": "Table",
        "Ytd": str(ytd),
        "Survey": "Scss",
        "ForTimePeriod.Year": str(year),
        "ForTimePeriod.Month": str(month),
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
            return response.read().decode("cp1252")
    except HTTPError as exc:
        print(
            f"  Warning: HTTP {exc.code} fetching Scss {table_id} for {geoid}",
            file=sys.stderr,
        )
        return ""
    except Exception as exc:
        print(
            f"  Warning: {exc} fetching Scss {table_id} for {geoid}",
            file=sys.stderr,
        )
        return ""


@dataclass
class ScssStartsRow:
    """Annual housing starts for a single CSD and year."""

    single: int | None = None
    semi: int | None = None
    row: int | None = None
    apartment: int | None = None
    total: int | None = None


def parse_scss_starts_csv(csv_text: str) -> ScssStartsRow | None:
    """Parse annual starts CSV (table 1.1.1 with Ytd=True).

    Format:
      Line 1: " — Starts by Dwelling Type"
      Line 2: "January - December 2025 Intended Markets - All"
      Line 3: "Single,Semi-Detached,Row,Apartment,All,"
      Line 4: "230,0,771,\"1,004\",\"2,005\","
    """
    if not csv_text:
        return None

    for line in csv_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith(" ") or line.startswith(","):
            continue
        if any(kw in line.lower() for kw in ["source", "single", "starts"]):
            continue
        # This is the data row
        fields = _parse_csv_line(line)
        if len(fields) < 5:
            continue
        return ScssStartsRow(
            single=_optional_int(fields[0]),
            semi=_optional_int(fields[1]),
            row=_optional_int(fields[2]),
            apartment=_optional_int(fields[3]),
            total=_optional_int(fields[4]),
        )
    return None


@dataclass
class ScssMonthlyRow:
    """One month of historical completions or under-construction data."""

    year: int
    month: int
    total: int | None = None


def parse_scss_historical_csv(csv_text: str) -> list[ScssMonthlyRow]:
    """Parse historical monthly CSV (tables 1.2.2 / 1.2.3).

    Format:
      Line 1: " — Historical Completions by Dwelling Type"
      Line 2: "January 2024 to March 2026 Intended Markets - All"
      Line 3: ",Single,Semi-Detached,Row,Apartment,All,"
      Line 4+: "Jan 2024,15,0,138,0,153,"  or  "Dec 2024,14,0,13,0,27,"
    """
    rows: list[ScssMonthlyRow] = []
    if not csv_text:
        return rows

    for line in csv_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith(" ") or line.startswith(","):
            continue
        if any(kw in line.lower() for kw in ["source", "single"]):
            continue

        fields = _parse_csv_line(line)
        if len(fields) < 6:
            continue

        # First field is "Mon YYYY" (e.g. "Jan 2024", "Dec 2025")
        date_parts = fields[0].strip().split()
        if len(date_parts) != 2:
            continue
        month_num = _MONTH_ABBREVS.get(date_parts[0])
        if month_num is None:
            continue
        try:
            row_year = int(date_parts[1])
        except ValueError:
            continue

        # "All" (total) is the last real column, field index 5
        rows.append(
            ScssMonthlyRow(
                year=row_year,
                month=month_num,
                total=_optional_int(fields[5]),
            )
        )

    return rows


def _sum_completions_for_year(monthly_rows: list[ScssMonthlyRow], year: int) -> int | None:
    """Sum monthly completions for a calendar year. Returns None if no data."""
    yearly = [r.total for r in monthly_rows if r.year == year and r.total is not None]
    return sum(yearly) if yearly else None


def _dec_snapshot_for_year(monthly_rows: list[ScssMonthlyRow], year: int) -> int | None:
    """Get the December snapshot value for under-construction inventory."""
    for r in monthly_rows:
        if r.year == year and r.month == 12:
            return r.total
    return None


def fetch_scss_for_municipality(
    geoid: str,
    years: list[int],
) -> dict[int, dict[str, Any]]:
    """Fetch all Scss data for one municipality across all years.

    Returns: {year: {housing_starts_total, ..single, ..semi, ..row, ..apartment,
                     housing_completions, units_under_construction}}
    """
    result: dict[int, dict[str, Any]] = {}

    # 1. Fetch starts, one call per year (Ytd=True gives annual total)
    for year in years:
        csv_text = fetch_scss_csv(geoid, TABLE_SCSS_STARTS, year, month=12, ytd=True)
        starts = parse_scss_starts_csv(csv_text)
        result[year] = {
            "housing_starts_total": starts.total if starts else None,
            "housing_starts_single": starts.single if starts else None,
            "housing_starts_semi": starts.semi if starts else None,
            "housing_starts_row": starts.row if starts else None,
            "housing_starts_apartment": starts.apartment if starts else None,
            "housing_completions": None,
            "units_under_construction": None,
            "unabsorbed_units": None,
        }
        time.sleep(REQUEST_DELAY)

    # 2. Fetch completions, one call from start year, returns all months
    csv_text = fetch_scss_csv(
        geoid, TABLE_SCSS_COMPLETIONS, years[0], month=1, ytd=False
    )
    comp_monthly = parse_scss_historical_csv(csv_text)
    for year in years:
        result[year]["housing_completions"] = _sum_completions_for_year(comp_monthly, year)
    time.sleep(REQUEST_DELAY)

    # 3. Fetch under construction, one call from start year, take Dec snapshot
    csv_text = fetch_scss_csv(
        geoid, TABLE_SCSS_UNDER_CONSTRUCTION, years[0], month=1, ytd=False
    )
    uc_monthly = parse_scss_historical_csv(csv_text)
    for year in years:
        result[year]["units_under_construction"] = _dec_snapshot_for_year(uc_monthly, year)
    time.sleep(REQUEST_DELAY)

    # 4. Fetch unabsorbed inventory, one call from start year, take Dec snapshot
    csv_text = fetch_scss_csv(
        geoid, TABLE_SCSS_UNABSORBED, years[0], month=1, ytd=False
    )
    ua_monthly = parse_scss_historical_csv(csv_text)
    for year in years:
        result[year]["unabsorbed_units"] = _dec_snapshot_for_year(ua_monthly, year)
    time.sleep(REQUEST_DELAY)

    return result


def fetch_scss_all_municipalities(
    years: list[int],
) -> dict[str, dict[int, dict[str, Any]]]:
    """Fetch Scss data for all 25 GTA municipalities.

    Returns: {geoid: {year: {starts, completions, under_construction fields}}}
    """
    all_scss: dict[str, dict[int, dict[str, Any]]] = {}
    total = len(ALL_GTA_GEOIDS)

    for idx, (geoid, name) in enumerate(sorted(ALL_GTA_GEOIDS.items()), 1):
        print(f"  [{idx}/{total}] Fetching Scss for {name} ({geoid})...")
        try:
            scss_data = fetch_scss_for_municipality(geoid, years)
            all_scss[geoid] = scss_data
            # Log a sample for verification
            latest = years[-1]
            starts = scss_data.get(latest, {}).get("housing_starts_total")
            print(f"    {latest} starts: {starts}")
        except Exception as exc:
            print(f"    Warning: {exc} — skipping", file=sys.stderr)

    return all_scss


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
                average_rent_bachelor=z.average_rent_bachelor,
                average_rent_1br=z.average_rent_1br,
                average_rent_2br=z.average_rent_2br,
                average_rent_3br_plus=z.average_rent_3br_plus,
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

    bedroom_accum: dict[str, tuple[float, int]] = {
        "average_rent_bachelor": (0.0, 0),
        "average_rent_1br": (0.0, 0),
        "average_rent_2br": (0.0, 0),
        "average_rent_3br_plus": (0.0, 0),
    }

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
        for field in bedroom_accum:
            val = getattr(z, field, None)
            if val is not None and units > 0:
                w, u = bedroom_accum[field]
                bedroom_accum[field] = (w + val * units, u + units)

    def _weighted_rent(field: str) -> float | None:
        w, u = bedroom_accum[field]
        return round(w / u) if u > 0 else None

    return CmhcRow(
        geoid=geoid,
        year=year,
        vacancy_rate=round(weighted_vacancy / vacancy_units, 1) if vacancy_units > 0 else None,
        average_rent_total=round(weighted_rent / rent_units) if rent_units > 0 else None,
        average_rent_bachelor=_weighted_rent("average_rent_bachelor"),
        average_rent_1br=_weighted_rent("average_rent_1br"),
        average_rent_2br=_weighted_rent("average_rent_2br"),
        average_rent_3br_plus=_weighted_rent("average_rent_3br_plus"),
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
    return sorted(
        item["geoid"]
        for item in seed["geographies"]
        if item.get("type") == "municipality"
    )


def validate_seed_coverage(
    metrics: list[CmhcRow],
    expected_geoids: set[str],
    years: list[int],
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Fail closed when an HMIP refresh is missing expected slices or fields."""
    expected_pairs = {(geoid, year) for geoid in expected_geoids for year in years}
    by_pair = {(row.geoid, row.year): row for row in metrics}
    missing_pairs = expected_pairs - set(by_pair)
    missing_scss = {
        pair
        for pair in expected_pairs & set(by_pair)
        if by_pair[pair].housing_starts_total is None
        and by_pair[pair].housing_completions is None
    }
    scss_field_coverage = {
        field: (
            100
            * sum(getattr(by_pair[pair], field) is not None for pair in expected_pairs & set(by_pair))
            / len(expected_pairs)
            if expected_pairs
            else 0.0
        )
        for field in ("housing_starts_total", "housing_completions")
    }
    rms_geoids = {
        geoid
        for zone_geoids in ZONE_TO_GEOIDS.values()
        for geoid in zone_geoids
        if geoid in expected_geoids
    }
    missing_rms = {
        pair
        for pair in {(geoid, year) for geoid in rms_geoids for year in years}
        if pair not in by_pair
        or all(
            getattr(by_pair[pair], field) is None
            for field in ("vacancy_rate", "average_rent_total", "rental_universe")
        )
    }
    duplicate_count = len(metrics) - len(by_pair)
    report = {
        "expected_rows": len(expected_pairs),
        "actual_rows": len(by_pair),
        "missing_pairs": len(missing_pairs),
        "missing_scss_pairs": len(missing_scss),
        "scss_field_coverage_pct": {
            field: round(value, 1) for field, value in scss_field_coverage.items()
        },
        "missing_rms_pairs": len(missing_rms),
        "duplicate_rows": duplicate_count,
    }
    problems = []
    if missing_pairs:
        problems.append(f"{len(missing_pairs)} missing municipality/year rows")
    if missing_scss:
        problems.append(f"{len(missing_scss)} rows missing both starts and completions")
    for field, coverage in scss_field_coverage.items():
        if coverage < 90.0:
            problems.append(f"{field} coverage {coverage:.1f}% is below 90.0%")
    if missing_rms:
        problems.append(f"{len(missing_rms)} surveyed rows missing RMS values")
    if duplicate_count:
        problems.append(f"{duplicate_count} duplicate rows")
    if problems and not allow_partial:
        raise ValueError(
            "CMHC refresh failed coverage validation: " + "; ".join(problems)
            + ". Re-run with --allow-partial only for diagnostic output."
        )
    report["partial"] = bool(problems)
    return report


def write_seed(
    metrics: list[CmhcRow],
    years: list[int],
    coverage: dict[str, Any] | None = None,
    output_path: Path = SEED_PATH,
) -> int:
    seed = {
        "metadata": {
            "source": "cmhc_hmip",
            "years": sorted(years),
            "fetched_at": datetime.now(UTC).isoformat(),
            "coverage": coverage or {},
            "notes": [
                "Rental Market Survey (RMS) and Starts & Completions Survey (Scss) data",
                "from CMHC Housing Market Information Portal (HMIP ExportTable endpoint).",
                "RMS: Table 2.1.31.3 at survey-zone level, aggregated to municipalities.",
                "Scss: Tables 1.1.1, 1.2.2, 1.2.3, 1.2.4 queried per CSD (municipality).",
                "Housing starts are annual totals (Jan-Dec YTD).",
                "Completions are annual sums of monthly completions.",
                "Under construction is December point-in-time inventory.",
                "Unabsorbed units is December point-in-time count of completed but unsold/unrented units.",
                "Municipalities without RMS zone coverage still get Scss data.",
            ],
        },
        "metrics": [asdict(m) for m in metrics],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)
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
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Update seed: fetch from HMIP, parse, aggregate, write
# ---------------------------------------------------------------------------


def update_seed(
    years: list[int] | None = None,
    *,
    allow_partial: bool = False,
    output_path: Path = SEED_PATH,
) -> int:
    """Fetch RMS + Scss data from HMIP for the given years and write the seed file."""
    if years is None:
        years = list(range(DEFAULT_START_YEAR, DEFAULT_END_YEAR + 1))

    known_geoids = set(load_geoids_from_seed())

    # ---- Phase 1: RMS (rental market data at survey-zone level) ----
    print("\n=== Phase 1: Rental Market Survey (RMS) ===")
    rms_by_key: dict[tuple[str, int], CmhcRow] = {}

    for year in years:
        print(f"  Fetching RMS Summary for {year}...")
        csv_text = fetch_rms_summary_csv(year)
        if not csv_text:
            print(f"  Skipping {year} — no data returned.")
            continue

        zones = parse_rms_summary_csv(csv_text)
        print(f"    Parsed {len(zones)} survey zones.")

        print(f"    Fetching bedroom-specific rents for {year}...")
        bedroom_rents = fetch_bedroom_rents_for_year(year)
        merge_bedroom_rents(zones, bedroom_rents)
        print(f"    Merged bedroom rents for {len(bedroom_rents)} zones.")

        rows = aggregate_zones_to_municipalities(zones, year)
        rows = [r for r in rows if r.geoid in known_geoids]
        print(f"    Mapped to {len(rows)} municipalities.")

        for row in rows:
            rms_by_key[(row.geoid, row.year)] = row
        time.sleep(REQUEST_DELAY)

    # ---- Phase 2: Scss (starts & completions per CSD) ----
    print("\n=== Phase 2: Starts & Completions Survey (Scss) ===")
    all_scss = fetch_scss_all_municipalities(years)

    # ---- Phase 3: Merge RMS + Scss into unified CmhcRow list ----
    print("\n=== Phase 3: Merging RMS + Scss data ===")
    all_metrics: list[CmhcRow] = []

    # Build the full set of (geoid, year) pairs, union of RMS and Scss coverage
    all_keys: set[tuple[str, int]] = set(rms_by_key.keys())
    for geoid, year_data in all_scss.items():
        if geoid in known_geoids:
            for year in year_data:
                all_keys.add((geoid, year))

    # Build set of geoids that have any RMS zone mapping
    rms_covered_geoids = {gid for zone_geoids in ZONE_TO_GEOIDS.values() for gid in zone_geoids}

    for geoid, year in sorted(all_keys):
        # Start with RMS data if available, otherwise create empty row
        row = rms_by_key.get((geoid, year))
        if row is None:
            row = CmhcRow(geoid=geoid, year=year)

        row.rms_surveyed = geoid in rms_covered_geoids

        # Overlay Scss fields
        scss_year_data = all_scss.get(geoid, {}).get(year)
        if scss_year_data:
            row.housing_starts_total = scss_year_data.get("housing_starts_total")
            row.housing_starts_single = scss_year_data.get("housing_starts_single")
            row.housing_starts_semi = scss_year_data.get("housing_starts_semi")
            row.housing_starts_row = scss_year_data.get("housing_starts_row")
            row.housing_starts_apartment = scss_year_data.get("housing_starts_apartment")
            row.housing_completions = scss_year_data.get("housing_completions")
            row.units_under_construction = scss_year_data.get("units_under_construction")
            row.unabsorbed_units = scss_year_data.get("unabsorbed_units")

        all_metrics.append(row)

    if not all_metrics:
        print("No data fetched. Seed file not updated.")
        return 0

    coverage = validate_seed_coverage(
        all_metrics, known_geoids, years, allow_partial=allow_partial
    )
    if coverage["partial"]:
        print(f"WARNING: writing partial CMHC data: {coverage}", file=sys.stderr)
    count = write_seed(all_metrics, years, coverage, output_path)
    print(f"\nWrote {count} metric rows to {output_path}")

    # Quick verification: check that starts vary across municipalities
    sample_year = years[-1]
    starts_vals = {
        m.geoid: m.housing_starts_total
        for m in all_metrics
        if m.year == sample_year and m.housing_starts_total is not None
    }
    unique_starts = len(set(starts_vals.values()))
    print(f"Verification: {unique_starts} unique housing_starts_total values for {sample_year}")
    if unique_starts <= 1 and len(starts_vals) > 1:
        print("  WARNING: All municipalities have the same value — Scss fetch may have failed!")

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
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow diagnostic output that fails coverage validation; requires noncanonical --output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output seed path (default: canonical app/data/cmhc_seed.json).",
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
        output_path = args.output or SEED_PATH
        if args.allow_partial and (
            args.output is None or output_path.resolve() == SEED_PATH.resolve()
        ):
            parser.error(
                "--allow-partial requires an explicit noncanonical --output path; "
                "partial diagnostics cannot replace the packaged seed."
            )
        print("Fetching CMHC Rental Market Survey data from HMIP portal...")
        years = [args.year] if args.year else None
        count = update_seed(
            years,
            allow_partial=args.allow_partial,
            output_path=output_path,
        )
        if count:
            print(f"Done. {count} rows written to seed file.")
        return

    parser.error("--update-seed, --from-seed, or --print-url is required.")


if __name__ == "__main__":
    main()
