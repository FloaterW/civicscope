# CMHC Data Integration Design

**Date:** 2026-05-10
**Status:** Approved
**Scope:** Add CMHC Rental Market Survey and Starts & Completions Survey data to the CivicScope dashboard.

## Summary

Integrate CMHC housing market data into CivicScope as a new data source alongside existing Statistics Canada Census Profile metrics. This adds vacancy rates, average rents (by bedroom type), turnover rates, availability rates, rental universe counts, housing starts (by dwelling type), housing completions, and units under construction. Data is fetched from CMHC's HMIP portal internal API endpoints and cached into a packaged seed file.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Metric scope | Full CMHC suite (vacancy, rents, turnover, availability, universe, starts, completions) | Maximizes the value of the integration |
| Map metric selector | Grouped dropdown (Census Profile / CMHC Rental Market) using `<optgroup>` | Single-dropdown interaction, visually separated data sources |
| Year handling | Year selector defaulting to most recent available year; Census metrics locked to 2021, CMHC metrics vary by year | Shows current data while acknowledging Census is a point-in-time snapshot |
| Geography levels | Both municipality (CSD) and census tract, best effort | CMHC CSD codes map to existing GEOIDs; tract data available within Toronto CMA |
| Data sourcing | Fetch-and-cache to seed file | Matches existing ETL pattern; dashboard works offline; survives HMIP endpoint changes |
| Architecture | Separate `cmhc_metrics` table | Clean data source separation; independent update cadence; easy to modify or drop |

## Data Model

### New table: `cmhc_metrics`

```
cmhc_metrics
├── id                        INT, PK
├── geoid                     VARCHAR(20), FK → geographies.geoid, indexed
├── year                      INT, indexed
│
│  ── Rental Market Survey ──
├── vacancy_rate              FLOAT, nullable
├── average_rent_total        FLOAT, nullable  (all bedroom types)
├── average_rent_bachelor     FLOAT, nullable
├── average_rent_1br          FLOAT, nullable
├── average_rent_2br          FLOAT, nullable
├── average_rent_3br_plus     FLOAT, nullable
├── turnover_rate             FLOAT, nullable
├── availability_rate         FLOAT, nullable
├── rental_universe           INT, nullable    (total surveyed rental units)
│
│  ── Starts & Completions Survey ──
├── housing_starts_total      INT, nullable
├── housing_starts_single     INT, nullable
├── housing_starts_semi       INT, nullable
├── housing_starts_row        INT, nullable
├── housing_starts_apartment  INT, nullable
├── housing_completions       INT, nullable
├── units_under_construction  INT, nullable
│
└── UNIQUE(geoid, year)
```

### Model file: `backend/app/models/cmhc_metric.py`

Follows the same pattern as `metric.py`: FK to `geographies.geoid` with `ondelete="CASCADE"`, `(geoid, year)` unique constraint, all metric fields nullable to handle suppressed data.

### Geography model update

`Geography` gains a `cmhc_metrics` relationship alongside the existing `metrics` relationship.

### Migration: `0002_add_cmhc_metrics.py`

Standard Alembic migration to CREATE TABLE `cmhc_metrics` with the columns above plus indexes on `geoid` and `year`.

### Data coverage

| Field group | Municipality (CSD) | Census tract |
|-------------|-------------------|--------------|
| Rental Market Survey (vacancy, rents, turnover, availability, universe) | Available | Available within Toronto CMA |
| Starts & Completions (starts, completions, under construction) | Available | Not available (NULL) |

## ETL Pipeline

### New script: `backend/etl/load_cmhc.py`

Fetches data from CMHC's HMIP portal internal API endpoints. The HMIP portal serves data to its frontend via internal HTTP endpoints that return CSV. No authentication required.

**HMIP portal endpoints:**
- Export URL pattern: `https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable`
- Parameters: `TableId` (survey table ID), `GeographyId` (area code), `GeographyTypeId` (3=CMA, 4=CSD, 7=census tract)
- The `cmhc` R package (github.com/mountainMath/cmhc) documents the endpoint structure and table IDs.

**Two survey fetches:**
1. Rental Market Survey: fetch at CSD level (25 municipalities) and census tract level (within Toronto CMA, GeographyId=2270)
2. Starts & Completions Survey: fetch at CSD level only

**CLI interface:**
```
python etl/load_cmhc.py --fetch-all          # Fetch all CMHC data, write to seed file
python etl/load_cmhc.py --update-seed        # Alias for --fetch-all
python etl/load_cmhc.py --from-seed          # Load packaged seed into database
python etl/load_cmhc.py --print-url          # Print HMIP endpoint URLs for debugging
python etl/load_cmhc.py --year 2023          # Fetch a specific year (default: latest available)
```

**Rate limiting:** 0.5s delay between requests (same courtesy as `load_tract_census.py`).

### Seed file: `backend/app/data/cmhc_seed.json`

Separate from `demo_seed.json` to keep CMHC data independent.

```json
{
  "metadata": {
    "source": "cmhc_hmip_rental_market_and_starts_completions",
    "years": [2021, 2022, 2023, 2024],
    "fetched_at": "2026-05-10T...",
    "notes": [
      "Rental Market Survey data from CMHC Housing Market Information Portal.",
      "Starts and Completions Survey data from CMHC HMIP.",
      "Census tract rental market data covers tracts within the Toronto CMA.",
      "Starts and completions are available at municipal level only."
    ]
  },
  "metrics": [
    {
      "geoid": "3520005",
      "year": 2024,
      "vacancy_rate": 2.1,
      "average_rent_total": 1850,
      "average_rent_bachelor": 1350,
      "average_rent_1br": 1650,
      "average_rent_2br": 1950,
      "average_rent_3br_plus": 2250,
      "turnover_rate": 12.5,
      "availability_rate": 3.2,
      "rental_universe": 45000,
      "housing_starts_total": 5200,
      "housing_starts_single": 200,
      "housing_starts_semi": 50,
      "housing_starts_row": 350,
      "housing_starts_apartment": 4600,
      "housing_completions": 4800,
      "units_under_construction": 18000
    }
  ]
}
```

### Seed loading

`seed.py` updated to also load `cmhc_seed.json` after loading `demo_seed.json`. Uses the same skip-if-exists / force-reseed logic: if `CmhcMetric` rows exist and `force=False`, skip. If `force=True`, delete and reload.

## API Changes

### Metric registration (`metric_calculations.py`)

New entries in `VALID_METRICS`:
```
vacancy_rate, average_rent_total, average_rent_bachelor, average_rent_1br,
average_rent_2br, average_rent_3br_plus, turnover_rate, availability_rate,
rental_universe, housing_starts_total, housing_starts_single, housing_starts_semi,
housing_starts_row, housing_starts_apartment, housing_completions,
units_under_construction
```

New entries in `METRIC_ALIASES`:
```
vacancy → vacancy_rate
starts → housing_starts_total
completions → housing_completions
rent_cmhc → average_rent_total
turnover → turnover_rate
availability → availability_rate
universe → rental_universe
```

A helper set `CMHC_METRICS` identifies which metric keys belong to the CMHC table, used by the API to determine which table to query.

### `metric_value()` update

Accepts an optional `cmhc_row` parameter. When the metric key is in `CMHC_METRICS`, reads from `cmhc_row` instead of the Census `row`.

### Year resolution

New `resolve_cmhc_year(db, year)` function: same pattern as `resolve_year()` but queries `func.max(CmhcMetric.year)`. Used when the requested metric is a CMHC key.

### `/api/map-data` endpoint

When the requested metric is a CMHC key:
- Joins `CmhcMetric` (instead of or alongside `Metric`) on `geoid` and year
- Uses `resolve_cmhc_year()` for year resolution
- Response metadata `data_quality` and `source` reflect CMHC source
- Response metadata gains `available_years` field: a sorted list of all years present in `cmhc_metrics` for the requested geography type (e.g. `[2021, 2022, 2023, 2024]`). This powers the frontend year selector.
- Response `features[].properties` includes `cmhc_metrics` object and `cmhc_year` field

When the requested metric is a Census key, behavior is unchanged. The `available_years` field is omitted or set to `[2021]`.

### `/api/summary` endpoint

Extended to include CMHC summary values when data exists:
- `vacancy_rate`: weighted average by rental universe
- `housing_starts_total`: straight sum across geographies
- `housing_completions`: straight sum
- `average_rent_total`: weighted average by rental universe

### `/api/compare` endpoint

Serialize function extended to include `cmhc_metrics` when `CmhcMetric` data exists for the geography/year.

### `data_quality()` and `map_data_source()` updates

New branch for CMHC metrics:
```python
{
    "metric_status": "official",
    "label": "CMHC Rental Market Survey",
    "description": "CMHC Rental Market Survey and Starts & Completions Survey data from the Housing Market Information Portal."
}
```

## Frontend Changes

### Types (`types/index.ts`)

`MetricKey` union extended with all CMHC keys.

New type:
```typescript
type CmhcMetricValues = {
  vacancy_rate: number | null;
  average_rent_total: number | null;
  average_rent_bachelor: number | null;
  average_rent_1br: number | null;
  average_rent_2br: number | null;
  average_rent_3br_plus: number | null;
  turnover_rate: number | null;
  availability_rate: number | null;
  rental_universe: number | null;
  housing_starts_total: number | null;
  housing_starts_single: number | null;
  housing_starts_semi: number | null;
  housing_starts_row: number | null;
  housing_starts_apartment: number | null;
  housing_completions: number | null;
  units_under_construction: number | null;
};
```

`MapFeature` properties gain:
```typescript
cmhc_metrics?: CmhcMetricValues;
cmhc_year?: number;
```

`Summary` type extended with optional CMHC summary fields.

### Metric selector (`lib/api.ts`)

`metricOptions` entries gain a `group` field. The `<select>` renders `<optgroup>` tags:

**Census Profile group:**
- Rent burden, Affordability index, Median income, Median rent, Population, Population growth

**CMHC Rental Market group:**
- Vacancy rate, Average rent (CMHC), Housing starts, Completions, Turnover rate, Availability rate

Per-bedroom rent breakdowns and per-type starts breakdowns are shown in the detail panel only, not in the map selector dropdown.

### Year selector

Small dropdown next to the metric selector:
- When a Census Profile metric is selected: locked to 2021, visually disabled
- When a CMHC metric is selected: shows available CMHC years, defaults to most recent
- Available years sourced from `metadata.available_years` in the map-data API response

### `formatMetric()` updates

| Metric type | Format |
|-------------|--------|
| `vacancy_rate`, `turnover_rate`, `availability_rate` | `X.X%` |
| `average_rent_*` | Currency (`$1,850`) |
| `housing_starts_*`, `housing_completions`, `units_under_construction`, `rental_universe` | Integer with commas |

### Detail panel

When a geography is selected and CMHC data exists, a "CMHC Rental Market" subsection appears below the existing Census Profile metrics. Shows the full breakdown:
- Vacancy rate, availability rate, turnover rate
- Average rents by bedroom type (bachelor, 1BR, 2BR, 3BR+, total)
- Housing starts by type (single, semi, row, apartment, total) — municipalities only
- Completions, units under construction — municipalities only
- Rental universe

### Summary panel

Adds vacancy rate and housing starts total to the summary cards when CMHC data is loaded.

### Comparison panel

CMHC metrics included in comparison chart bars when a CMHC metric is selected.

## Testing

### Backend tests

- Model creation and unique constraint enforcement for `CmhcMetric`
- ETL parsing: mock HMIP CSV responses, verify correct field mapping
- API: `/api/map-data?metric=vacancy_rate` returns CMHC data with correct metadata
- API: CMHC metrics return correct year resolution independent of Census year
- API: summary and compare endpoints include CMHC data when available
- Null handling: suppressed CMHC values don't crash serialization

### Frontend tests (`dashboard.spec.ts`)

- Grouped metric selector renders `<optgroup>` tags
- Selecting a CMHC metric loads CMHC map data with correct domain
- Year selector appears and is interactive when CMHC metric is selected
- Year selector is disabled when Census metric is selected
- Detail panel shows CMHC subsection when geography has CMHC data
- Switching between Census and CMHC metrics doesn't produce API errors

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| HMIP portal endpoints change or break | Seed file decouples the dashboard from live HMIP access; dashboard works from cached data |
| CMHC suppresses data for some tracts/municipalities | All fields nullable; "No data" display pattern already established |
| Starts/completions unavailable at tract level | Fields are NULL for tracts; frontend handles gracefully |
| Year selector adds UI complexity | Locked/disabled state for Census metrics keeps it simple; default to latest year |
| Large seed file from multi-year CMHC data | Separate `cmhc_seed.json` keeps it isolated; GZip middleware already active |

## Files to Create

| File | Purpose |
|------|---------|
| `backend/app/models/cmhc_metric.py` | CmhcMetric SQLAlchemy model |
| `backend/alembic/versions/0002_add_cmhc_metrics.py` | Migration to create cmhc_metrics table |
| `backend/etl/load_cmhc.py` | ETL script for HMIP portal data fetching |
| `backend/app/data/cmhc_seed.json` | Packaged CMHC seed data |

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Export CmhcMetric |
| `backend/app/models/geography.py` | Add cmhc_metrics relationship |
| `backend/app/services/seed.py` | Load cmhc_seed.json alongside demo_seed.json |
| `backend/app/services/metric_calculations.py` | Add CMHC metric keys, aliases, CMHC_METRICS set, update metric_value() |
| `backend/app/services/summary.py` | Add CMHC weighted averages to build_summary() |
| `backend/app/api/routes.py` | Add resolve_cmhc_year(), update map-data/summary/compare endpoints, update data_quality/map_data_source |
| `frontend/types/index.ts` | Add CmhcMetricValues type, extend MetricKey, update MapFeature/Summary |
| `frontend/lib/api.ts` | Add grouped metricOptions, update formatMetric(), add CMHC year resolution |
| `frontend/components/*` | Update metric selector (optgroup), add year selector, update detail/summary/comparison panels |
| `frontend/tests/dashboard.spec.ts` | Add CMHC-specific regression tests |
