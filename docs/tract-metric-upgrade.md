# Official Census Tract Metric Upgrade

## Current State

CivicScope ships official 2021 Statistics Canada census tract geometries and official tract-level Census Profile metrics from a normalized DF_CT extract (`backend/app/data/statcan_ct_metrics.csv`, 1,334 rows). The packaged seed mirrors that CSV exactly: official values verbatim, source-suppressed values preserved as null, and **no estimates baked into the data**.

Rather than a blanket "official" label, the API exposes **field-level provenance** so the UI never overclaims:

- `official` — published Statistics Canada value.
- `estimated` — official value suppressed; a labeled fallback (rent burden from rent and income) is computed at serialization time.
- `unavailable` — suppressed/missing; rendered as "Not available".
- `low_confidence` — population growth computed off a 2016 base below 100; flagged because a near-empty base turns ordinary growth into an extreme percentage.

The map badge reports `official`, `mixed` (tract rent burden), or `estimated` (CMHC allocated to tracts) for the selected metric.

### Stale-data safety

On startup the API compares the database against the packaged seed and auto-reseeds when a stale Docker volume holds superseded values (this fixed a volume that still carried the older `packaged_seed_census_tracts_estimated_metrics` load). `FORCE_RESEED=true` forces a full rebuild. No manual volume deletion required.

### Documented gaps in the canonical CSV

`rent_burden_pct` 38, `median_rent` 18, `median_income` 6, `renter_households` 8, `previous_population` 2, `population` 1. Dwelling-type/tenure characteristics are not in the DF_CT extract, so tract Housing Stock is hidden in the UI (municipalities still show it).

## Completed Scope

The packaged seed includes official tract-level values for:

- population
- previous population
- median household income
- median monthly shelter cost for rented dwellings
- tenant households
- tenant shelter-cost burden

## Source And Loader

The tract metric upgrade uses a normalized Statistics Canada 2021 Census Profile CT extract. The existing metric loader can reload it into a local database:

```bash
docker compose exec backend python etl/load_census.py --csv /app/data/statcan_ct_metrics.csv
```

Expected normalized columns:

```csv
geoid,year,median_income,median_rent,population,previous_population,renter_households,rent_burden_pct
5350001.00,2021,90500,1580,2140,1642,420,39.0
```

## Implementation Notes

- Use CTUID values such as `5350001.00` as `geoid`.
- Keep the current `geographies.type = census_tract` rows.
- Preserve nulls where Statistics Canada suppresses or omits tract values.
- Keep rounded display precision. Even official profile values should not be shown with false precision.

## Remaining Follow-Ups

- Add a reproducible download script that fetches and normalizes the CT extract end to end. (Partial: `etl/load_tract_census.py --generate-csv` fetches/normalizes; `--from-csv` syncs the seed null-preserving.)
- Rename the legacy `county` column to a clearer parent geography field in a future migration.
- Source official tract-level dwelling-type/tenure characteristics if a future DF_CT extract includes them, then re-enable the tract Housing Stock section.

Done in this iteration: null/suppressed counts are documented (see Data Dictionary), tract metrics are field-level labeled, low-confidence growth is flagged, stale-volume reseeding is bidirectional, official CMHC tract starts/completions are used where available, survey-zone vacancy/rent is used where matched, and every fallback remains explicitly labeled.
