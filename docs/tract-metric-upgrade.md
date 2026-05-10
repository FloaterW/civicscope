# Official Census Tract Metric Upgrade

## Current State

CivicScope currently ships official 2021 Statistics Canada census tract geometries and estimated tract metrics derived from each tract's parent municipality. This keeps the demo usable offline while avoiding fake precision in the UI.

## Target State

Replace packaged tract estimates with official tract-level Census Profile values for:

- population
- previous population
- median household income
- median monthly shelter cost for rented dwellings
- tenant households
- tenant shelter-cost burden

## Recommended Source

Use the Statistics Canada 2021 Census Profile comprehensive download for census tracts, then normalize it into the CivicScope metric CSV format.

The existing metric loader already supports this once a normalized CSV is available:

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
- Preserve the current UI data-quality badge, but change the tract badge from estimated to official only after the tract metric seed/database has official values.
- Keep rounded display precision. Census tract estimates and official profile values should not be shown with false precision.

## Why Not Treat This As Done Yet

Statistics Canada's per-tract SDMX dataflow advertises a census tract profile flow, but tract geography identifiers include periods. In local testing, direct per-tract SDMX key URLs returned `404` for dotted tract DGUID values, so the comprehensive download plus normalization path is the safer reproducible route.
