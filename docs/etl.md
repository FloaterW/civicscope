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
