# CivicScope Case Study

## Planning Question

Where in the Greater Toronto Area are housing affordability conditions most strained relative to local incomes, and how do those conditions differ between nearby municipalities and census tracts?

## Target User

CivicScope is designed for a policy analyst, housing researcher, municipal planner, or regional government staff member who needs a fast first-pass view of affordability patterns before deeper analysis in GIS or statistical tools.

## Product Workflow

1. Start at the GTA overview to scan median income, median rent, rent-to-income ratio, population, rent burden, and affordability index.
2. Change the active metric. Metrics in the cached Census/transit or CMHC-year family repaint locally; changing family, year, or geography fetches the required payload once.
3. Search for a municipality or census tract and inspect its local metrics in the detail panel.
4. Compare selected places in the chart/table area to understand nearby variation.
5. Use data-quality badges to distinguish official Census Profile metrics from CMHC metrics that are estimated when allocated to tracts.

## Technical Decisions

- FastAPI owns API validation, metric formulas, data shaping, and GeoJSON delivery.
- PostgreSQL/PostGIS stores native geometries for map simplification and future spatial analysis.
- The frontend caches one payload per geography/data-family/year and uses the API's metric metadata catalog to repaint values, legends, sources, and quality labels locally.
- Packaged seed data keeps the demo reliable without API keys or live downloads.
- ETL scripts separate official boundary loading, Census Profile metric loading, and tract layer refreshes.

## Current Data Quality

Municipality and census tract metrics use official Statistics Canada 2021 Census Profile values. Census tract geometries are official Statistics Canada 2021 cartographic boundaries filtered to the GTA. CMHC tract construction counts are published values where available, parent-tract estimates after boundary splits, or renter-share municipal allocations as a final fallback. Vacancy and average rent use CMHC survey zones for matched tracts and a disclosed municipal fallback elsewhere. UI badges and CSV exports preserve these distinctions per value.

## What This Demonstrates

- Full-stack application architecture with a typed frontend and tested backend.
- Geospatial data modeling using GeoJSON and PostGIS.
- Public-data ETL design for repeatable civic analytics workflows.
- Product thinking around policy analysis, data provenance, and local government use cases.
- Production-readiness habits: Docker Compose, tests, documentation, deployment notes, screenshots, and demo media.
