# Deployment Guide

This guide assumes the portfolio deployment uses:

- Backend: Render, Fly.io, or Railway
- Database: the Render PostgreSQL 16 resource defined in `render.yaml`, or another managed PostgreSQL provider with PostGIS enabled
- Frontend: Vercel

The repository includes:

- `render.yaml` for a Render Blueprint backend/database setup.
- `frontend/vercel.json` for the Vercel frontend project.
- `.env.production.example` for production environment variable names.
- `docs/launch-checklist.md` for the end-to-end GitHub, Render, and Vercel sequence.

## Backend

Required environment variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Set to `production`. |
| `DATABASE_URL` | PostgreSQL connection string using the SQLAlchemy/psycopg format, for example `postgresql+psycopg://user:password@host:5432/dbname`. |
| `SEED_ON_STARTUP` | Use `true` for a portfolio demo with packaged GTA seed data; use `false` when production data is loaded separately. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins, for example `https://civicscope.vercel.app,http://localhost:3001`. |
| `FORWARDED_ALLOW_IPS` | Proxy addresses trusted for client IP/rate-limit headers. Render uses `*` because traffic is terminated by its managed proxy; self-hosted deployments should list only their proxy addresses. |
| `RATE_LIMIT` | SlowAPI limit string. Defaults to `60/minute`; automated test environments can raise it without weakening production. |

Install command:

```bash
python -m pip install --require-hashes -r requirements.lock
```

Release or migration command:

```bash
alembic upgrade head
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The production Dockerfile already runs migrations before startup:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Health check:

```text
/health
```

## Database

The app expects PostGIS support. The Alembic migration creates the PostGIS extension when the database user has permission:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

If the managed provider requires extensions to be enabled manually, enable PostGIS before running migrations.

The app stores source GeoJSON in `geographies.geometry` and syncs a native PostGIS `geographies.geom` column for spatial indexing and simplified map payloads.

## Frontend

Required Vercel environment variable:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Public URL of the deployed FastAPI service. |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | API timeout in milliseconds. The default is 60000 to tolerate a cold-starting demo backend. |

Build command:

```bash
npm run build
```

For the production Docker image, public variables are compiled into the browser
bundle and therefore must be supplied as build arguments (runtime-only values are
too late for a static Next.js build):

```bash
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_API_TIMEOUT_MS=60000 \
  -t civicscope-frontend ./frontend
```

When importing the repository into Vercel, set the project root directory to:

```text
frontend
```

Output:

```text
.next
```

After deploying the frontend, update backend `CORS_ORIGINS` with the Vercel production URL and any preview domains you want to test.

## Data Refresh

For a hosted demo, packaged seed data is enough to make the app usable immediately. To refresh the database from official sources:

```bash
python etl/load_geo.py
python etl/load_census.py --official-gta
python etl/load_tracts.py  # geometry-only; requires existing official tract metrics
```

To refresh the packaged seed files before building a demo image:

```bash
python etl/load_geo.py --update-seed
python etl/load_census.py --update-seed
python etl/load_tracts.py --update-seed --geojson /path/to/statcan_ct.geojson
python etl/load_tract_census.py --generate-csv --update-seed
python etl/load_cmhc.py --update-seed
python etl/load_cmhc_tracts.py --generate-csv
```

Every tract/CMHC refresh validates row, field, geography/year, and slice coverage
before replacing a file, and writes through a temporary file. `load_tracts.py`
preserves official metrics during boundary refreshes. `--allow-partial` outputs are
diagnostic and must not be deployed.

## Pre-Deploy Checklist

- `pytest` passes in `backend`.
- `npm run typecheck` passes in `frontend`.
- `npm run build` passes in `frontend`.
- `npm run test:e2e` passes with backend reachable.
- `alembic upgrade head` has run against the target database.
- `/health` returns HTTP 200; HTTP 503 means the database is unavailable.
- `CORS_ORIGINS` includes the deployed frontend origin.
- No real secrets are committed; use `.env.example` only as a template.
- `pip-audit --require-hashes -r requirements.lock` and `npm audit --audit-level=high` report no actionable vulnerabilities.
- The transit snapshot manifest reports the agencies and coverage status expected for the release.
- GitHub branch protection requires the CI and CodeQL checks before merging to `main`.
- Configure external uptime/error monitoring for `/health`; the keep-alive workflow now fails visibly on a persistent non-200 response.
