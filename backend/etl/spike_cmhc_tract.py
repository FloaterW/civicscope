"""SPIKE (throwaway): pull REAL census-tract-level CMHC data.

Purpose
-------
Reduce uncertainty about replacing the app's municipality inheritance/allocation
with real CMHC census-tract values. CMHC's Housing Market Information Portal
(HMIP) publishes Rental Market Survey (RMS) and Starts & Completions Survey
(SCSS) data with a Census Tract breakdown for the Toronto CMA (see
docs/cmhc-real-tract-data-spike.md). There is no official JSON API; the de-facto
programmatic route is the `cmhc` R package, which drives HMIP's internal
`TableMapChart` endpoints. This script demonstrates the equivalent ingestion in
Python and reports coverage/suppression so we can judge how much real data we'd
actually get per metric.

This is a SPIKE: not wired into the app, not imported anywhere, no tests. It
exists to validate the approach and produce coverage numbers.

Usage
-----
    # Offline: prove the parse + coverage logic works on an embedded sample.
    python etl/spike_cmhc_tract.py --dry-run

    # Live (requires outbound network to www03.cmhc-schl.gc.ca):
    python etl/spike_cmhc_tract.py --metric vacancy_rate --year 2024

Note: the live HMIP endpoint params below mirror what the `cmhc` R package
sends, but HMIP's internal API is undocumented and version-sensitive — verify
against the live portal (or just use the `cmhc` R package) before relying on it.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Toronto CMA in HMIP. (GeographyId for the Toronto CMA in the portal.)
TORONTO_CMA_GEOGRAPHY_ID = "2270"
HMIP_BASE = "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart"

# Metric -> (HMIP category level 1/2). These mirror the `cmhc` R package's
# table identifiers; treat as a starting point to verify against live HMIP.
METRIC_TABLES = {
    "vacancy_rate": ("Primary Rental Market", "Vacancy Rate (%)"),
    "average_rent": ("Primary Rental Market", "Average Rent ($)"),
    "rental_universe": ("Primary Rental Market", "Rental Universe"),
    "housing_starts": ("New Housing Construction", "Starts (Actual)"),
    "housing_completions": ("New Housing Construction", "Completions"),
}
# CMHC suppression / reliability markers in exported tables.
SUPPRESSED_TOKENS = {"**", "n/a", "n/u", "", "-", "x"}


def load_gta_tract_ctuids() -> list[str]:
    seed = json.loads((PROJECT_ROOT / "app" / "data" / "demo_seed.json").read_text(encoding="utf-8"))
    return sorted(g["geoid"] for g in seed["geographies"] if g.get("type") == "census_tract")


def cmhc_ct_table_url(metric: str, year: int) -> str:
    """Build the HMIP CSV-export URL for a metric, broken down by Census Tract.

    RowField=23 is "by Census Tract" in HMIP's TableMapChart API (per the
    `cmhc` R package). This is the network-dependent, verify-me part.
    """
    cat1, cat2 = METRIC_TABLES[metric]
    params = {
        "GeographyType": "MetropolitanMajorArea",
        "GeographyId": TORONTO_CMA_GEOGRAPHY_ID,
        "CategoryLevel1": cat1,
        "CategoryLevel2": cat2,
        "RowField": "23",   # by Census Tract
        "Year": str(year),
        "Format": "CSV",
    }
    return f"{HMIP_BASE}/Table?{urlencode(params)}"


def fetch_cmhc_ct_csv(metric: str, year: int, timeout: int = 30) -> str:
    url = cmhc_ct_table_url(metric, year)
    req = Request(url, headers={"User-Agent": "civicscope-spike/0.1"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig")


def parse_cmhc_ct_csv(text: str) -> dict[str, dict[str, object]]:
    """Parse an HMIP CT-breakdown CSV into {ctuid: {value, suppressed, reliability}}.

    HMIP tables vary in shape; this targets the common "CT | value | reliability"
    export. Cells holding a suppression token are recorded as suppressed=True.
    """
    out: dict[str, dict[str, object]] = {}
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    for row in rows:
        first = row[0].strip()
        # CT rows look like "5350001.00" (optionally with a CMA prefix).
        ctuid = _normalize_ctuid(first)
        if ctuid is None:
            continue
        raw_value = row[1].strip() if len(row) > 1 else ""
        reliability = row[2].strip() if len(row) > 2 else ""
        suppressed = raw_value.lower() in SUPPRESSED_TOKENS
        value = None if suppressed else _to_number(raw_value)
        out[ctuid] = {"value": value, "suppressed": suppressed, "reliability": reliability}
    return out


def _normalize_ctuid(token: str) -> str | None:
    t = token.replace(",", "").strip()
    # Accept "5350001.00" or "0001.00"-style; require a dotted CT id.
    if "." in t and t.replace(".", "").isdigit() and len(t.split(".")[0]) >= 4:
        return t
    return None


def _to_number(s: str):
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def coverage_report(metric: str, parsed: dict[str, dict[str, object]], gta_ctuids: list[str]) -> dict:
    gta = set(gta_ctuids)
    in_gta = {c: v for c, v in parsed.items() if c in gta}
    real = [c for c, v in in_gta.items() if not v["suppressed"] and v["value"] is not None]
    suppressed = [c for c, v in in_gta.items() if v["suppressed"]]
    missing = [c for c in gta if c not in parsed]
    return {
        "metric": metric,
        "gta_tracts": len(gta),
        "real": len(real),
        "suppressed": len(suppressed),
        "missing_from_table": len(missing),
        "real_pct": round(100 * len(real) / len(gta), 1) if gta else 0.0,
        "sample_real": {c: in_gta[c] for c in real[:3]},
    }


# A tiny embedded sample so --dry-run exercises the parser/coverage offline.
_SAMPLE_CSV = """Census Tract,Vacancy Rate (%),Reliability
5350001.00,1.8,a
5350002.00,**,
5350003.01,2.4,b
9990000.00,3.1,a
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="SPIKE: real CMHC census-tract data")
    parser.add_argument("--metric", choices=sorted(METRIC_TABLES), default="vacancy_rate")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--dry-run", action="store_true", help="Parse an embedded sample (no network).")
    args = parser.parse_args()

    gta = load_gta_tract_ctuids()
    print(f"GTA census tracts in seed: {len(gta)}")

    if args.dry_run:
        parsed = parse_cmhc_ct_csv(_SAMPLE_CSV)
        # Pretend the sample's first 3 CTUIDs are in-GTA for the demo.
        report = coverage_report(args.metric, parsed, gta_ctuids=list(parsed)[:3])
        print("DRY RUN — parsed sample:")
        print(json.dumps(parsed, indent=2))
        print("Coverage (sample):", json.dumps(report, indent=2))
        return

    try:
        text = fetch_cmhc_ct_csv(args.metric, args.year)
    except Exception as exc:  # noqa: BLE001 - spike: report and exit cleanly
        print(f"Live fetch failed ({exc}).", file=sys.stderr)
        print(
            "Network to HMIP may be unavailable in this environment. Use the `cmhc` "
            "R package as the reference path, e.g.:\n"
            '  library(cmhc); get_cmhc(survey="Rms", series="Vacancy Rate", '
            'dimension="Bedroom Type", breakdown="Census Tracts", '
            'geo_uid=cmhc::get_cmhc_geography("CT", region="Toronto"), year=2024)',
            file=sys.stderr,
        )
        raise SystemExit(2)

    parsed = parse_cmhc_ct_csv(text)
    report = coverage_report(args.metric, parsed, gta)
    print("Coverage:", json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
