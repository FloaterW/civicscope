# Contributing to CivicScope

## Quick Start

```bash
# Clone and start all services
git clone <repo-url> && cd civicscope
docker compose up -d          # PostgreSQL + backend + frontend
# OR run locally:
cd backend && pip install -r requirements.txt
cd ../frontend && npm install
```

## Development

### Backend (FastAPI)

```bash
cd backend
DATABASE_URL=sqlite:///./dev.db SEED_ON_STARTUP=true uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs
python -m pytest               # 113 tests
```

### Frontend (Next.js)

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
npm run typecheck              # TypeScript strict mode
npm run lint                   # ESLint
npm run test:unit              # Vitest (20 tests)
npm run test:e2e               # Playwright (35 tests, needs backend running)
```

## Adding a New Census Metric

1. **Backend model** -- add the column to `backend/app/models/metric.py`
2. **Migration** -- create a new Alembic migration in `backend/app/db/migrations/`
3. **Seed data** -- update `backend/data/demo_seed.json` with values for all geographies
4. **Metric calculation** -- register in `backend/app/services/metric_calculations.py` (`VALID_METRICS`, `metric_value()`)
5. **API serialization** -- add to `serialize_metric()` in `backend/app/api/routes.py`
6. **Frontend selector** -- add to `metricOptions` in `frontend/lib/api.ts`
7. **Formatting** -- add formatting logic to `formatMetric()` in `frontend/lib/api.ts`
8. **Types** -- update `MetricKey` union in `frontend/types/index.ts`
9. **Tests** -- add backend test in `backend/tests/` and frontend unit test in `frontend/tests/unit/`

## Adding a New CMHC Metric

Same as above, plus:

- Add to `CMHC_METRICS` in `metric_calculations.py`
- Add to `CMHC_METRIC_KEYS` in `frontend/lib/api.ts`
- If it's a count metric, add to `CMHC_COUNT_METRICS` in `routes.py`
- If it has real tract-level data, add to `CMHC_REAL_TRACT_METRICS` in `routes.py`

## Architecture

```
backend/
  app/
    api/routes.py          # All API endpoints
    models/                # SQLAlchemy models (Geography, Metric, CmhcMetric)
    services/              # Business logic (summary, metric calculations, seed, ETL)
    db/                    # Database session, migrations, init
  data/                    # Seed data, CMHC crosswalk CSVs
  tests/                   # pytest tests

frontend/
  app/                     # Next.js app router (layout, page)
  components/              # React components (CivicDashboard, CivicMap, etc.)
  lib/                     # API client, color ramp, tooltip builder
  types/                   # TypeScript type definitions
  tests/                   # Playwright e2e + Vitest unit tests
```

## Data Integrity Rules

- Never fabricate data or label estimated values as official
- All CMHC tract-level values must be validated against published CMA totals
- Suppressed Census values show as "Not available", never backfilled silently
- Growth rates computed from populations under 50 are flagged `low_confidence`
- Field-level provenance (`official` / `estimated` / `unavailable`) is required for every metric

## Code Style

- TypeScript strict mode, no `any` unless unavoidable
- Tailwind CSS with project CSS variables (`--civic-*`) for theming
- Dark mode via CSS class strategy (`darkMode: "class"` in Tailwind config)
- No comments unless the "why" is non-obvious
