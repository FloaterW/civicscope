"""Diagnostic official RMS tract-universe pilot; never updates application data.

Table 2.1.26.6 was identified from CMHC's linked rental-universe tract page.
The requested universe is Row / Apartment, matching the existing RMS loader.
Identifier matches are candidates, NOT proof of matching boundary vintages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable"
TABLE = "2.1.26.6"
CMAS = {"2270": "535", "2240": "532", "2320": "537"}
COLUMNS = ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom +", "Total"]


def count_cell(raw: str) -> dict:
    text = raw.strip()
    normalized = text.replace(",", "")
    if re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", text):
        return {"raw": text, "value": int(normalized), "status": "published"}
    status = "suppressed_or_unreliable" if text in {"**", "x"} else "unavailable"
    if text not in {"", "**", "x", "-", "—", "n/a"}:
        raise ValueError(f"Unexpected universe cell: {text!r}")
    return {"raw": text, "value": None, "status": status}


def parse_universe(text: str, year: int) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3 or not rows[0] or "Universe by Bedroom Type by Census Tract" not in rows[0][0]:
        raise ValueError("Response is not the expected tract-universe CSV")
    if rows[1] != [f"October {year} Row / Apartment"]:
        raise ValueError("Response period or dwelling universe differs from request")
    header = [cell.strip() for cell in rows[2]]
    if header[:6] != ["", *COLUMNS]:
        raise ValueError("Unexpected universe columns")
    tracts, total = {}, None
    seen_summary = False
    for row in rows[3:]:
        if not row:
            continue
        geoid = row[0].strip()
        is_tract = bool(re.fullmatch(r"\d{4}\.\d{2}", geoid))
        if not is_tract and geoid:
            continue
        if len(row) < 6:
            if is_tract:
                raise ValueError("Truncated tract row")
            continue
        values = {name: count_cell(row[index + 1]) for index, name in enumerate(COLUMNS)}
        if is_tract:
            if geoid in tracts:
                raise ValueError(f"Duplicate tract {geoid}")
            tracts[geoid] = values
        elif seen_summary:
            raise ValueError("Duplicate published summary row")
        else:
            seen_summary = True
            total = values["Total"]["value"]
    if not tracts or total is None:
        raise ValueError("Missing tract rows or published summary total")
    published = [row["Total"]["value"] for row in tracts.values()]
    known_sum = sum(value for value in published if value is not None)
    return {
        "tracts": tracts, "published_total": total, "known_tract_sum": known_sum,
        "totals_reconcile": known_sum == total and all(value is not None for value in published),
    }


def fetch_universe(cma: str, year: int) -> bytes:
    form = {
        "TableId": TABLE, "GeographyId": cma, "GeographyTypeId": "3",
        "ForTimePeriod.Year": str(year), "ForTimePeriod.Month": "10", "ExportType": "csv",
        "AppliedFilters[0].Key": "dwelling_type_desc_en",
        "AppliedFilters[0].Value": "Row / Apartment",
    }
    request = Request(ENDPOINT, data=urlencode(form).encode(), headers={"User-Agent": "civicscope-research/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=70) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("Unexpectedly large RMS response")
                return raw
        except (URLError, TimeoutError, ConnectionError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def run_pilot(year: int, output: Path) -> dict:
    output = output.resolve()
    allowed = (ROOT.parent / "out").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError("Pilot output must be a new directory beneath the repository out directory")
    if output.exists():
        raise ValueError("Pilot output already exists; use a new directory")
    seed = json.loads((ROOT / "app/data/demo_seed.json").read_text(encoding="utf-8"))
    our_ids = {row["geoid"] for row in seed["geographies"] if row["type"] == "census_tract"}
    report = {
        "status": "research_only_not_for_promotion", "year": year, "month": 10,
        "universe": "Row / Apartment", "table": TABLE, "source": ENDPOINT,
        "retrieved_at": datetime.now(UTC).isoformat(), "boundary_compatibility": "not_verified",
        "application_tracts": len(our_ids), "cmas": {},
    }
    matches = set()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rms-pilot-", dir=output.parent) as temporary:
        stage = Path(temporary) / "artifacts"
        stage.mkdir()
        for cma, prefix in CMAS.items():
            raw = fetch_universe(cma, year)
            parsed = parse_universe(raw.decode("cp1252"), year)
            ids = {prefix + short for short, fields in parsed["tracts"].items() if fields["Total"]["value"] is not None}
            eligible = ids & our_ids
            matches.update(eligible)
            subset = {geoid for geoid in our_ids if geoid.startswith(prefix)}
            report["cmas"][cma] = {
                "raw_sha256": hashlib.sha256(raw).hexdigest(), "source_rows": len(parsed["tracts"]),
                "published_total": parsed["published_total"], "known_tract_sum": parsed["known_tract_sum"],
                "totals_reconcile": parsed["totals_reconcile"], "application_tracts": len(subset),
                "matching_identifiers_with_total": len(eligible),
                "without_published_exact_identifier_total": sorted(subset - eligible),
                "source_identifiers_outside_application": sorted(ids - our_ids),
                "unavailable_total_cells": sum(fields["Total"]["value"] is None for fields in parsed["tracts"].values()),
            }
            (stage / f"cmhc-{cma}-{year}.csv").write_bytes(raw)
            (stage / f"parsed-{cma}-{year}.json").write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
        report["matching_identifiers_with_total"] = len(matches)
        report["identifier_coverage_pct"] = round(100 * len(matches) / len(our_ids), 1) if our_ids else 0
        (stage / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_pilot(args.year, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "cmas"}, indent=2))
