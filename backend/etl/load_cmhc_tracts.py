"""Acquire REAL CMHC census-tract Starts & Completions (SCSS) data from HMIP.

This replaces the renter-share *allocation estimate* with CMHC's actually
published census-tract values for the metrics and years where they exist.

Honesty contract (see docs/cmhc-real-tract-data-plan.md):
  * Every (CMA, metric, year) slice is validated: the sum of the census-tract
    "All" column MUST equal CMHC's own published CMA total. A mismatch aborts
    the slice rather than writing unverified data.
  * Parser tests run against a committed fixture of REAL CMHC rows
    (backend/tests/fixtures/cmhc_ct_starts_sample.csv), never synthetic data.
  * Where CMHC publishes no row for a tract/year, the value is simply absent
    (the app keeps its labeled allocation estimate); zero is a real value
    distinct from absent.

Verified recipe (confirmed by direct HMIP calls, 2026-06-01):
  POST .../TableMapChart/ExportTable, form-encoded:
    TableId, GeographyId (CMA METCODE), GeographyTypeId=3, ForTimePeriod.Year,
    Frequency=Annual, exportType=csv  -> latin1 multi-section CSV.
  CT tables use the ".11" breakdown suffix; CMHC returns SHORT ct ids
  (e.g. "0001.00") which map to our CTUID by prepending the CMA prefix.

Usage:
  python etl/load_cmhc_tracts.py --self-test          # offline parser test
  python etl/load_cmhc_tracts.py --generate-csv [--years 2018 ... ]  # live pull
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]

HMIP_EXPORT = "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable"

# CMA METCODE -> our CTUID prefix. Confirmed by direct probe: each CMA returns
# real census-tract rows whose short ids map onto our tracts via this prefix.
CMA_PREFIX = {
    "2270": "535",  # Toronto
    "2240": "532",  # Oshawa
    "2320": "537",  # Hamilton
}

# metric -> (census-tract table code, published-CMA-total table code for the
# validation gate). Both verified: CT sum equals the published total.
METRICS = {
    "housing_starts_total": ("1.1.1.11", "1.1.1.3"),
    "housing_completions": ("1.1.2.11", "1.1.2.3"),
}

_CT_SHORT = re.compile(r"^\d{4}\.\d{2}$")


def _to_int(cell: str) -> int | None:
    v = (cell or "").replace(",", "").replace("$", "").strip()
    if v == "" or v in ("**", "x", "n/a", "-"):
        return None
    return int(v) if v.lstrip("-").isdigit() else None


def parse_ct_table(text: str) -> dict[str, int]:
    """Parse a CMHC CT ExportTable CSV -> {short_ct_id: All_value}.

    Picks the "All" column from the dwelling-type header row. Suppressed/blank
    cells are skipped (absent), not coerced to zero.
    """
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    all_idx: int | None = None
    out: dict[str, int] = {}
    for row in reader:
        if not row:
            continue
        first = row[0].strip()
        if header is None and first == "" and "All" in [c.strip() for c in row]:
            header = [c.strip() for c in row]
            all_idx = header.index("All")
            continue
        if all_idx is not None and _CT_SHORT.match(first):
            val = _to_int(row[all_idx]) if len(row) > all_idx else None
            if val is not None:
                out[first] = val
    return out


def parse_published_total(text: str) -> int | None:
    """Sum the 'All' column of a published CMA/centres table (validation gate).

    The province/centres table lists named rows; the total is the blank-named
    summary row, or the sum of the named rows. We sum named rows and also accept
    the explicit summary row when present.
    """
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    all_idx: int | None = None
    named_sum = 0
    named_rows = 0
    summary: int | None = None
    for row in reader:
        if not row:
            continue
        first = row[0].strip()
        if header is None and first == "" and "All" in [c.strip() for c in row]:
            header = [c.strip() for c in row]
            all_idx = header.index("All")
            continue
        if all_idx is None or len(row) <= all_idx:
            continue
        val = _to_int(row[all_idx])
        if val is None:
            continue
        if first == "":  # the blank-named summary/total row
            summary = val
        elif first not in ("Source", "Notes"):
            named_sum += val
            named_rows += 1
    if summary is not None:
        return summary
    # ``named_rows`` distinguishes a genuine zero total from "no parseable rows":
    # only return a number when we actually saw at least one named data row, so
    # the caller can treat None as "could not validate" rather than "zero".
    return named_sum if (all_idx is not None and named_rows) else None


def _fetch(table_id: str, cma_id: str, year: int) -> str:
    body = urlencode(
        {
            "TableId": table_id,
            "GeographyId": cma_id,
            "GeographyTypeId": "3",
            "ForTimePeriod.Year": str(year),
            "Frequency": "Annual",
            "exportType": "csv",
        }
    ).encode()
    req = Request(HMIP_EXPORT, data=body, headers={"User-Agent": "civicscope-etl/1.0"})
    with urlopen(req, timeout=90) as resp:
        return resp.read().decode("latin1")


def fetch_validated_slice(metric: str, cma_id: str, year: int) -> dict[str, int] | None:
    """Fetch one (metric, CMA, year) census-tract slice, gated on validation.

    Returns {our_ctuid: value} only if the CT sum equals the published CMA
    total. Returns None when the slice is empty (not yet published) and raises
    ValueError on a validation mismatch (never silently writes bad data).
    """
    ct_code, total_code = METRICS[metric]
    ct_rows = parse_ct_table(_fetch(ct_code, cma_id, year))
    if not ct_rows:
        return None  # CMHC has not published this slice yet
    ct_sum = sum(ct_rows.values())
    published = parse_published_total(_fetch(total_code, cma_id, year))
    if published is None:
        # CT rows exist but the published total could not be parsed (e.g. an
        # HTML/stub gateway response). Refuse to write data we cannot validate.
        raise ValueError(
            f"VALIDATION ABORTED {metric} CMA {cma_id} {year}: CT table has "
            f"{len(ct_rows)} rows but the published CMA total could not be parsed."
        )
    if ct_sum != published:
        raise ValueError(
            f"VALIDATION FAILED {metric} CMA {cma_id} {year}: "
            f"CT sum {ct_sum} != published total {published}"
        )
    prefix = CMA_PREFIX[cma_id]
    return {prefix + short: val for short, val in ct_rows.items()}


def _our_tract_geoids() -> set[str]:
    seed = json.loads((PROJECT_ROOT / "app" / "data" / "demo_seed.json").read_text(encoding="utf-8"))
    return {g["geoid"] for g in seed["geographies"] if g.get("type") == "census_tract"}


def generate_csv(years: list[int], output: Path) -> dict[str, Any]:
    our = _our_tract_geoids()
    # rows[(geoid, year)][metric] = value
    rows: dict[tuple[str, int], dict[str, int]] = {}
    validated, skipped_empty = [], []
    for metric in METRICS:
        for cma_id in CMA_PREFIX:
            for year in years:
                sl = fetch_validated_slice(metric, cma_id, year)
                if sl is None:
                    skipped_empty.append((metric, cma_id, year))
                    continue
                validated.append((metric, cma_id, year))
                for geoid, val in sl.items():
                    if geoid in our:
                        rows.setdefault((geoid, year), {})[metric] = val

    fields = ["geoid", "year", *METRICS]
    with output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for (geoid, year), metrics in sorted(rows.items()):
            w.writerow([geoid, year, *(metrics.get(m, "") for m in METRICS)])

    covered = {g for (g, _y) in rows}
    return {
        "output": str(output),
        "data_rows": len(rows),
        "tracts_covered": len(covered),
        "coverage_pct": round(100 * len(covered) / len(our), 1),
        "validated_slices": len(validated),
        "skipped_empty_slices": len(skipped_empty),
        "years": years,
    }


def _self_test() -> None:
    fixture = PROJECT_ROOT / "tests" / "fixtures" / "cmhc_ct_starts_sample.csv"
    text = fixture.read_text(encoding="latin1")
    parsed = parse_ct_table(text)
    # The fixture is REAL CMHC data: 0017.01 = 2,304 (comma-formatted), 0005.00 = 410.
    assert parsed["0017.01"] == 2304, parsed.get("0017.01")
    assert parsed["0005.00"] == 410, parsed.get("0005.00")
    assert parsed["0001.00"] == 0  # zero is a real value, kept
    print("self-test OK:", {k: parsed[k] for k in ("0001.00", "0005.00", "0017.01")})


def main() -> None:
    p = argparse.ArgumentParser(description="Load real CMHC census-tract SCSS data.")
    p.add_argument("--self-test", action="store_true", help="Offline parser test against the real fixture.")
    p.add_argument("--generate-csv", action="store_true")
    p.add_argument("--years", type=int, nargs="+", default=list(range(2018, 2025)))
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "app" / "data" / "cmhc_ct_metrics.csv")
    args = p.parse_args()

    if args.self_test:
        _self_test()
        return
    if args.generate_csv:
        print("Fetching + validating real CMHC census-tract SCSS data from HMIP...", file=sys.stderr)
        report = generate_csv(args.years, args.output)
        print(json.dumps(report, indent=2))
        return
    p.error("--self-test or --generate-csv required")


if __name__ == "__main__":
    main()
