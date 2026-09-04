# CivicScope

A geospatial analytics dashboard for exploring housing affordability, income, and population patterns across Greater Toronto Area communities. Every metric shows where its data came from.

[![CI](https://github.com/FloaterW/civicscope/actions/workflows/ci.yml/badge.svg)](https://github.com/FloaterW/civicscope/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![API Docs](https://img.shields.io/badge/API-OpenAPI%20Docs-009688)](https://civicscope.onrender.com/docs)
![Next.js](https://img.shields.io/badge/Next.js-16.3-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688)
![PostGIS](https://img.shields.io/badge/PostgreSQL-PostGIS-316192)

[![CivicScope overview dashboard](docs/screenshots/overview-dashboard.png)](https://civicscope-gold.vercel.app)

## Live Demo

- **Frontend:** https://civicscope-gold.vercel.app
- **Backend API:** https://civicscope.onrender.com
- **Health check:** https://civicscope.onrender.com/health
- **API docs:** https://civicscope.onrender.com/docs

> The backend runs on Render's free tier and spins down after inactivity. The first request after idle may take ~30 seconds while the instance wakes up.

## Overview

CivicScope is a full-stack project for public-sector analytics. The backend is FastAPI with a SQLAlchemy data model on Postgres/PostGIS (Docker), packaged GTA seed data, tested API endpoints, and repeatable Statistics Canada and CMHC ETL scripts. The frontend is a Next.js dashboard with an interactive MapLibre map, municipality/census-tract switching, summary cards, a comparison chart, search, and a detail panel.

Municipal geometries use Statistics Canada 2021 cartographic census subdivision boundaries. Metric values use official Statistics Canada 2021 Census Profile characteristics for the selected GTA municipalities.

Census tract geometries use Statistics Canada 2021 cartographic census tract boundaries filtered to the selected GTA municipalities. Tract-level metrics are official Statistics Canada 2021 Census Profile values fetched via the SDMX DF_CT dataflow.

### Data provenance

The app tracks where every value comes from instead of silently filling gaps:

- Every metric carries a field-level source flag (`official` / `derived` / `estimated` / `unavailable` / `low_confidence`) that the UI shows, so a calculation or estimate is never displayed as if it were directly published.
- Source-suppressed census values render as "Not available" rather than being filled. Where the official rent-burden value is suppressed, the app shows a labeled estimate derived from rent and income.
- Tracts with a tiny 2016 base population have their growth rate flagged low-confidence, since a near-empty base turns ordinary growth into an absurd percentage.
- CMHC publishes Starts & Completions at the census-tract level for the GTA's three CMAs (Toronto, Oshawa, Hamilton). The ETL validates every slice against CMHC's published CMA total and labels published tract values `official`. Boundary-split values are `estimated_parent`; uncovered tracts use a municipal-share `estimated` fallback. Vacancy rate and average rent use CMHC survey-zone values where the tract-zone crosswalk is available, with a disclosed parent-municipality fallback elsewhere.

## Screenshots

Demo video:

[CivicScope demo walkthrough](docs/demo/civicscope-demo.webm)

Overview dashboard with GTA municipal rent burden:

![CivicScope overview dashboard](docs/screenshots/overview-dashboard.png)

Selected municipality drilldown:

![Selected Toronto municipality](docs/screenshots/selected-toronto.png)

Population growth metric view:

![Population growth metric view](docs/screenshots/population-growth.png)

Census tract map layer:

![Census tract map layer](docs/screenshots/census-tracts.png)

Regenerate screenshots from the running app:

```bash
cd frontend
npm run screenshots
```

Regenerate the demo video from the running app:

```bash
cd frontend
npm run demo:video
```

## Case Study

CivicScope answers a practical planning question: where are GTA housing affordability conditions most strained relative to local incomes, and how do those conditions differ between nearby municipalities and census tracts?

The core workflow is built for a policy analyst or planner: scan the regional overview, switch metrics, search or click a geography, inspect local affordability indicators, and compare selected areas. Official Census Profile and real CMHC values are visibly distinguished from estimated fallbacks, so it's always clear which numbers are survey-grade.

See [docs/case-study.md](docs/case-study.md) for the full project narrative.

### Documentation

- [docs/architecture.md](docs/architecture.md): system design and component overview.
- [docs/data-dictionary.md](docs/data-dictionary.md): every column, metric, provenance status, and fallback formula.
- [docs/cmhc-real-tract-data-plan.md](docs/cmhc-real-tract-data-plan.md): the CMHC census-tract acquisition recipe and validation gate.
- [docs/etl.md](docs/etl.md): ETL workflows and data refresh.
- [docs/tract-metric-upgrade.md](docs/tract-metric-upgrade.md): tract-metric upgrade notes and follow-ups.

## Architecture

```mermaid
flowchart LR
  user["Planner / policy analyst"] --> web["Next.js dashboard"]
  web --> api["FastAPI API"]
  api --> db["PostgreSQL + PostGIS"]
  migrations["Alembic migrations"] --> db
  seed["Packaged GTA seed data (validated)"] --> api
  statcan["Statistics Canada Census Profile + boundaries"] --> etl["Python ETL scripts"]
  cmhc["CMHC HMIP (Starts & Completions, validated)"] --> etl
  etl --> db
```

## Project Structure

```text
civicscope/
  backend/
    app/
    alembic/
    etl/
    tests/
  frontend/
    app/
    components/
    lib/
    types/
  docs/
    architecture.md
    case-study.md
    data-dictionary.md
    cmhc-real-tract-data-plan.md
    etl.md
    launch-checklist.md
    tract-metric-upgrade.md
    deployment.md
    demo/
    screenshots/
  docker-compose.yml
  render.yaml
  Makefile
```

## Setup

Copy the example environment file if you want local overrides. Docker Compose also has safe local defaults, so this step is optional for a first run:

```bash
cp .env.example .env
```

Production-style environment values are documented in `.env.production.example`.

Run the full stack with Docker:

```bash
docker compose up --build
```

If port `3000` is already in use, set `FRONTEND_PORT=3102` in `.env` or run PowerShell with `$env:FRONTEND_PORT='3102'` before starting Docker.

Local URLs:

- Frontend: http://localhost:3000, or your configured `FRONTEND_PORT` such as http://localhost:3102
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Run services manually. The backend requires a running PostgreSQL + PostGIS instance
(the migrations are PostGIS-specific). The easiest way is to start just the database
with Docker, then point the backend at it:

```bash
# 1. Start the PostGIS database (or use your own Postgres+PostGIS).
docker compose up -d db

# 2. Backend (DATABASE_URL must point at PostGIS; .env.example has this value).
cd backend
python -m pip install --require-hashes -r requirements-dev.lock
export DATABASE_URL="postgresql+psycopg://civicscope:civicscope@localhost:5432/civicscope"
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

> Note: without a PostGIS database, `alembic upgrade head` fails, because the schema uses
> PostGIS types and functions that SQLite does not support. (Tests are the exception:
> `pytest` uses an isolated in-memory SQLite database created from SQLAlchemy metadata.)

## API Reference

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Service and database health check. |
| `GET /api/geographies` | List/search GTA geographies. Defaults to municipalities; pass `type=census_tract` for tracts. |
| `GET /api/geographies/{id}` | Get one geography by internal id or GEOID. |
| `GET /api/metrics?metric=rent_burden` | Return metric values by geography. |
| `GET /api/summary` | GTA summary. |
| `GET /api/summary?ids=3520005` | Summary for selected geography IDs. |
| `GET /api/compare?ids=3520005,3521005` | Compare selected geographies. |
| `GET /api/map-data?metric=affordability_index` | GeoJSON FeatureCollection for map rendering. |
| `GET /api/map-data?metric=rent_burden&detail=display` | Map-ready GeoJSON simplified with PostGIS when available. Add `type=census_tract` for tract-level map data. |
| `GET /api/transit-routes` | Packaged transit-route GeoJSON plus snapshot coverage, agency, timestamp, and checksum metadata. |

Supported metrics:

- `median_income`
- `median_rent`
- `rent_burden_pct`
- `population`
- `population_growth_pct`
- `affordability_index`
- `rent_to_income_ratio`
- `vacancy_rate`
- `average_rent_total`
- `housing_starts_total`
- `housing_completions`
- `units_under_construction`
- `unabsorbed_units`
- `rental_universe`

Aliases such as `rent_burden`, `income`, `rent`, and `growth` are accepted by the backend. CMHC metrics accept a `year` query parameter (2018–2025); census metrics are a single 2021 vintage and ignore `year`.

## Data Sources

The packaged seed covers GTA lower/single-tier municipalities:

- Toronto
- Peel municipalities: Mississauga, Brampton, Caledon
- York municipalities: Vaughan, Markham, Richmond Hill, Aurora, Newmarket, King, Whitchurch-Stouffville, East Gwillimbury, Georgina
- Durham municipalities: Pickering, Ajax, Whitby, Oshawa, Clarington, Uxbridge, Scugog, Brock
- Halton municipalities: Oakville, Burlington, Milton, Halton Hills

It also includes 1,334 packaged census tract features assigned to those municipalities by tract centroid. Tract boundaries are official 2021 Statistics Canada cartographic census tract polygons, and tract Census Profile metrics are official 2021 Statistics Canada values loaded from the normalized DF_CT extract. Some tract values are suppressed or unavailable in the source and are handled as missing data.

CMHC data is stored at municipality level, with two refinements for census tracts:

- **Starts & Completions:** real CMHC census-tract values where published (1,244 of 1,334 tracts, ~93%), labeled `official` and validated against CMHC's published CMA totals during ETL. Toronto-CMA tracts match CMHC 1:1. For Oshawa/Hamilton, where CMHC still publishes on the pre-2021 (coarser) tract boundaries, a 2021 child tract inherits its real parent tract's value: `official` where the parent recorded zero, or `estimated_parent` (allocated among siblings by renter share, conserving the parent total exactly) where it was non-zero. Tracts with no CMHC data at all keep a municipal-share `estimated` allocation.
- **Rate metrics:** vacancy rate and average rent use CMHC survey-zone values for 1,232 matched tracts; the remaining 102 tracts use a disclosed parent-municipality fallback. Bedroom rents, availability, and turnover remain parent-municipality values because those fields are not present in the zone crosswalk.

> **Note:** Turnover rate and availability rate are defined in the CMHC schema but CMHC's RMS summary export does not include values for them. These metrics are not exposed in the UI and contain no data. They may be populated in a future release if CMHC makes this data available.

Current and planned sources:

- Statistics Canada Census Profile Web Data Service/downloads for income, shelter costs, population, renters, and affordability indicators.
- Statistics Canada 2021 Cartographic Boundary Files for census subdivisions and census tracts.
- Ontario GeoHub municipal boundaries for provincial municipal layers.
- Optional CMHC rental market data for rent context.
- GTFS static feeds from TTC, GO Transit, MiWay, Brampton Transit, and Durham Region Transit for derived access scoring. The currently packaged snapshot is explicitly marked partial because Brampton Transit was unavailable when it was built; its manifest names the four included agencies and records artifact checksums.

## Metric Definitions

`rent_to_income_ratio = annualized median rent / median household income`

`affordability_index = 100 * (0.30 / rent_to_income_ratio)`

An affordability score of 100 means median rent is exactly 30 percent of median household income. Higher values indicate more affordability. GTA `rent_burden_pct` values come from the Statistics Canada Census Profile tenant shelter-cost burden characteristic.

Summary cards use weighted averages of local median values, which are useful for a demo dashboard but should not be treated as official regional medians.

## ETL Workflows

Print the official Statistics Canada CSD boundary query URL:

```bash
docker compose exec backend python etl/load_geo.py --print-url
```

Load GTA municipal boundaries from the Statistics Canada cartographic boundary service:

```bash
docker compose exec backend python etl/load_geo.py
```

Print the official Statistics Canada census tract boundary query URL:

```bash
docker compose exec backend python etl/load_tracts.py --print-url
```

Load packaged census tract rows into an existing local database:

```bash
docker compose exec backend python etl/load_tracts.py --from-seed
```

Refresh packaged census tract rows from a Statistics Canada CT GeoJSON file or URL:

```bash
docker compose exec backend python etl/load_tracts.py --update-seed --geojson /app/data/statcan_ct.geojson
```

This refresh is geometry-only and preserves official tract metrics. It aborts if
boundary identifiers no longer match the metric seed. The explicit
`--replace-metrics-with-estimates` flag exists for demo-only rebuilds and must not be
used for publication data.

Refresh the packaged offline seed geometries from the same official service:

```bash
docker compose exec backend python etl/load_geo.py --update-seed
```

Print a Census Profile WDS URL for selected CSDUIDs and characteristic IDs:

```bash
docker compose exec backend python etl/load_census.py --print-profile-url 3520005 3521005 --characteristics 1 2 229 1476 1478 1480
```

Load official 2021 Census Profile metrics for all 25 GTA municipalities:

```bash
docker compose exec backend python etl/load_census.py --official-gta
```

Refresh the packaged offline seed metrics from the official Census Profile API:

```bash
docker compose exec backend python etl/load_census.py --update-seed
```

Load a normalized Census Profile CSV extract:

```bash
docker compose exec backend python etl/load_census.py --csv /app/data/statcan_metrics.csv
```

Regenerate the real CMHC census-tract Starts & Completions data from the CMHC
Housing Market Information Portal. Each `(metric, CMA, year)` slice is validated
against CMHC's published CMA total and the run aborts on any mismatch, so the
committed `cmhc_ct_metrics.csv` is never unverified:

```bash
# Offline parser self-test (no network):
docker compose exec backend python etl/load_cmhc_tracts.py --self-test

# Live pull + validation (writes app/data/cmhc_ct_metrics.csv):
docker compose exec backend python etl/load_cmhc_tracts.py --generate-csv
```

More details are in `docs/etl.md`, and the verified acquisition recipe + honesty
guardrails are documented in `docs/cmhc-real-tract-data-plan.md`.

## Database Migrations

Docker Compose runs `alembic upgrade head` before starting Uvicorn, and the FastAPI app verifies the database is on the expected migration revision during startup. The migration chain (currently through `0009`) creates the core tables, enables PostGIS, adds `geographies.geom geometry(GEOMETRY, 4326)` with a GiST index, then adds CMHC metrics, dwelling/tenure fields, indexes, real CMHC tract values with provenance, and transit accessibility columns.

Run migrations manually:

```bash
docker compose exec backend alembic upgrade head
```

Check migration state:

```bash
docker compose exec db psql -U civicscope -d civicscope -c "SELECT version_num FROM alembic_version;"
```

## Testing

Run everything:

```bash
make test          # backend pytest + frontend vitest
make lint          # typecheck + eslint
make frontend-e2e  # Playwright browser tests (needs backend running)
```

Or individually:

```bash
cd backend && pytest                   # 158 passing tests; 3 PostGIS tests skip without a test database
cd frontend && npm run test:unit       # 31 Vitest unit tests
cd frontend && npm run test:e2e        # 48 Playwright e2e tests (incl. axe-core a11y audit)
cd frontend && npm run typecheck       # TypeScript strict mode
cd frontend && npm run lint            # ESLint
```

**Test coverage highlights:**

- **158 backend tests** plus 3 opt-in PostGIS integration checks covering API endpoints, provenance, refresh safety, conservation rules, ETL coverage gates, metric calculations, and data validation
- **48 Playwright e2e tests** covering map rendering, theme/layer persistence, metric selection, search, retry states, responsive controls, comparison, provenance, and accessibility
- **31 Vitest unit tests** for formatting, request cancellation/timeouts, cache keys, spreadsheet-safe CSV exports, color semantics, labeling, and CMHC classification
- **axe-core WCAG 2.0 AA audit** runs in CI — zero critical or serious violations
- **Rate limiting** at 60 req/min per IP via slowapi

The Playwright suite expects the backend API running at `NEXT_PUBLIC_API_URL` or `http://127.0.0.1:8000`. It starts its own Next.js server on port `3101`. To run against Docker, pass `PLAYWRIGHT_PORT=3102`.

CI (`.github/workflows/ci.yml`) runs dependency audits, backend pytest, frontend typecheck/lint/build, Vitest, Playwright against a freshly seeded API, reversible migrations against real PostGIS, and production Docker image builds. CodeQL and Dependabot add scheduled static analysis and update checks.

Screenshot generation:

```bash
cd frontend
npm run screenshots
```

## Deployment Notes

See `docs/deployment.md` for a deployment checklist.
See `docs/launch-checklist.md` for the exact GitHub, Render, and Vercel launch sequence.

Current production stack:

- **Database:** Render PostgreSQL 16 from `render.yaml` by default; an external PostGIS provider such as Neon can be used by supplying `DATABASE_URL`
- **Backend API:** Render Docker web service
- **Frontend:** Vercel (Next.js auto-deploy from `main` branch)
- Render Blueprint: `render.yaml`
- Vercel project config: `frontend/vercel.json`
- Migrations: `alembic upgrade head` runs automatically on backend startup.
- CORS: set `CORS_ORIGINS` to the deployed frontend URL and any local preview URLs needed for testing.

SQLite test databases still use SQLAlchemy metadata creation for fast isolated tests.

## Resume Bullets

- Built CivicScope, a geospatial housing-affordability analytics platform using Next.js, FastAPI, PostgreSQL/PostGIS, and public-data-ready workflows to visualize rent burden and income patterns across Greater Toronto Area municipalities and census tracts.
- Designed ETL-ready civic data workflows for Statistics Canada municipal and census tract boundary loading, Census Profile metric normalization, PostGIS geometry indexing, and GeoJSON API delivery for interactive map visualizations.
- Engineered a field-level data-provenance model that ingests real CMHC census-tract data validated against the agency's own published totals, and labels every metric `official` / `estimated` / `unavailable` so the UI never presents an estimate as fact.
- Implemented production-style API, database, CI (GitHub Actions gating every push), testing, and Docker workflows for a public-sector analytics dashboard used to compare housing affordability across regions.

## Performance & Security

- **Next.js standalone output** with tree-shaking; heavy components (`ComparisonPanel`, `DetailPanel`) are code-split via `next/dynamic`
- **Tailwind CSS** (zero-runtime CSS-in-JS); no client-side style injection overhead
- **GZip compression** on all API responses via Starlette middleware
- **HTTP caching** — `Cache-Control: public, max-age=3600, stale-while-revalidate=86400` on census data endpoints (2021 data is immutable)
- **Geometry simplification** — production PostGIS uses `ST_SimplifyPreserveTopology`; SQLite/demo environments use compact rounded GeoJSON
- **PostGIS spatial indexing** — GiST index on `geographies.geom` for efficient spatial queries
- **Rate limiting** — 60 requests/minute per IP via slowapi
- **Security headers** — a restrictive Content Security Policy, HSTS, cross-origin opener isolation, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and CORS locked to configured origins
- **Reproducible dependencies** — npm lockfile plus hash-locked Python runtime/development environments, audited in CI
- **Bundle analysis** available via `npm run build:analyze` (`@next/bundle-analyzer`)

## Current Limitations

- Packaged seed data remains available for offline demos even though the database can refresh boundaries and metrics from Statistics Canada and CMHC.
- The native PostGIS `geom` column is currently backfilled from stored GeoJSON; a future migration can make it the canonical geometry store.
- Census tract boundaries and metrics use official Statistics Canada 2021 Census Profile values (SDMX DF_CT). A small number of tracts have source-suppressed values, surfaced as "Not available".
- Real CMHC tract data covers **Starts & Completions** for 1,244 tracts. Vacancy and average rent use survey-zone values for 1,232 matched tracts and municipal fallback for 102; other RMS and construction inventory fields retain labeled municipal inheritance/allocation. Direct tract RMS ingestion remains a follow-up.
- Dissemination areas and parcel-level workflows remain planned expansion paths.
- Transit access is derived from a packaged, partial four-agency GTFS snapshot (TTC, MiWay, GO Transit, and Durham Region Transit); Brampton Transit is recorded as missing in the manifest. Every tract receives an explicit route count, including zero-service tracts; the score measures route availability, not frequency or travel time.

## How this was built

I designed the architecture, data modeling, and provenance approach, and drove validation across all data layers. That work included the investigation that uncovered a 2016-vs-2021 census-tract boundary mismatch in CMHC's published Starts & Completions data, and the fix that recovered real values for the affected tracts. Every metric value is verified against its official published source.

## License

MIT. See [LICENSE](LICENSE).
