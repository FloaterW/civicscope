"""Build an isolated Census candidate from official bulk ZIPs when SDMX is unavailable.

Uses only the total-count column and its adjacent symbol (headers repeat SYMBOL).
Never loads a database or overwrites the packaged seed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from etl.load_census import parse_metric_row, update_seed_metrics, validate_official_metrics
from etl.load_tract_census import TractMetric, update_seed_with_official_metrics, validate_tract_coverage, write_csv

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BASE = "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger/comp/GetFile.cfm?FILETYPE=CSV&GEONO="
# The bulk release includes additional income characteristics. Its IDs are NOT
# SDMX IDs. Validate both the code and exact published label before using data.
BULK_CHARACTERISTICS = {
    "population": ("1", "Population, 2021"),
    "previous_population": ("2", "Population, 2016"),
    "median_income": ("243", "Median total income of household in 2020 ($)"),
    "renter_households": ("1490", "Total - Tenant households in non-farm, non-reserve private dwellings - 25% sample data"),
    "rent_burden_pct": ("1492", "% of tenant households spending 30% or more of its income on shelter costs"),
    "median_rent": ("1494", "Median monthly shelter costs for rented dwellings ($)"),
    "dwellings_total": ("41", "Total - Occupied private dwellings by structural type of dwelling - 100% data"),
    "dwellings_single_detached": ("42", "Single-detached house"),
    "dwellings_semi_detached": ("43", "Semi-detached house"),
    "dwellings_row_house": ("44", "Row house"),
    "dwellings_apt_duplex": ("45", "Apartment or flat in a duplex"),
    "dwellings_apt_low_rise": ("46", "Apartment in a building that has fewer than five storeys"),
    "dwellings_apt_high_rise": ("47", "Apartment in a building that has five or more storeys"),
    "owner_households": ("1415", "Owner"),
    "tenure_renter_households": ("1416", "Renter"),
}


def parse_bulk_rows(rows, expected_dguids):
    header = next(rows)
    indices = {key: header.index(key) for key in ("CENSUS_YEAR", "DGUID", "CHARACTERISTIC_ID", "CHARACTERISTIC_NAME", "C1_COUNT_TOTAL")}
    value_index = indices["C1_COUNT_TOTAL"]
    if header[value_index + 1] != "SYMBOL":
        raise ValueError("Missing total-count symbol column")
    mapping = {value[0]: key for key, value in BULK_CHARACTERISTICS.items()}
    grouped = {}
    seen = set()
    for row in rows:
        if not row:
            continue
        dguid = row[indices["DGUID"]]
        characteristic = row[indices["CHARACTERISTIC_ID"]]
        if dguid not in expected_dguids or characteristic not in mapping:
            continue
        if row[indices["CENSUS_YEAR"]] != "2021":
            raise ValueError("Unexpected Census vintage")
        key = (dguid, characteristic)
        if key in seen:
            raise ValueError(f"Duplicate Census observation: {key}")
        seen.add(key)
        label = row[indices["CHARACTERISTIC_NAME"]].strip()
        if label != BULK_CHARACTERISTICS[mapping[characteristic]][1]:
            raise ValueError(f"Census characteristic label changed: {characteristic} {label}")
        symbol = row[value_index + 1].strip()
        value = row[value_index] if symbol in ("", "r") else None
        geoid = expected_dguids[dguid]
        grouped.setdefault(geoid, {"geoid": geoid, "year": 2021})[mapping[characteristic]] = value
    required = {(dguid, code) for dguid in expected_dguids for code in mapping}
    missing = required - seen
    if missing:
        raise ValueError(f"Bulk file omitted {len(missing)} requested Census observations")
    return [parse_metric_row(grouped[geoid]) for geoid in sorted(grouped)]


def read_archive(path, dguids):
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith("_English_CSV_data.csv")]
        if len(names) != 1:
            raise ValueError("Expected exactly one official English data CSV")
        with archive.open(names[0]) as handle:
            # These official bulk files use single-byte Windows characters
            # (e.g. accented geography names), unlike the UTF-8 SDMX endpoint.
            return parse_bulk_rows(csv.reader(io.TextIOWrapper(handle, encoding="cp1252", newline="")), dguids)


def build_candidate(csd_zip: Path, ct_zip: Path, output: Path):
    if output.exists():
        raise ValueError("Candidate output already exists; use a new directory")
    baseline = ROOT / "app/data"
    seed = json.loads((baseline / "demo_seed.json").read_text(encoding="utf-8"))
    municipalities = {"2021A0005" + g["geoid"]: g["geoid"] for g in seed["geographies"] if g["type"] == "municipality"}
    tracts = {"2021S0507" + g["geoid"].replace(".", "_"): g["geoid"] for g in seed["geographies"] if g["type"] == "census_tract"}
    # Bulk DGUIDs retain dots, whereas SDMX encodes them with underscores.
    tracts = {key.replace("_", "."): value for key, value in tracts.items()}
    municipal = read_archive(csd_zip, municipalities)
    validate_official_metrics(municipal, list(municipalities.values()))
    tract = [TractMetric(**vars(record)) for record in read_archive(ct_zip, tracts)]
    coverage = validate_tract_coverage(tract, list(tracts.values()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".census-candidate-", dir=output.parent) as temporary:
        stage = Path(temporary) / "data"
        stage.mkdir()
        shutil.copy2(baseline / "demo_seed.json", stage / "demo_seed.json")
        update_seed_metrics(stage / "demo_seed.json", municipal)
        update_seed_with_official_metrics(stage / "demo_seed.json", tract)
        refreshed = json.loads((stage / "demo_seed.json").read_text(encoding="utf-8"))
        refreshed["metadata"]["source"] = "statistics_canada_2021_census_profile_bulk_csv_and_boundaries"
        refreshed["metadata"]["notes"] = [
            "Municipal and tract boundaries are Statistics Canada 2021 cartographic boundaries; GTA tracts are filtered by centroid.",
            "Metrics are official 2021 Census Profile bulk CSV total-count observations (Ontario CSD and national CMA/CA/CT archives).",
            "Total-count suppression symbols are preserved as null. Unflagged genuine zeros are retained.",
            "Owner and renter tenure use the same private-household universe (25% sample); tenant shelter-cost households remain separate.",
        ]
        refreshed["metadata"]["tract_metric_coverage"] = coverage
        (stage / "demo_seed.json").write_text(json.dumps(refreshed, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        write_csv(tract, stage / "statcan_ct_metrics.csv")
        manifest = {
            "checked_at": datetime.now(UTC).isoformat(),
            "source": "Statistics Canada 2021 Census Profile official bulk CSV",
            "source_archives": [
                {"url": SOURCE_BASE + code + "&Lang=E", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for code, path in (("021", csd_zip), ("007", ct_zip))
            ],
            "municipalities": len(municipal), "tracts": len(tract), "coverage": coverage,
            "artifacts": {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in ("demo_seed.json", "statcan_ct_metrics.csv")},
        }
        (stage / "census_source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    print(json.dumps(manifest, indent=2))


def promote_candidate(candidate: Path):
    """Promote a reviewed local candidate only when its hashes/geographies match.

    This is an explicit developer action, not called by scheduled refreshes.
    Existing numeric values may change only for the known owner mapping fix.
    """
    baseline = ROOT / "app/data"
    manifest = json.loads((candidate / "census_source_manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifacts"].items():
        if name not in {"demo_seed.json", "statcan_ct_metrics.csv"}:
            raise ValueError("Unexpected candidate artifact")
        if hashlib.sha256((candidate / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Candidate artifact hash mismatch")
    if set(manifest["artifacts"]) != {"demo_seed.json", "statcan_ct_metrics.csv"}:
        raise ValueError("Incomplete candidate artifacts")
    before = json.loads((baseline / "demo_seed.json").read_text(encoding="utf-8"))
    after = json.loads((candidate / "demo_seed.json").read_text(encoding="utf-8"))
    old = {g["geoid"]: g for g in before["geographies"]}
    new = {g["geoid"]: g for g in after["geographies"]}
    if set(old) != set(new) or len(new) != len(after["geographies"]):
        raise ValueError("Candidate changed geography coverage")
    for geoid, item in new.items():
        if {k: v for k, v in item.items() if k != "metrics"} != {k: v for k, v in old[geoid].items() if k != "metrics"}:
            raise ValueError("Candidate changed geography definitions")
        metrics = item.get("metrics")
        if not isinstance(metrics, list) or len(metrics) != 1 or not isinstance(metrics[0], dict):
            raise ValueError("Candidate must contain exactly one Census metric row")
        metric = metrics[0]
        if set(metric) != {"year", *BULK_CHARACTERISTICS} or type(metric["year"]) is not int or metric["year"] != 2021:
            raise ValueError("Candidate Census fields or vintage changed")
        for field, value in metric.items():
            if value is not None and (type(value) not in {int, float} or abs(value) > 10**12 or not math.isfinite(value) or value < 0):
                raise ValueError(f"Invalid Census value: {geoid} {field}")
            if field not in {"median_income", "median_rent", "rent_burden_pct"} and value is not None and type(value) is not int:
                raise ValueError(f"Census count is not an integer: {geoid} {field}")
            if field == "rent_burden_pct" and value is not None and value > 100:
                raise ValueError("Invalid rent burden percentage")
            previous = old[geoid]["metrics"][0].get(field)
            if field != "owner_households" and previous is not None and value != previous:
                raise ValueError(f"Unreviewed existing value change: {geoid} {field}")
    for name in ("demo_seed.json", "statcan_ct_metrics.csv", "census_source_manifest.json"):
        temporary = baseline / (name + ".tmp")
        shutil.copy2(candidate / name, temporary)
        temporary.replace(baseline / name)
    print("Promoted audited Census artifacts; no database was modified.")


def freeze_corrections(candidate: Path, destination: Path):
    """Generate a one-time immutable data-migration input, never overwrite it."""
    manifest = json.loads((candidate / "census_source_manifest.json").read_text(encoding="utf-8"))
    contents = (candidate / "demo_seed.json").read_bytes()
    if hashlib.sha256(contents).hexdigest() != manifest["artifacts"]["demo_seed.json"]:
        raise ValueError("Candidate seed hash mismatch")
    seed = json.loads(contents)
    fields = set(BULK_CHARACTERISTICS) - {"median_income", "median_rent"}
    records = [{"geoid": row["geoid"], "type": row["type"], "geometry_source": row["geometry_source"],
                "metrics": [{"year": 2021, **{key: row["metrics"][0][key] for key in sorted(fields)}}]}
               for row in sorted(seed["geographies"], key=lambda g: g["geoid"])]
    payload = {"schema_version": 1, "source_archives": manifest["source_archives"], "geographies": records}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with destination.open("xb") as handle:
        handle.write(encoded)
    print("Frozen correction SHA-256: " + hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csd-zip", type=Path)
    parser.add_argument("--ct-zip", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--promote", type=Path, help="Explicitly promote an already reviewed candidate (no database writes).")
    parser.add_argument("--freeze-corrections", type=Path, help="Candidate to freeze for a new one-time data migration; requires --output.")
    args = parser.parse_args()
    if args.freeze_corrections and args.output:
        freeze_corrections(args.freeze_corrections, args.output)
    elif args.promote:
        promote_candidate(args.promote)
    elif args.csd_zip and args.ct_zip and args.output:
        build_candidate(args.csd_zip, args.ct_zip, args.output)
    else:
        parser.error("Provide both archives and --output, or --promote.")
