"""Acquire CMHC census-tract Starts & Completions (SCSS) data from HMIP.

Replaces the renter-share allocation estimate with CMHC's published census-tract
values for the metrics/years where they exist. Each (CMA, metric, year) slice is
validated: the sum of the census-tract "All" column must equal CMHC's published
CMA total, otherwise the slice is rejected. Parser tests use a committed fixture
of real CMHC rows (tests/fixtures/cmhc_ct_starts_sample.csv).

HMIP request: POST .../TableMapChart/ExportTable, form-encoded with TableId,
GeographyId (CMA METCODE), GeographyTypeId=3, ForTimePeriod.Year, Frequency=Annual,
exportType=csv. Returns a latin1 multi-section CSV. CT tables use the ".11"
breakdown suffix; CMHC returns short CT ids (e.g. "0001.00") that map to our CTUID
by prepending the CMA prefix.

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

    Returns {short_ct_id: value} (CMHC's own short ids, e.g. "0001.00") only if
    the CT sum equals the published CMA total. Returns None when the slice is
    empty (not yet published) and raises ValueError on a validation mismatch or
    an unparseable published total (never silently writes bad data).
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
    return ct_rows


def _parent_short(short_id: str) -> str:
    """CMHC's pre-split parent tract for a 2021 short id: 0003.01 -> 0003.00.

    StatCan preserves the integer part when a tract splits, so the 2016 parent
    of every 2021 child shares its integer tract number with a ``.00`` suffix.
    """
    return short_id.split(".")[0] + ".00"


def resolve_cma_slice(
    cmhc_short: dict[str, int],
    our_ctuids: list[str],
    prefix: str,
    renter: dict[str, int],
) -> dict[str, tuple[int, str]]:
    """Resolve our 2021 tracts in one CMA against CMHC's published tract values.

    Returns {our_ctuid: (value, source)} for every tract that resolves to real
    or parent-derived CMHC data. ``source`` is:
      * "official"        - exact same-CMA CMHC value, OR a CMHC *parent* tract
                            that recorded 0 (so every 2021 child is a real 0).
      * "estimated_parent"- the CMHC parent tract recorded a non-zero total that
                            we allocate among its 2021 children by renter share
                            (a better estimate than the municipal allocation, but
                            still an estimate — labelled distinctly, not official).
    Tracts that resolve to neither are omitted (the API keeps the municipal
    allocation estimate for them).
    """
    resolved: dict[str, tuple[int, str]] = {}
    by_parent: dict[str, list[str]] = {}
    for full in our_ctuids:
        short = full[len(prefix):]
        if short in cmhc_short:
            resolved[full] = (cmhc_short[short], "official")  # exact 2021 match
        else:
            parent = _parent_short(short)
            if parent in cmhc_short:
                by_parent.setdefault(parent, []).append(full)

    for parent, siblings in by_parent.items():
        parent_value = cmhc_short[parent]
        if parent_value == 0:
            # CMHC measured zero starts/completions in the whole parent tract, so
            # every 2021 child genuinely had zero. Real, official, no allocation.
            for s in siblings:
                resolved[s] = (0, "official")
            continue
        # Allocate the real parent total among siblings by renter share, using
        # largest-remainder so the children sum back to the parent total exactly.
        weights = {s: max(renter.get(s, 0) or 0, 0) for s in siblings}
        total_w = sum(weights.values())
        if total_w <= 0:
            base, rem = divmod(parent_value, len(siblings))
            for i, s in enumerate(sorted(siblings)):
                resolved[s] = (base + (1 if i < rem else 0), "estimated_parent")
            continue
        raw = {s: parent_value * weights[s] / total_w for s in siblings}
        alloc = {s: int(raw[s]) for s in siblings}
        remainder = parent_value - sum(alloc.values())
        for s in sorted(siblings, key=lambda s: raw[s] - alloc[s], reverse=True)[:remainder]:
            alloc[s] += 1
        for s in siblings:
            resolved[s] = (alloc[s], "estimated_parent")
    return resolved


def _load_seed_tracts() -> tuple[set[str], dict[str, int]]:
    """Return (our census-tract geoids, {geoid: renter_households}) from the seed."""
    seed = json.loads((PROJECT_ROOT / "app" / "data" / "demo_seed.json").read_text(encoding="utf-8"))
    geoids: set[str] = set()
    renter: dict[str, int] = {}
    for g in seed["geographies"]:
        if g.get("type") != "census_tract":
            continue
        geoids.add(g["geoid"])
        metrics = g.get("metrics") or []
        if metrics:
            latest = sorted(metrics, key=lambda r: r.get("year", 0))[-1]
            if latest.get("renter_households") is not None:
                renter[g["geoid"]] = int(latest["renter_households"])
    return geoids, renter


# CSV/DB source values, most-to-least authoritative:
#   official          - real CMHC census-tract value (or a parent that recorded 0)
#   estimated_parent  - allocated from a real CMHC parent tract (split estimate)
# (A tract absent from this file keeps the API's municipal allocation, "estimated".)
SOURCE_COLUMNS = {m: f"{m}_source" for m in METRICS}
MIN_TRACT_COVERAGE_PCT = 90.0


def validate_generation_coverage(
    all_tracts: set[str],
    covered_tracts: set[str],
    skipped_slices: list[tuple[str, str, int]],
    expected_slice_count: int,
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    coverage_pct = 100 * len(covered_tracts) / len(all_tracts) if all_tracts else 0.0
    problems = []
    if skipped_slices:
        problems.append(f"{len(skipped_slices)}/{expected_slice_count} missing metric slices")
    if coverage_pct < MIN_TRACT_COVERAGE_PCT:
        problems.append(
            f"tract coverage {coverage_pct:.1f}% is below {MIN_TRACT_COVERAGE_PCT:.1f}%"
        )
    if problems and not allow_partial:
        raise ValueError(
            "CMHC tract refresh failed coverage validation: " + "; ".join(problems)
            + ". Re-run with --allow-partial only for diagnostic output."
        )
    return {
        "coverage_pct": round(coverage_pct, 1),
        "expected_slices": expected_slice_count,
        "skipped_empty_slices": len(skipped_slices),
        "partial": bool(problems),
    }


def generate_csv(
    years: list[int], output: Path, *, allow_partial: bool = False
) -> dict[str, Any]:
    our, renter = _load_seed_tracts()
    our_by_prefix: dict[str, list[str]] = {}
    for geoid in our:
        our_by_prefix.setdefault(geoid[:3], []).append(geoid)

    # rows[(geoid, year)][metric] = (value, source)
    rows: dict[tuple[str, int], dict[str, tuple[int, str]]] = {}
    validated, skipped_empty = [], []
    counts = {"official": 0, "estimated_parent": 0}
    for metric in METRICS:
        for cma_id, prefix in CMA_PREFIX.items():
            our_in_cma = our_by_prefix.get(prefix, [])
            for year in years:
                sl = fetch_validated_slice(metric, cma_id, year)
                if sl is None:
                    skipped_empty.append((metric, cma_id, year))
                    continue
                validated.append((metric, cma_id, year))
                resolved = resolve_cma_slice(sl, our_in_cma, prefix, renter)
                for geoid, (val, source) in resolved.items():
                    rows.setdefault((geoid, year), {})[metric] = (val, source)
                    counts[source] += 1

    covered = {g for (g, _y) in rows}
    expected_slice_count = len(METRICS) * len(CMA_PREFIX) * len(years)
    coverage = validate_generation_coverage(
        our,
        covered,
        skipped_empty,
        expected_slice_count,
        allow_partial=allow_partial,
    )

    fields = ["geoid", "year"]
    for m in METRICS:
        fields += [m, SOURCE_COLUMNS[m]]
    temporary_output = output.with_suffix(f"{output.suffix}.tmp")
    with temporary_output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for (geoid, year), metrics in sorted(rows.items()):
            cells: list[Any] = [geoid, year]
            for m in METRICS:
                val, source = metrics.get(m, (None, None))
                cells += ["" if val is None else val, source or ""]
            w.writerow(cells)
    temporary_output.replace(output)

    return {
        "output": str(output),
        "data_rows": len(rows),
        "tracts_covered": len(covered),
        "coverage_pct": coverage["coverage_pct"],
        "expected_slices": coverage["expected_slices"],
        "validated_slices": len(validated),
        "skipped_empty_slices": len(skipped_empty),
        "partial": coverage["partial"],
        "metric_value_counts": counts,
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
    p.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow diagnostic CSV output that fails coverage validation.",
    )
    args = p.parse_args()

    if args.self_test:
        _self_test()
        return
    if args.generate_csv:
        canonical_output = PROJECT_ROOT / "app" / "data" / "cmhc_ct_metrics.csv"
        if args.allow_partial and args.output.resolve() == canonical_output.resolve():
            p.error(
                "--allow-partial requires an explicit noncanonical --output path; "
                "partial diagnostics cannot replace the packaged CSV."
            )
        print("Fetching + validating real CMHC census-tract SCSS data from HMIP...", file=sys.stderr)
        report = generate_csv(args.years, args.output, allow_partial=args.allow_partial)
        print(json.dumps(report, indent=2))
        return
    p.error("--self-test or --generate-csv required")


if __name__ == "__main__":
    main()
