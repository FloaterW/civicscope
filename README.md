# CivicScope

A geospatial civic analytics platform that helps users explore housing affordability, income, population growth, and access patterns across Greater Toronto Area communities — with rigorous, visible data provenance.

[![CI](https://github.com/FloaterW/civicscope/actions/workflows/ci.yml/badge.svg)](https://github.com/FloaterW/civicscope/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Next.js](https://img.shields.io/badge/Next.js-15-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688)
![PostGIS](https://img.shields.io/badge/PostgreSQL-PostGIS-316192)

[![CivicScope overview dashboard](docs/screenshots/overview-dashboard.png)](https://civicscope-gold.vercel.app)

## Live Demo

- **Frontend:** https://civicscope-gold.vercel.app
- **Backend API:** https://civicscope.onrender.com
- **Health check:** https://civicscope.onrender.com/health
- **API docs:** https://civicscope.onrender.com/docs

> The backend runs on Render's free tier and spins down after inactivity. The first request after idle may take ~30 seconds while the instance wakes up.

## Overview

CivicScope is a portfolio-grade full-stack project for public-sector analytics. It pairs a FastAPI backend, SQLAlchemy data model, Postgres/PostGIS Docker stack, packaged Greater Toronto Area seed data, tested API endpoints, and repeatable Statistics Canada + CMHC ETL scripts with a Next.js dashboard — an interactive MapLibre map, municipality/census-tract level switching, summary cards, comparison chart, search, and a detail panel.

Municipal geometries use Statistics Canada 2021 cartographic census subdivision boundaries. Metric values use official Statistics Canada 2021 Census Profile characteristics for the selected GTA municipalities.

Census tract geometries use Statistics Canada 2021 cartographic census tract boundaries filtered to the selected GTA municipalities. Tract-level metrics are official Statistics Canada 2021 Census Profile values fetched via the SDMX DF_CT dataflow.

**Data honesty is the project's defining principle.** Most demos fabricate or silently impute their data; CivicScope does not:

- **Every metric carries field-level provenance** (`official` / `estimated` / `unavailable` / `low_confidence`), surfaced in the UI, so an estimate is never shown as if it were official.
- Source-suppressed census values render as "Not available" rather than being filled. Where the official rent-burden value is suppressed, the app shows a clearly-labeled *estimate* derived from rent and income.
- Tracts with a tiny 2016 base population have their growth rate flagged low-confidence (a near-empty base turns ordinary growth into an absurd percentage).
- **Real CMHC census-tract data, validated, not faked.** CMHC publishes Starts & Completions at the census-tract level for the GTA's three CMAs (Toronto, Oshawa, Hamilton). CivicScope ingests these real values — **validated during ETL against CMHC's own published CMA totals** (a slice is rejected unless its tract values sum to the published total) — and labels them `official`. For the ~9% of tracts CMHC does not survey, it falls back to a renter-household-share allocation labeled `estimated`. The map badge reads "official + estimated" and the detail panel marks each value accordingly. CMHC *rate* metrics (vacancy, average rent) are not published at tract level, so they are inherited unchanged from the parent municipality and labeled as such.

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

The core workflow is designed for a policy analyst or planner: scan the regional overview, switch metrics, search or click a geography, inspect local affordability indicators, and compare selected areas. Throughout, the app is explicit about data provenance — official Census Profile and real CMHC values are visibly distinguished from estimated fallbacks, so a planner is never misled about which numbers are survey-grade.

See [docs/case-study.md](docs/case-study.md) for the full project narrative.

### Documentation

- [docs/architecture.md](docs/architecture.md) — system design and component overview.
- [docs/data-dictionary.md](docs/data-dictionary.md) — every column, metric, provenance status, and fallback formula.
- [docs/cmhc-real-tract-data-plan.md](docs/cmhc-real-tract-data-plan.md) — the verified CMHC census-tract acquisition recipe, validation gate, and honesty guardrails.
- [docs/etl.md](docs/etl.md) — ETL workflows and data refresh.
- [docs/tract-metric-upgrade.md](docs/tract-metric-upgrade.md) — tract-metric upgrade notes and follow-ups.

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

# 2. Backend — DATABASE_URL must point at PostGIS (.env.example has this value).
cd backend
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://civicscope:civicscope@localhost:5432/civicscope"
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

> Note: without a PostGIS database, `alembic upgrade head` fails — the schema uses
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
- `turnover_rate`
- `availability_rate`

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

- **Starts & Completions:** real CMHC census-tract values where published (1,213 of 1,334 tracts, ~91%), labeled `official` and validated against CMHC's published CMA totals during ETL; a renter-share allocation labeled `estimated` for the rest.
- **Rate metrics** (vacancy, average rent, turnover, availability): not published at tract level, so inherited unchanged from the parent municipality and labeled as inherited.

Current and planned sources:

- Statistics Canada Census Profile Web Data Service/downloads for income, shelter costs, population, renters, and affordability indicators.
- Statistics Canada 2021 Cartographic Boundary Files for census subdivisions and census tracts.
- Ontario GeoHub municipal boundaries for provincial municipal layers.
- Optional CMHC rental market data for rent context.
- Optional GTFS transit stop data from TTC, GO Transit, MiWay, Brampton Transit, York Region Transit, Durham Region Transit, and Burlington/Oakville/Milton providers for access scoring.

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

Docker Compose runs `alembic upgrade head` before starting Uvicorn, and the FastAPI app verifies the database is on the expected migration revision during startup. The migration chain (currently through `0007`) creates the core tables, enables PostGIS, adds `geographies.geom geometry(GEOMETRY, 4326)` (backfilled from stored GeoJSON with a GiST spatial index), then layers on the CMHC metrics, dwelling/tenure columns, county/state indexes, and the real CMHC census-tract Starts & Completions table (`cmhc_tract_metrics`).

Run migrations manually:

```bash
docker compose exec backend alembic upgrade head
```

Check migration state:

```bash
docker compose exec db psql -U civicscope -d civicscope -c "SELECT version_num FROM alembic_version;"
```

## Testing

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Browser regression tests:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The Playwright suite expects the backend API to be running at `NEXT_PUBLIC_API_URL` or `http://127.0.0.1:8000`.
It starts a separate Next.js test server on port `3101` by default so it does not conflict with the normal local dashboard port. To run against an already-running dashboard (e.g. the Docker frontend on `3102`), pass `PLAYWRIGHT_PORT=3102`.

Continuous integration (`.github/workflows/ci.yml`) runs the full gate — backend `pytest`, frontend typecheck/lint/build, and the Playwright suite against a freshly-seeded backend — on **every branch push** and pull request, so regressions are caught before they reach `main`.

Screenshot generation:

```bash
cd frontend
npm run screenshots
```

## Deployment Notes

See `docs/deployment.md` for a deployment checklist.
See `docs/launch-checklist.md` for the exact GitHub, Render, and Vercel launch sequence.

Current production stack:

- **Database:** Neon PostgreSQL (free tier, AWS US East 1)
- **Backend API:** Render free-tier web service (Docker), connected to Neon
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

## Current Limitations

- Packaged seed data remains available for offline demos even though the database can refresh boundaries and metrics from Statistics Canada and CMHC.
- The native PostGIS `geom` column is currently backfilled from stored GeoJSON; a future migration can make it the canonical geometry store.
- Census tract boundaries and metrics use official Statistics Canada 2021 Census Profile values (SDMX DF_CT). A small number of tracts have source-suppressed values, surfaced as "Not available".
- Real CMHC tract data covers **Starts & Completions** only. CMHC *rate* metrics (vacancy, rent) are heavily suppressed at tract level, so they remain inherited from the parent municipality; `units_under_construction`/`unabsorbed_units` keep the renter-share allocation. Ingesting these as real tract values is a possible follow-up.
- Dissemination areas and parcel-level workflows remain planned expansion paths.
- Transit/access scoring is intentionally not implemented yet; GTFS ingestion is the next domain feature after deployment polish.

## License

MIT — see [LICENSE](LICENSE).
