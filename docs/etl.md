# ETL Notes

## Geography Loader

`backend/etl/load_geo.py` loads Greater Toronto Area census subdivision boundaries from the Statistics Canada 2021 Cartographic Boundary Files ArcGIS service.

Useful commands:

```bash
docker compose exec backend python etl/load_geo.py --print-url
docker compose exec backend python etl/load_geo.py --update-seed
docker compose exec backend python etl/load_geo.py
```

The loader filters the official CSD layer to the 25 GTA municipalities used by the dashboard, normalizes CSDUIDs into `geographies.geoid`, calculates bounding boxes, and writes an `etl_runs` record.

Use `--update-seed` when the packaged offline demo file should be refreshed from the official boundary service. Use the plain loader command when the database should be refreshed. Database refreshes also sync `geographies.geom` from the stored GeoJSON so PostGIS map operations remain current.

Source:

- Statistics Canada 2021 Cartographic Boundary Files service: `https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer/9`

## Census Tract Loader

`backend/etl/load_tracts.py` loads Statistics Canada 2021 cartographic census tract boundaries and filters them to the current GTA municipality set by tract representative point. Packaged tract Census Profile metrics are official 2021 Statistics Canada values from the normalized DF_CT extract; source-suppressed values remain null.

Useful commands:

```bash
docker compose exec backend python etl/load_tracts.py --print-url
docker compose exec backend python etl/load_tracts.py --from-seed
docker compose exec backend python etl/load_tracts.py --update-seed --geojson /app/data/statcan_ct.geojson
docker compose exec backend python etl/load_tracts.py
```

Use `--from-seed` when an existing local database already has municipality rows and needs the packaged census tract rows added without recreating the Postgres volume. `--update-seed` refreshes geometry only and preserves every official metric for matching CTUIDs. It aborts on identifier drift. `--replace-metrics-with-estimates` is an explicit demo-only escape hatch and must not be used for publication data.

Source:

- Statistics Canada 2021 Cartographic Boundary Files census tract service: `https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer/11`

See `tract-metric-upgrade.md` for the completed official tract metric upgrade notes and remaining follow-ups.

## Census Metric Loader

`backend/etl/load_census.py` supports four production-facing workflows:

1. Generate a Statistics Canada Census Profile WDS URL for selected CSDUIDs and characteristic IDs.
2. Fetch official 2021 Census Profile metrics for all GTA municipalities.
3. Refresh packaged seed metrics from the official API.
4. Load a normalized CSV extract into the `metrics` table.

Useful commands:

```bash
docker compose exec backend python etl/load_census.py --print-profile-url 3520005 3521005 --characteristics 1 2 229 1476 1478 1480
docker compose exec backend python etl/load_census.py --official-gta
docker compose exec backend python etl/load_census.py --update-seed
docker compose exec backend python etl/load_census.py --csv /app/data/statcan_metrics.csv
```

Official characteristic IDs used by CivicScope:

| Field | Census Profile characteristic |
| --- | --- |
| `population` | `1` - Population, 2021 |
| `previous_population` | `2` - Population, 2016 |
| `median_income` | `229` - Median total income of household in 2020 |
| `renter_households` | `1476` - Total tenant households in non-farm, non-reserve private dwellings |
| `rent_burden_pct` | `1478` - Percent of tenant households spending 30 percent or more of income on shelter costs |
| `median_rent` | `1480` - Median monthly shelter costs for rented dwellings |

Expected CSV columns can use either CivicScope names or common aliases:

```csv
csduid,year,median_household_income,median_monthly_rent,population_2021,population_2016,tenant_households,shelter_cost_burden_pct
3520005,2021,88000,1850,2794000,2731571,650000,43.0
```

The loader calculates `affordability_index`. Official/suppressed rent burden is preserved in storage; a labeled fallback is calculated only at API serialization time when rent and income are available.

Source:

- Statistics Canada 2021 Census Profile Web Data Service: `https://www12.statcan.gc.ca/wds-sdw/2021profile-profil2021-eng.cfm`

## Migrations And Map Payload Modes

Alembic migrations create the core tables and the native `geographies.geom geometry(GEOMETRY, 4326)` column. The migration backfills `geom` from `geographies.geometry` and adds `ix_geographies_geom` as a GiST index.

`GET /api/map-data` supports:

- `detail=full`: stored GeoJSON geometry, best for export or debugging.
- `detail=display`: PostGIS `ST_SimplifyPreserveTopology` output when available, best for interactive map rendering.
- `type=municipality` or `type=census_tract`: geography level selection for the dashboard map and summaries.

The frontend uses `detail=display` by default so the map remains responsive while the database keeps higher-detail municipal and tract boundaries. In SQLite tests, the API falls back to Python GeoJSON compaction.

The map payload includes all relevant values plus a per-metric metadata catalog. The frontend caches one payload per geography/data-family/year and changes metrics in that family locally. A different CMHC year, geography level, or Census/CMHC family triggers a new request.

## Publication Safety

Canonical seed refreshes are fail-closed and atomic. Census tract geometry and metric
loaders reject missing, unexpected, duplicate, or wrong-vintage identifiers before
mutating the database or seed. CMHC tract slices must reconcile to their published CMA
totals. A partial network result can only be written with `--allow-partial` to an explicit,
noncanonical diagnostic output path; it cannot update the database or overwrite a
packaged seed.

## Transit Loader

`backend/etl/load_transit.py` builds route and tract-score artifacts from the configured
TTC, MiWay, GO Transit, Durham Region Transit, and Brampton Transit GTFS feeds. Canonical
publication requires all configured feeds. Downloads are refreshed after 24 hours (or
with `--refresh`), are staged atomically, and never replace a usable cached feed on a
failed request. `--skip-download` is the explicit offline-cache mode.

Every canonical generation also writes `app/data/transit_manifest.json` with agency
coverage, timestamps, method parameters, and artifact hashes. As with the other loaders,
`--allow-partial` requires an explicit noncanonical output and cannot update the database.

New transit candidates identify the calculation as
`routes-within-800m-all-tracts-v2`: percentile normalization includes every supported
tract, including zero-route tracts. The manifest explicitly records that the importer
uses all trips in each feed without evaluating service calendars. A feed retrieval
date is not a claim that those routes operate on that date. This method/version change
applies to newly generated candidates; it does not revise the published snapshot.

## Isolated refreshes and incident handling

Run from the repository root, with the backend dependencies installed:

```bash
python backend/etl/refresh_candidate.py --source census --output out/candidate-census --diagnostics-output out/diagnostics-census
```

Use new, separate directories. The candidate appears only after complete source
coverage and validation pass. The diagnostics directory is also emitted after an ETL
failure, containing step status, exception types, HTTP status, hashed request identifiers
and staged file hashes. It excludes response bodies, request URLs, subprocess output,
headers and environment values. Failed staged hashes are evidence only, never proof
that the corresponding files are fit to publish. A setup failure before the refresh
starts may have no diagnostics artifact.

Census reads make at most three attempts for transient network failures or HTTP
408/429/500/502/503/504. Delays are 1 and 2 seconds unless a valid `Retry-After` asks
for longer. Both seconds and HTTP dates are supported; a requested delay above
30 seconds aborts the candidate instead of retrying early. Certificate, permanent
HTTP, schema, suppression-flag and coverage failures are not retried. See
[HTTP Retry-After semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).

The data-refresh workflow retains candidates and sanitized diagnostics for 30 days.
Transit candidates also retain the exact downloaded public GTFS ZIPs under
`source-inputs/`, with their hashes, source URLs and retrieval dates in
`source-inputs.json`. Missing or mismatched ZIPs block candidate export. These are
review inputs, not application assets: preserve upstream attribution and terms;
do not commit or serve them as dashboard downloads. Download evidence before its
Actions artifact expiry when review will take longer. Hashes alone cannot reproduce
inputs that have expired upstream.

For transit review, validate calendar coverage and exceptions from the retained
archives before accepting a service-date interpretation. GTFS defines weekly service
dates in `calendar.txt` and additions/removals (or all dates) in `calendar_dates.txt`.
See the [GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/#calendartxt).
Also inspect every configured agency, tract coverage, changed counts versus changed
normalization, overlay consistency, and zero/missing semantics. “Complete” coverage
means the configured feed list, not every agency operating in the GTA.

Production monitoring maintains separate bot-owned `Source verification - census`,
`Source verification - cmhc`, and `Source verification - transit` issues. A stale or
unknown source reported by a reachable API opens its own incident; repeated unchanged
states create no new comments. An unavailable status endpoint is indeterminate and
cannot close any source incident. The old combined issue is retired only after all
states are known and every outstanding failure has a confirmed replacement issue.
Newly created issues are confirmed directly by their returned URL, avoiding GitHub
search-index delays during migration.
Availability and refresh-execution incidents remain separate from source freshness.

Candidate validation does not update production or silently mark a source verified.
Review and promote only the relevant source's artifacts/manifest entry in a separate
data change; never copy a candidate's whole manifest over later reviews of other
sources. The [November 20 review](source-refresh-review-2026-11-20.md) records the
existing candidates' dispositions.
