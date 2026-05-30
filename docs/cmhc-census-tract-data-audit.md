# CMHC Census Tract Data Audit

## Question

Does CMHC publish rental market and housing supply data at the census tract level for the GTA, or is the app's inheritance/allocation approach the only option?

## Summary (corrected 2026-05)

**CMHC *does* publish both Rental Market Survey (RMS) and Starts & Completions Survey
(SCSS) data at the census tract level for the Toronto CMA.** An earlier version of
this audit incorrectly stated that tract-level CMHC data was unavailable and that
CMHC zones do not align to census tracts. Both claims were wrong. The app's current
municipality inheritance/allocation is therefore a *reasonable fallback*, not the only
option — real tract data exists and could replace much of the estimation.

The important nuance is **suppression**, not availability: at the tract level CMHC
suppresses a large share of RMS rate/rent estimates for confidentiality and
reliability, so real tract data is *sparse and patchy* for rates/rents, but much more
complete for counts.

## Findings

### Geography levels (verified against CMHC's own Help/methodology pages)

- HMIP's "Choosing a geography" help lists smaller-area geographies as **Zone, Census
  Subdivision, Neighbourhood, and Census Tract**. Census Tract is a standard selectable
  geography, including for the Toronto CMA.
- The geography hierarchy **nests on census tracts**: a CMHC Zone is "made up of one or
  many Statistics Canada Census Tract boundaries" and "zone boundaries respect CT
  boundaries"; Neighbourhoods are groupings of CTs and cannot cross zone boundaries. So
  CT → Neighbourhood → Zone → CSD is a clean containment hierarchy (each tract maps to
  exactly one zone). The earlier claim that "survey zones do not align to census tracts"
  is incorrect.

### Rental Market Survey (RMS) — rates & rents

- Vacancy rate, availability rate, turnover rate, average rent, and rental universe are
  published with a **Census Tract** breakdown for the Toronto CMA.
- **But** estimates (vacancy, rents, etc.) are released only when based on **4+
  responding entities**, and values with CV > 10% are **suppressed (`**`)**. Letter
  codes A–D indicate reliability. At tract granularity a large fraction of GTA cells are
  suppressed, made worse by a recent RMS sample reduction. So real tract rates/rents
  exist where samples are adequate (often a minority of tracts) and are suppressed
  elsewhere.
- `rental_universe` is a **count, not an estimate**, so it is released at CT even where
  rates are suppressed.

### Starts & Completions Survey (SCSS) — counts

- Starts, completions, and under-construction inventory are published at **Census
  Tract** level (observed counts, generally not CV-suppressed), so tract coverage is far
  more complete than RMS rates. CMHC notes tract/neighbourhood construction geography is
  "subject to error" because new builds occur in sometimes-unmapped areas.

### Access

- No official CMHC REST/JSON API. HMIP exports per-table **CSV**. The de-facto
  programmatic route is the **`cmhc` R package** (mountainMath), which drives HMIP's
  internal `TableMapChart` endpoints and supports CT-level queries for both RMS and SCSS.
- `open.canada.ca` CMHC datasets are CMA/CA/CSD aggregates only (not tract).
- CMHC also publishes Census Tract / Zone / Neighbourhood **boundary layers** (ArcGIS),
  so tract values can be joined to geometry on CTUID.

## What the app does today

CMHC metrics in census tract mode are **inherited** (rates) or **allocated** by
renter-household share (counts) from the parent municipality, and are clearly labeled as
estimated in the UI (badge "CMHC (estimated allocation)", "municipal rates" / "est."
notes). This is honest and functional, but it is an estimate where real CT data could be
used.

## Recommendation (layered, per metric family)

| Metric family | Finest real CMHC geography | Recommended source | Note |
| --- | --- | --- | --- |
| RMS rates (vacancy, availability, turnover) | Census Tract (suppressed when CV>10 / <4 respondents) | real CT → Neighbourhood → Zone → municipality fallback | display reliability code; mark `**` as suppressed instead of back-filling |
| RMS rents (average rent by type) | Census Tract (same suppression) | same CT → Neighbourhood → Zone fallback | zone-level real rents are well-populated for Toronto |
| RMS rental_universe (count) | Census Tract (released even when rates suppressed) | real CT value directly | should replace renter-share allocation for universe |
| SCSS counts (starts, completions, under construction) | Census Tract (observed counts) | real CT counts directly | replaces allocation; note tract attribution can be imperfect for new builds |

Practical path: ingest CT-level RMS + SCSS for GTA tracts via the `cmhc` R package (or by
replicating its `TableMapChart` CSV-export calls), joined on CTUID, and keep the current
estimation only as an explicit, labeled fallback where CMHC suppresses a value.

## Confidence / caveats

Geography availability (CT is published for RMS and SCSS) and the suppression rules are
verified against CMHC's own Help and methodology pages and corroborated by the Community
Data Program and mountainMath. The exact proportion of GTA tracts that survive RMS
suppression is qualitative ("many are suppressed") and would need confirming by actually
pulling the Toronto CT tables. See `docs/cmhc-real-tract-data-spike.md` for the spike
assessment.
