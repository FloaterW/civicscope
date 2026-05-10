# Data Dictionary

## geographies

| Column | Meaning |
| --- | --- |
| `id` | Internal primary key. |
| `geoid` | Stable geography identifier. GTA rows use official 2021 CSDUID values such as `3520005` for Toronto. |
| `name` | Display name. |
| `type` | Geography type, currently `municipality`. |
| `county` | Upper-tier region name for filtering and display. This column is retained from the original schema and should be renamed to `region` in a future migration. |
| `state` | Province/region code, currently `ON`. |
| `geometry` | Stored GeoJSON geometry retained for provenance, portability, and seed loading. |
| `geom` | Native PostGIS geometry in EPSG:4326, backfilled from `geometry` and indexed with GiST for spatial operations and map simplification. |
| `bbox` | Bounding box used by the frontend when selecting a geography. |
| `geometry_source` | Human-readable provenance note. |

## metrics

| Column | Meaning |
| --- | --- |
| `geoid` | Joins to `geographies.geoid`. |
| `year` | Metric vintage. |
| `median_income` | Median household income in dollars. |
| `median_rent` | Median monthly gross rent in dollars. |
| `population` | Current population estimate. |
| `previous_population` | Prior comparison population estimate. |
| `renter_households` | Renter household count used as a weight. |
| `rent_burden_pct` | Percent of tenant households spending 30 percent or more of income on shelter costs. Packaged GTA seed values come from Statistics Canada Census Profile characteristic `1478`. |
| `affordability_index` | Score where 100 equals the 30 percent rent-to-income threshold; higher is more affordable. |

## Formulas

`rent_to_income_ratio = (median_rent * 12) / median_income`

`affordability_index = 100 * (0.30 / rent_to_income_ratio)`

`population_growth_pct = ((population - previous_population) / previous_population) * 100`

Municipal geometries in the seed data come from Statistics Canada 2021 cartographic census subdivision boundaries filtered to GTA municipalities. They can now be refreshed with `backend/etl/load_geo.py`.

Packaged seed metrics use official Statistics Canada 2021 Census Profile values for the selected GTA municipalities. Refresh them with `backend/etl/load_census.py --update-seed`, or refresh the database directly with `backend/etl/load_census.py --official-gta`.
