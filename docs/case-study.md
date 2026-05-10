# CivicScope Case Study

## Planning Question

Where in the Greater Toronto Area are housing affordability conditions most strained relative to local incomes, and how do those conditions differ between nearby municipalities and census tracts?

## Target User

CivicScope is designed for a policy analyst, housing researcher, municipal planner, or regional government staff member who needs a fast first-pass view of affordability patterns before deeper analysis in GIS or statistical tools.

## Product Workflow

1. Start at the GTA overview to scan median income, median rent, rent-to-income ratio, population, rent burden, and affordability index.
2. Change the active metric to repaint the map immediately without waiting for another map request.
3. Search for a municipality or census tract and inspect its local metrics in the detail panel.
4. Compare selected places in the chart/table area to understand nearby variation.
5. Use data-quality badges to distinguish official municipal metrics from estimated tract metrics.

## Technical Decisions

- FastAPI owns API validation, metric formulas, data shaping, and GeoJSON delivery.
- PostgreSQL/PostGIS stores native geometries for map simplification and future spatial analysis.
- The frontend receives all metric values in the map payload, then changes map colors locally for responsive metric switching.
- Packaged seed data keeps the demo reliable without API keys or live downloads.
- ETL scripts separate official boundary loading, Census Profile metric loading, and tract layer refreshes.

## Current Data Quality

Municipality metrics use official Statistics Canada 2021 Census Profile values. Census tract geometries are official Statistics Canada 2021 cartographic tract boundaries, but packaged tract metric values are estimated from parent municipalities for offline demo use. The app labels this in the UI and docs to avoid misleading precision.

## What This Demonstrates

- Full-stack application architecture with a typed frontend and tested backend.
- Geospatial data modeling using GeoJSON and PostGIS.
- Public-data ETL design for repeatable civic analytics workflows.
- Product thinking around policy analysis, data provenance, and local government use cases.
- Production-readiness habits: Docker Compose, tests, documentation, deployment notes, screenshots, and demo media.
