# Data Dictionary

## geographies

| Column | Meaning |
| --- | --- |
| `id` | Internal primary key. |
| `geoid` | Stable geography identifier. Municipality rows use official 2021 CSDUID values such as `3520005` for Toronto. Census tract rows use official CTUID values such as `5350001.00`. |
| `name` | Display name. |
| `type` | Geography type: `municipality` or `census_tract`. |
| `county` | Region-like display field. Municipality rows store upper-tier region names; census tract rows store the assigned parent municipality. This column is retained from the original schema and should be renamed to `region` or split into parent fields in a future migration. |
| `state` | Province/region code, currently `ON`. |
| `geometry` | Stored GeoJSON geometry retained for provenance, portability, and seed loading. |
| `geom` | Native PostGIS geometry in EPSG:4326, backfilled from `geometry` and indexed with GiST for spatial operations and map simplification. |
| `bbox` | Bounding box used by the frontend when selecting a geography. |
| `geometry_source` | Human-readable provenance note. |

## metrics

| Column | Meaning |
| --- | --- |
| `geoid` | Joins to `geographies.geoid`. |
| `year` | Metric vintage. |
| `median_income` | Median household income in dollars. |
| `median_rent` | Median monthly gross rent in dollars. |
| `population` | Current population estimate. |
| `previous_population` | Prior comparison population estimate. |
| `renter_households` | Renter household count used as a weight. |
| `rent_burden_pct` | Percent of tenant households spending 30 percent or more of income on shelter costs. Stored as the **official** Statistics Canada 2021 Census Profile value, or **null** when Statistics Canada suppressed it. No estimate is ever persisted to the database. When the official value is missing the API returns a clearly-labeled **estimate** derived from rent and income (see Field-level provenance). |
| `affordability_index` | Derived score where 100 equals the 30 percent rent-to-income threshold; higher is more affordable. Computed from median rent and income, not a published Statistics Canada value. |
| `dwellings_*`, `owner_households` | Dwelling-type and tenure counts. **Populated for municipalities only.** Statistics Canada does not publish these at tract level in the packaged DF_CT extract, so they are null for census tracts and the tract Housing Stock section is hidden. |

## Field-level provenance (`data_quality`)

Every serialized `metrics` object includes a `data_quality` map giving the provenance of each census field so the UI never implies an estimated or missing number is official:

| Status | Meaning | UI treatment |
| --- | --- | --- |
| `official` | Published Statistics Canada 2021 Census Profile value. | Shown plainly. |
| `derived` | Calculated from published inputs, such as affordability, rent-to-income, population growth, or transit access. | Shown with a derived indicator and formula/source explanation. |
| `estimated` | Official value was suppressed; a labeled fallback was computed (currently only `rent_burden_pct`). | Value shown with an "est." flag and an explanatory note. |
| `unavailable` | Suppressed/missing and not estimable; value is null. | Rendered as "Not available". |
| `low_confidence` | Derived value off an unreliable base (currently `population_growth_pct` where the 2016 base population is below 100). | Value shown with a caution flag and note. |

The map-data metadata `data_quality.metric_status` summarizes the selected metric for the badge: `official`, `derived`, `estimated` (CMHC allocated to tracts), `mixed` (multiple provenance classes), or `zone` (CMHC survey-zone values).

## Formulas

`rent_to_income_ratio = (median_rent * 12) / median_income`

`affordability_index = 100 * (0.30 / rent_to_income_ratio)`

`population_growth_pct = ((population - previous_population) / previous_population) * 100`

When the prior (2016) base population is below 100, the result is flagged `low_confidence`: a handful of GTA tracts were largely undeveloped in 2016, so an ordinary increase becomes an extreme percentage that must not be read as a stable trend.

`rent_burden_pct` estimated fallback (used only when the official value is suppressed, and always labeled `estimated`):

`estimate = clamp(18 + (rent_to_income_ratio - 0.20) * 150, 12, 65)`

Municipal geometries in the seed data come from Statistics Canada 2021 cartographic census subdivision boundaries filtered to GTA municipalities. They can now be refreshed with `backend/etl/load_geo.py`.

Packaged seed metrics use official Statistics Canada 2021 Census Profile values for the selected GTA municipalities. Refresh them with `backend/etl/load_census.py --update-seed`, or refresh the database directly with `backend/etl/load_census.py --official-gta`.

Census tract geometries in the seed data come from Statistics Canada 2021 cartographic census tract boundaries. `backend/etl/load_tracts.py` filters candidate tract features to the current GTA municipalities by tract representative point and assigns them to parent municipalities. Tract Census Profile metrics in the packaged seed are official 2021 Statistics Canada values from the normalized DF_CT extract, stored canonically in `backend/app/data/statcan_ct_metrics.csv` (1,334 rows). Source-suppressed values are preserved as null — the seed bakes in **no** estimates. The exact gaps in the canonical CSV are: `rent_burden_pct` 38, `median_rent` 18, `median_income` 6, `renter_households` 8, `previous_population` 2, `population` 1.

Refresh the packaged seed's tract metrics from the canonical CSV (null-preserving, no estimation) with `python backend/etl/load_tract_census.py --from-csv app/data/statcan_ct_metrics.csv`, or re-fetch the CSV from Statistics Canada with `--generate-csv`. On startup the API compares the database against the packaged seed and automatically re-seeds if a stale volume holds superseded values, so official data loads without manually deleting Docker volumes. `FORCE_RESEED=true` forces a rebuild.

## cmhc_metrics

Municipal CMHC metrics are stored by municipality/year. Census-tract starts and completions use published tract rows where available, parent-tract allocations after boundary splits, and renter-share municipal allocation only as a final fallback. Vacancy and average rent use official CMHC survey-zone values for matched tracts; unmatched tracts and other RMS fields use a disclosed parent-municipality fallback. API and CSV output carry per-field source labels.

Municipality-level integer totals allocated to tracts use deterministic largest-remainder
allocation. Published tract values are reserved first and only the residual is allocated,
so the displayed tract integers conserve each available parent total exactly.

## Transit snapshot

`app/data/transit_manifest.json` records the packaged GTFS method, buffer distance,
coverage status, included and missing agencies, build timestamp, feed timestamps when
known, and SHA-256 checksums for the route and score artifacts. The current snapshot is
partial: TTC, MiWay, GO Transit, and Durham Region Transit are included; Brampton Transit
is explicitly missing. Transit fields are `derived`, not agency-published measures.
