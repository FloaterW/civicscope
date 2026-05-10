# Deployment Guide

This guide assumes the portfolio deployment uses:

- Backend: Render, Fly.io, or Railway
- Database: managed PostgreSQL with PostGIS enabled
- Frontend: Vercel

## Backend

Required environment variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Set to `production`. |
| `DATABASE_URL` | PostgreSQL connection string using the SQLAlchemy/psycopg format, for example `postgresql+psycopg://user:password@host:5432/dbname`. |
| `SEED_ON_STARTUP` | Use `true` for a portfolio demo with packaged GTA seed data; use `false` when production data is loaded separately. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins, for example `https://civicscope.vercel.app,http://localhost:3001`. |

Install command:

```bash
pip install -r requirements.txt
```

Release or migration command:

```bash
alembic upgrade head
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
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

Build command:

```bash
npm run build
```

Output:

```text
.next
```

After deploying the frontend, update backend `CORS_ORIGINS` with the Vercel production URL and any preview domains you want to test.

## Data Refresh

For a hosted demo, packaged seed data is enough to make the app usable immediately. To refresh from official sources:

```bash
python etl/load_geo.py
python etl/load_census.py --official-gta
```

To refresh the packaged seed files before building a demo image:

```bash
python etl/load_geo.py --update-seed
python etl/load_census.py --update-seed
```

## Pre-Deploy Checklist

- `pytest` passes in `backend`.
- `npm run typecheck` passes in `frontend`.
- `npm run build` passes in `frontend`.
- `npm run test:e2e` passes with backend reachable.
- `alembic upgrade head` has run against the target database.
- `CORS_ORIGINS` includes the deployed frontend origin.
- No real secrets are committed; use `.env.example` only as a template.
