"""Fetch official 2021 Census Profile metrics for GTA census tracts.

Uses the Statistics Canada SDMX Census Profile API (DF_CT dataflow).
Census tract DGUIDs use prefix 2021S0507 with dots replaced by underscores.

Usage:
    # Generate normalized CSV for all GTA tracts
    python etl/load_tract_census.py --generate-csv

    # Load the generated CSV into the database
    python etl/load_census.py --csv data/statcan_ct_metrics.csv

    # Update seed file with official tract metrics
    python etl/load_tract_census.py --update-seed
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SDMX_BASE_URL = (
    "https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/data/STC_CP,DF_CT"
)

# Same characteristic IDs as load_census.py
CHARACTERISTIC_IDS = {
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
CHARACTERISTIC_TO_FIELD = {v: k for k, v in CHARACTERISTIC_IDS.items()}

BATCH_SIZE = 40  # DGUIDs per API request to avoid URL length limits
MIN_COVERAGE_PCT = 99.0  # fail-closed: require nearly all requested tracts
FIELD_MIN_COVERAGE_PCT = {
    "population": 99.0,
    "previous_population": 99.0,
    "median_income": 99.0,
    "median_rent": 98.0,
    "renter_households": 99.0,
    "rent_burden_pct": 95.0,
}


def ctuid_to_dguid(ctuid: str) -> str:
    """Convert CTUID (e.g. 5350001.00) to SDMX DGUID (e.g. 2021S05075350001_00)."""
    return f"2021S0507{ctuid.replace('.', '_')}"


def dguid_to_ctuid(dguid: str) -> str:
    """Convert SDMX DGUID back to CTUID."""
    prefix = "2021S0507"
    if not dguid.startswith(prefix):
        raise ValueError(f"Unexpected CT DGUID prefix: {dguid}")
    return dguid.removeprefix(prefix).replace("_", ".")


@dataclass(frozen=True)
class TractMetric:
    geoid: str
    year: int
    population: int | None
    previous_population: int | None
    median_income: float | None
    median_rent: float | None
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


def load_tract_geoids(seed_path: Path | None = None) -> list[str]:
    """Load GTA census tract CTUIDs from the seed file."""
    path = seed_path or PROJECT_ROOT / "app" / "data" / "demo_seed.json"
    seed = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        item["geoid"]
        for item in seed["geographies"]
        if item.get("type") == "census_tract"
    )


def fetch_batch(dguids: list[str]) -> list[TractMetric]:
    """Fetch Census Profile metrics for a batch of tract DGUIDs."""
    dguid_str = "+".join(dguids)
    char_str = "+".join(CHARACTERISTIC_IDS.values())
    url = f"{SDMX_BASE_URL}/A5.{dguid_str}.1.{char_str}.1?format=csv&detail=dataonly"

    try:
        with urlopen(Request(url), timeout=60) as response:
            text = response.read().decode("utf-8-sig")
    except HTTPError as exc:
        print(f"  Warning: HTTP {exc.code} for batch of {len(dguids)} tracts", file=sys.stderr)
        return []
    except Exception as exc:
        print(f"  Warning: {exc} for batch of {len(dguids)} tracts", file=sys.stderr)
        return []

    # Parse SDMX CSV into grouped metrics
    grouped: dict[str, dict[str, Any]] = {}
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        char_id = str(row.get("CHARACTERISTIC", "")).strip()
        field = CHARACTERISTIC_TO_FIELD.get(char_id)
        if field is None:
            continue
        dguid = str(row["REF_AREA"]).strip()
        ctuid = dguid_to_ctuid(dguid)
        grouped.setdefault(ctuid, {"geoid": ctuid})
        grouped[ctuid][field] = row.get("OBS_VALUE")

    results = []
    for ctuid, data in grouped.items():
        results.append(
            TractMetric(
                geoid=ctuid,
                year=2021,
                population=_optional_int(data.get("population")),
                previous_population=_optional_int(data.get("previous_population")),
                median_income=_optional_float(data.get("median_income")),
                median_rent=_optional_float(data.get("median_rent")),
                renter_households=_optional_int(data.get("renter_households")),
                rent_burden_pct=_optional_float(data.get("rent_burden_pct")),
                dwellings_total=_optional_int(data.get("dwellings_total")),
                dwellings_single_detached=_optional_int(data.get("dwellings_single_detached")),
                dwellings_semi_detached=_optional_int(data.get("dwellings_semi_detached")),
                dwellings_row_house=_optional_int(data.get("dwellings_row_house")),
                dwellings_apt_duplex=_optional_int(data.get("dwellings_apt_duplex")),
                dwellings_apt_low_rise=_optional_int(data.get("dwellings_apt_low_rise")),
                dwellings_apt_high_rise=_optional_int(data.get("dwellings_apt_high_rise")),
                owner_households=_optional_int(data.get("owner_households")),
            )
        )
    return results


def fetch_all_tract_metrics(geoids: list[str]) -> list[TractMetric]:
    """Fetch Census Profile metrics for all GTA tracts in batches."""
    dguids = [ctuid_to_dguid(g) for g in geoids]
    all_metrics: list[TractMetric] = []
    total_batches = (len(dguids) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(dguids), BATCH_SIZE):
        batch = dguids[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Fetching batch {batch_num}/{total_batches} ({len(batch)} tracts)...")
        metrics = fetch_batch(batch)
        all_metrics.extend(metrics)
        if i + BATCH_SIZE < len(dguids):
            time.sleep(0.5)  # Rate limit courtesy

    return sorted(all_metrics, key=lambda m: m.geoid)


def validate_tract_coverage(
    metrics: list[TractMetric],
    geoids: list[str],
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Validate row and field-level coverage before replacing official data."""
    unique_geoids = {metric.geoid for metric in metrics}
    row_coverage = 100 * len(unique_geoids) / len(geoids) if geoids else 0.0
    duplicate_count = len(metrics) - len(unique_geoids)
    field_coverage = {
        field: (
            100 * sum(getattr(metric, field) is not None for metric in metrics) / len(metrics)
            if metrics
            else 0.0
        )
        for field in FIELD_MIN_COVERAGE_PCT
    }
    problems = []
    if row_coverage < MIN_COVERAGE_PCT:
        problems.append(
            f"row coverage {row_coverage:.1f}% is below {MIN_COVERAGE_PCT:.1f}%"
        )
    if duplicate_count:
        problems.append(f"{duplicate_count} duplicate tract rows")
    for field, minimum in FIELD_MIN_COVERAGE_PCT.items():
        if field_coverage[field] < minimum:
            problems.append(
                f"{field} coverage {field_coverage[field]:.1f}% is below {minimum:.1f}%"
            )
    if problems and not allow_partial:
        raise ValueError("; ".join(problems))
    return {
        "row_coverage_pct": round(row_coverage, 1),
        "field_coverage_pct": {k: round(v, 1) for k, v in field_coverage.items()},
        "duplicate_rows": duplicate_count,
        "partial": bool(problems),
    }


def write_csv(metrics: list[TractMetric], output_path: Path) -> None:
    """Write normalized CSV compatible with load_census.py --csv."""
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "geoid", "year", "median_income", "median_rent",
            "population", "previous_population", "renter_households", "rent_burden_pct",
            "dwellings_total", "dwellings_single_detached", "dwellings_semi_detached",
            "dwellings_row_house", "dwellings_apt_duplex", "dwellings_apt_low_rise",
            "dwellings_apt_high_rise", "owner_households",
        ])
        for m in metrics:
            writer.writerow([
                m.geoid, m.year,
                m.median_income if m.median_income is not None else "",
                m.median_rent if m.median_rent is not None else "",
                m.population if m.population is not None else "",
                m.previous_population if m.previous_population is not None else "",
                m.renter_households if m.renter_households is not None else "",
                m.rent_burden_pct if m.rent_burden_pct is not None else "",
                m.dwellings_total if m.dwellings_total is not None else "",
                m.dwellings_single_detached if m.dwellings_single_detached is not None else "",
                m.dwellings_semi_detached if m.dwellings_semi_detached is not None else "",
                m.dwellings_row_house if m.dwellings_row_house is not None else "",
                m.dwellings_apt_duplex if m.dwellings_apt_duplex is not None else "",
                m.dwellings_apt_low_rise if m.dwellings_apt_low_rise is not None else "",
                m.dwellings_apt_high_rise if m.dwellings_apt_high_rise is not None else "",
                m.owner_households if m.owner_households is not None else "",
            ])
    temporary_path.replace(output_path)


def update_seed_with_official_metrics(
    seed_path: Path, metrics: list[TractMetric]
) -> int:
    """Replace estimated tract metrics in the seed file with official values."""
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    by_geoid = {m.geoid: m for m in metrics}
    updated = 0

    for item in seed["geographies"]:
        if item.get("type") != "census_tract":
            continue
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

    # Update geometry source description for tracts with official metrics
    for item in seed["geographies"]:
        if item.get("type") != "census_tract":
            continue
        if item["geoid"] in by_geoid:
            item["geometry_source"] = (
                "Statistics Canada 2021 cartographic census tract boundary; "
                "filtered to GTA municipalities by tract centroid. "
                "Metrics are official 2021 Census Profile values."
            )

    # Update metadata
    seed["metadata"]["notes"] = [
        "Municipal geometries are Statistics Canada 2021 cartographic census subdivision boundaries.",
        "Municipal metrics are loaded from official Statistics Canada 2021 Census Profile characteristics.",
        "Census tract geometries are official Statistics Canada 2021 cartographic tract boundaries "
        "filtered by centroid to the current GTA municipalities.",
        "Census tract metrics are official Statistics Canada 2021 Census Profile values "
        "fetched via the SDMX DF_CT dataflow.",
    ]

    temporary_path = seed_path.with_suffix(f"{seed_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(seed, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(seed_path)
    return updated


TRACT_METRIC_FIELDS = (
    "median_income",
    "median_rent",
    "population",
    "previous_population",
    "renter_households",
    "rent_burden_pct",
)
_INT_FIELDS = {"population", "previous_population", "renter_households"}


def apply_csv_metrics_to_seed(seed: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    """Replace census-tract metrics in ``seed`` with values from CSV ``rows``.

    The statcan_ct_metrics.csv is the canonical official source.  Values are
    copied verbatim and suppressed/blank values are preserved as ``None`` so
    that downstream provenance can distinguish official from estimated and
    unavailable.  No estimation is performed here.  Returns the number of
    census tracts updated.
    """
    by_geoid = {str(row["geoid"]).strip(): row for row in rows if row.get("geoid")}
    updated = 0
    for item in seed["geographies"]:
        if item.get("type") != "census_tract":
            continue
        row = by_geoid.get(item["geoid"])
        if row is None:
            continue
        metric: dict[str, Any] = {
            "year": _optional_int(row.get("year")) or 2021,
        }
        for field in TRACT_METRIC_FIELDS:
            raw = row.get(field)
            metric[field] = _optional_int(raw) if field in _INT_FIELDS else _optional_float(raw)
        item["metrics"] = [metric]
        updated += 1
    return updated


def sync_seed_from_csv(seed_path: Path, csv_path: Path) -> int:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    updated = apply_csv_metrics_to_seed(seed, rows)
    seed["metadata"]["source"] = "statistics_canada_2021_census_profile_csd_and_ct_seed"
    seed["metadata"]["notes"] = [
        "Municipal geometries are Statistics Canada 2021 cartographic census subdivision boundaries.",
        "Municipal metrics are official Statistics Canada 2021 Census Profile values.",
        "Census tract geometries are official Statistics Canada 2021 cartographic tract "
        "boundaries filtered by centroid to the current GTA municipalities.",
        "Census tract metrics are official Statistics Canada 2021 Census Profile values "
        "from the SDMX DF_CT dataflow (app/data/statcan_ct_metrics.csv). Suppressed or "
        "unavailable values are stored as null; rent burden is estimated from rent and "
        "income only as a clearly labeled fallback at serialization time.",
    ]
    temporary_path = seed_path.with_suffix(f"{seed_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(seed, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(seed_path)
    return updated


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "..", "x", "F"):
        return None
    return float(str(value).replace(",", "").replace("%", ""))


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch official Census Profile metrics for GTA census tracts."
    )
    parser.add_argument(
        "--generate-csv",
        action="store_true",
        help="Fetch official metrics and write normalized CSV.",
    )
    parser.add_argument(
        "--update-seed",
        action="store_true",
        help="Update seed file with official tract metrics.",
    )
    parser.add_argument(
        "--from-csv",
        type=Path,
        help="Sync seed tract metrics from an existing CSV instead of fetching "
        "from Statistics Canada (preserves nulls; performs no estimation).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "app" / "data" / "statcan_ct_metrics.csv",
        help="Output CSV path (default: app/data/statcan_ct_metrics.csv).",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow writing results even when coverage is below the minimum threshold.",
    )
    args = parser.parse_args()

    if args.from_csv:
        seed_path = PROJECT_ROOT / "app" / "data" / "demo_seed.json"
        updated = sync_seed_from_csv(seed_path, args.from_csv)
        print(f"Synced {updated} seed tract rows from {args.from_csv} (nulls preserved).")
        return

    if not args.generate_csv and not args.update_seed:
        parser.error("--generate-csv, --update-seed, or --from-csv is required.")

    print("Loading tract geoids from seed...")
    geoids = load_tract_geoids()
    print(f"Found {len(geoids)} GTA census tracts.")

    print("Fetching official Census Profile metrics from Statistics Canada...")
    metrics = fetch_all_tract_metrics(geoids)
    print(f"Fetched metrics for {len(metrics)} tracts.")

    # Report coverage
    has_income = sum(1 for m in metrics if m.median_income is not None)
    has_rent = sum(1 for m in metrics if m.median_rent is not None)
    has_pop = sum(1 for m in metrics if m.population is not None)
    has_burden = sum(1 for m in metrics if m.rent_burden_pct is not None)
    print(f"Coverage: income={has_income}, rent={has_rent}, population={has_pop}, burden={has_burden}")

    try:
        coverage = validate_tract_coverage(
            metrics, geoids, allow_partial=args.allow_partial
        )
    except ValueError as exc:
        print(
            f"ABORTING: {exc}. Re-run with --allow-partial only for diagnostic output. "
            "No files were written.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Coverage validation: {json.dumps(coverage, sort_keys=True)}")
    if coverage["partial"]:
        print("WARNING: writing partial tract data by explicit request.", file=sys.stderr)

    if args.generate_csv:
        write_csv(metrics, args.output)
        print(f"Wrote {len(metrics)} rows to {args.output}")

    if args.update_seed:
        seed_path = PROJECT_ROOT / "app" / "data" / "demo_seed.json"
        updated = update_seed_with_official_metrics(seed_path, metrics)
        print(f"Updated {updated} seed tract rows with official metrics.")


if __name__ == "__main__":
    main()
