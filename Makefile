.PHONY: up down logs backend-dev frontend-dev backend-test frontend-build frontend-e2e db-upgrade seed load-geo load-geo-seed load-census-url load-census-official load-census-seed load-census clean

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

backend-dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

backend-test:
	cd backend && pytest

frontend-build:
	cd frontend && npm run typecheck && npm run build

frontend-e2e:
	cd frontend && npm run test:e2e

db-upgrade:
	cd backend && alembic upgrade head

seed:
	cd backend && python etl/seed_demo_data.py

load-geo:
	cd backend && python etl/load_geo.py

load-geo-seed:
	cd backend && python etl/load_geo.py --update-seed

load-census-url:
	cd backend && python etl/load_census.py --print-profile-url 3520005 3521005 --characteristics 1 2 229 1476 1478 1480

load-census-official:
	cd backend && python etl/load_census.py --official-gta

load-census-seed:
	cd backend && python etl/load_census.py --update-seed

load-census:
	cd backend && python etl/load_census.py --csv $(CSV)

clean:
	docker compose down -v
