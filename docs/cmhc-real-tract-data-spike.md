# Spike: Real CMHC census-tract data

Status: **implemented count-first; RMS tract ingestion remains follow-up**. Date: 2026-05-30; implementation status updated 2026-07-11.

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

> The throwaway prototype `backend/etl/spike_cmhc_tract.py` was **removed** once the
> production loader (`backend/etl/load_cmhc_tracts.py`) landed and was validated. Its
> findings are preserved below and in git history; the production loader is now the
> single authoritative ingestion path.

The original spike demonstrated the Python ingestion path:

- `--dry-run` parsed an embedded sample CSV and printed a coverage report
  (real / suppressed / missing) — proving the parse + coverage logic **offline**.
- Live mode built the HMIP `TableMapChart` CSV-export URL (params mirroring the `cmhc`
  R package), fetched a CT-breakdown table for the Toronto CMA, parsed it (marking
  `**`/blank cells as suppressed), and reported per-metric tract coverage.

**Empirical finding (2026-05-30, updated): the CSV data endpoint IS reachable.**
An earlier draft of this note said a plain HTTP pull fails. That is true only for the
*interactive* `TableMapChart` page (a JavaScript SPA that returns no data to a `GET`),
but that is not the real data path. CMHC's **`ExportTable` endpoint works from this
environment**, verified directly:

- `POST https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable`
  with form fields `TableId`, `GeographyId`, `GeographyTypeId`, `exportType=csv`
  returned **HTTP 200 + real CSV** (Toronto CMA `GeographyId=2270`,
  `GeographyTypeId=3`, `TableId=1.9.3` → real "Under Construction Inventory by
  Intended Market" monthly series, 1990–2026). **No auth cookie was required.**
- Geography type codes (from the `cmhc` package's `cmhc_region_params_from_census`):
  Canada=1, Province=2, Metropolitan(CMA)=3, Census Subdivision=4, Survey Zone=5,
  Neighbourhood=6, **Census Tract=7**.

**The catch (why Phase A is still a milestone, not a one-liner):** the census-tract
breakdown is **encoded in the table code**, not a free parameter. Adding
`BreakdownGeographyTypeId=7` to table `1.9.3` was **ignored** — it returned the
identical CMA-total series. Real CT rows require:

1. mining the `cmhc` package's bundled table list for the **CT-specific TableCode**
   per SCSS/RMS series (the package maps survey/series/breakdown → a specific code);
2. covering **all CMAs that contain GTA tracts** (the 1,334 tracts span CTUID prefixes
   535/532/537 — multiple CMAs, not just Toronto 2270);
3. parsing CMHC's **multi-section, latin1, quality-coded** CSV (the `cmhc` package
   spends ~150 lines on this: `$1,234` comma handling, "- Quality" columns, header
   detection);
4. mapping CMHC's returned CT **GeoUIDs to our CTUIDs**; and
5. **validating** the result against known-good CMHC figures before labeling anything
   "real."

**Decision update: the SCSS portion of Phase A is shipped.**
Feasibility is now *confirmed* (real data is reachable here), which removes the biggest
unknown — but doing it correctly is a real data-pipeline effort, and shipping
reverse-engineered values without the validation step (item 5) would violate the
project's honesty principle. The labeled inheritance/allocation fallback stays in the
meantime. A follow-up can start from the verified `ExportTable` contract above instead
of from zero.

The production loader supersedes the spike — run it instead:

```bash
python backend/etl/load_cmhc_tracts.py --self-test     # offline parser check
python backend/etl/load_cmhc_tracts.py --generate-csv  # live pull + validation
```

The single most reliable reference path remains the `cmhc` R package:

```r
library(cmhc)
get_cmhc(survey="Scss", series="Completions", dimension="Dwelling Type",
         breakdown="Census Tracts",
         geo_uid=get_cmhc_geography("CT", region="Toronto"), year=2024)
```

## Implemented integration and remaining work

Recommended **layered, count-first** rollout:

1. **Phase A — SCSS starts/completions: implemented.** The production loader writes
   tract values and per-field source labels, validates all slices, and retains the
   municipal allocation only where no published tract value exists. Real tract
   `rental_universe` remains a follow-up.
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

Continue with tract RMS and `rental_universe` as a follow-up. Preserve the current
validated SCSS ingestion and survey-zone/municipality fallback chain; do not remove
fallbacks for suppressed or unavailable cells.
