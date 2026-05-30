# Spike: Real CMHC census-tract data

Status: **spike / assessment** (not implemented in the app). Date: 2026-05-30.

## Goal

Decide whether to replace the app's CMHC municipality inheritance/allocation with
**real census-tract CMHC values**, and if so, how. See
`docs/cmhc-census-tract-data-audit.md` for the corrected availability findings.

## Findings

1. **Real CT-level CMHC data exists for the Toronto CMA.** HMIP publishes both
   Rental Market Survey (RMS) and Starts & Completions Survey (SCSS) with a
   **Census Tract** breakdown. (Corrected an earlier audit claim that it did not.)
2. **Suppression is the real constraint, not availability.**
   - RMS rate/rent estimates are released only with 4+ responding entities and are
     suppressed (`**`) when CV > 10%. At tract granularity, **many GTA cells are
     suppressed** → real RMS rate/rent coverage is partial.
   - RMS `rental_universe` is a count (not an estimate) → released at CT even where
     rates are suppressed.
   - SCSS counts (starts, completions, under-construction) are observed counts →
     **good CT coverage**, with a CMHC caveat that tract attribution of new builds
     can be imperfect.
3. **No official JSON API.** Two viable ingestion routes:
   - The **`cmhc` R package** (mountainMath), which drives HMIP's internal
     `TableMapChart` endpoints and supports `breakdown="Census Tracts"`. This is the
     maintained, correct interface.
   - Replicating the package's **HMIP CSV-export** HTTP calls from Python.
4. **Clean geography hierarchy.** CMHC zones/neighbourhoods nest census tracts
   (CT → Neighbourhood → Zone → CSD), so a fallback chain is well-defined and a
   tract maps to exactly one zone.

## Prototype

`backend/etl/spike_cmhc_tract.py` (throwaway; not wired in, no tests) demonstrates
the Python ingestion path:

- `--dry-run` parses an embedded sample CSV and prints a coverage report
  (real / suppressed / missing) — proves the parse + coverage logic **offline**.
- Live mode builds the HMIP `TableMapChart` CSV-export URL (params mirror the `cmhc`
  R package), fetches a CT-breakdown table for the Toronto CMA, parses it (marking
  `**`/blank cells as suppressed), and reports per-metric tract coverage.

**Empirical finding (2026-05-30): a plain HTTP pull does NOT work.** The host is
reachable (HTTP 200), and the Toronto CMA "Vacancy Rate by Census Tract" page was
fetched directly (~100 KB). The returned HTML is a **JavaScript single-page-app
shell**: it carries `<script>` tags but **zero** `<table>`/`<svg>` elements and
**zero** occurrences of "Census Tract", "Vacancy", "Toronto", or any CT id / data
value — the table/chart is rendered client-side via AJAX after load. So a naive
`requests.get(...)` cannot retrieve real values; only the spike's offline `--dry-run`
path runs here. Real ingestion needs one of: (1) the **`cmhc` R package** run as an
**offline ETL step** that emits a committed CSV (mirroring how
`app/data/statcan_ct_metrics.csv` is produced today); (2) reverse-engineering HMIP's
undocumented internal AJAX/JSON endpoint; or (3) headless-browser automation. Any
ingested values must be **validated against known-good CMHC figures before being
labeled "real"** — shipping unvalidated data would violate the project's honesty
principle — so Phase A is left as a documented, validated plan rather than rushed.

To run where network is available:

```bash
python backend/etl/spike_cmhc_tract.py --dry-run                 # offline logic check
python backend/etl/spike_cmhc_tract.py --metric vacancy_rate --year 2024
python backend/etl/spike_cmhc_tract.py --metric housing_starts --year 2024
```

The single most reliable reference path remains the `cmhc` R package:

```r
library(cmhc)
get_cmhc(survey="Scss", series="Completions", dimension="Dwelling Type",
         breakdown="Census Tracts",
         geo_uid=get_cmhc_geography("CT", region="Toronto"), year=2024)
```

## Proposed integration (if we proceed — not done here)

Recommended **layered, count-first** rollout:

1. **Phase A — SCSS counts + `rental_universe` (highest value, lowest risk).**
   These have good CT coverage and are real counts, so they **replace the renter-share
   allocation** entirely. New ETL loader writes per-tract `cmhc_metrics` rows keyed by
   CTUID; the API stops allocating for tracts that have real rows.
2. **Phase B — RMS rates/rents with a real fallback chain.** Use the real CT value
   where published; otherwise fall back CT → Neighbourhood → Zone → municipality (all
   real CMHC geographies, better than blind CSD passthrough).
3. **Schema/UI:** add per-field `reliability` (A–D) and `suppressed` flags so the
   detail panel can show CMHC's reliability code and render suppressed cells as
   "Not available" instead of back-filling — consistent with the census provenance
   work already shipped.

### Effort / risk

- Phase A: medium (one ETL loader + tract-keyed CMHC rows + drop allocation for
  covered tracts + tests). High payoff (removes a whole class of estimation).
- Phase B: medium-high (fallback chain + reliability surfacing + UI). Payoff partial
  because RMS rates are often suppressed at CT.
- Main risk: HMIP's internal endpoint is undocumented; prefer the `cmhc` R package or
  pin the CSV-export contract and add a smoke test.

## Recommendation

Worth doing as a **follow-up milestone**, count-first (Phase A). The current
inheritance/allocation is an honest, clearly-labeled fallback and is fine to keep
shipping until then. Do **not** rip out estimation — keep it as the labeled fallback
for suppressed cells.
