# Phase A: Real CMHC census-tract data — implementation plan

Status: **plan + verified acquisition recipe.** Every fact below was confirmed by
direct HTTP calls to HMIP and cross-checked against CMHC's own published totals
(2026-06-01). Nothing here is assumed.

## Goal

Serve **real** CMHC Starts & Completions Survey (SCSS) census-tract values where
CMHC publishes them, labeled *official*, and keep the existing renter-share
**allocation** as a clearly-labeled *estimate* only for tracts CMHC does not
cover. This is an honest, per-tract real-vs-estimated split (consistent with the
field-level provenance already shipped for census metrics).

Scope is **SCSS counts** (starts, completions, under-construction). RMS
rates/rents (vacancy, average rent) are out of scope here — they are heavily
suppressed at CT level and remain inherited from the parent municipality.

## Verified acquisition recipe

### Endpoint
`POST https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable`,
form-encoded, fields:
`TableId`, `GeographyId`, `GeographyTypeId=3` (CMA), `ForTimePeriod.Year`,
`Frequency=Annual`, `exportType=csv`. Returns latin1 multi-section CSV. No cookie.

### Census-tract table codes (the `.11` suffix = "Census Tracts" breakdown)
Confirmed against the `cmhc` R package's bundled table list and by live pulls:

| Metric | CT TableId | Published-total TableId | Verified |
| --- | --- | --- | --- |
| housing_starts_total | `1.1.1.11` | `1.1.1.3` | yes — sum == published total, all slices |
| housing_completions | `1.1.2.11` | `1.1.2.3` | yes — sum == published total, all slices |
| units_under_construction | — | — | **dropped**: CT table code not confirmed (`1.4.1.11` is actually "Starts by Intended Market", not under-construction) |

(The earlier failure used `1.1.2`, a CSD-level archived stub returning 0 rows.
The `.11` breakdown suffix is mandatory. Under-construction was dropped rather
than shipped on a guess; only the two validated metrics are included.)

### GTA spans three CMHC CMAs (METCODEs), confirmed by direct probe
| CMA | METCODE (GeographyId) | Our CTUID prefix | Municipalities |
| --- | --- | --- | --- |
| Toronto | `2270` | 535 | Toronto, Mississauga, Brampton, Markham, Vaughan, ... |
| Oshawa | `2240` | 532 | Oshawa, Whitby, Clarington |
| Hamilton | `2320` | 537 | Burlington |

### GeoUID mapping (verified)
CMHC returns **short** CT ids (`0001.00`), not full CTUIDs. Map by prepending the
CMA's 3-char prefix: `535` + `0001.00` = `5350001.00` (our CTUID). For Toronto,
all **582/582** of our tracts matched. No external translation table needed.

### Coverage (real numbers, from the actual generated CSV)
- **1,213 of 1,334 tracts (90.9%)** have CMHC SCSS CT data across the 3 CMAs.
  The other ~9% fall outside CMHC's CMA survey boundaries — they keep the
  allocation estimate.
- Generated `cmhc_ct_metrics.csv`: **7,921 rows**, years 2018–2024 (starts) and
  2018–2022 (completions; 2023–2024 not yet published by CMHC — honestly absent,
  not zero). Zero is a real value (no construction) distinct from "not covered".
- The CSV is filtered to our seed's tracts, so a CMA's CSV subtotal is slightly
  below the published CMA total (e.g. Toronto starts 2023: our 535-tracts sum to
  47,098; CMHC's full Toronto CMA = 47,428; the 330-unit / 32-tract gap is
  CMHC tracts outside our GTA seed — reconciled exactly).

### Validation (the step that proves it is real, not fabricated)
For Toronto 2023, **sum of CT `All` values = 47,428**, which **exactly equals**
CMHC's published Toronto total (table `1.1.1.3`, Ontario row = 47,428). This
internal-consistency check MUST be run per CMA per year and must match before any
data is committed or labeled official.

## Build plan

### Step 1 — ETL acquisition (this PR)
1. `backend/etl/load_cmhc_tracts.py`:
   - Verify the under-construction table code/title first; drop it if unconfirmed.
   - For each (CMA, metric, year 2018–2025): POST ExportTable, parse the latin1
     CSV's `All` column, prefix-map short id → CTUID, keep only our tracts.
   - **Built-in validation**: for each (CMA, year), assert `sum(CT All) ==`
     the CMA published total from `1.1.1.3`; abort/flag on mismatch.
   - Write `backend/app/data/cmhc_ct_metrics.csv` (geoid, year, metric columns).
   - Real network is required to regenerate; tests use a **committed fixture
     CSV** (small, real rows), never synthetic sample data presented as real.
2. Commit the loader + the generated CSV + this doc. Report true coverage.

### Step 2 — API + UI integration (separate PR)
1. Schema/seed: load CT SCSS rows into a per-tract store keyed by (geoid, year).
2. `routes.py` map-data/compare/summary for SCSS count metrics in tract mode:
   - If a real CT value exists → serve it; `data_quality` = **official**
     ("CMHC census-tract value").
   - Else → keep the renter-share allocation; `data_quality` = **estimated**
     ("CMHC (estimated tract allocation)").
   - Domain/legend computed over the served values.
3. Detail panel + badge: per-tract provenance reflects official vs estimated;
   "Not available" only when neither exists.
4. Tests: real-vs-estimated selection, validation invariant, mixed-coverage
   municipality, year switching. Full verification (pytest, build, Playwright).

### Out of scope / explicitly deferred
- RMS rates/rents at CT (suppression-heavy) — stays inherited.
- Monthly granularity — annual only.
- Auto-refresh; the CSV is regenerated manually via the ETL like
  `statcan_ct_metrics.csv`.

## Honesty guardrails (lessons from the first attempt)
- Never present parser self-test sample data as real CMHC output.
- Never write a coverage/row number that wasn't produced by a real run.
- The sum-vs-published-total validation is a hard gate before committing data.
- If the live endpoint is unavailable in a session, say so and stop — do not
  synthesize.
