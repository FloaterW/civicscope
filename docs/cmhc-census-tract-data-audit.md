# CMHC Census Tract Data Audit

Date: 2026-05-12

## Current Data Sources

### CMHC Housing Market Information Portal (HMIP)

- **ETL script**: `backend/etl/load_cmhc.py`
- **Seed file**: `backend/app/data/cmhc_seed.json`
- **Geography level**: Municipality (Census Subdivision / CSD)
- **Years**: 2018–2025
- **Join key**: CSD geoid (e.g., `3520005` for Toronto)

### Datasets Currently Loaded

| Dataset | HMIP Table | Geography | Metrics |
|---------|-----------|-----------|---------|
| Rental Market Survey (RMS) | 2.1.31.3 | Survey zone → aggregated to CSD | vacancy_rate, availability_rate, average_rent (total + by unit type), turnover_rate, rental_universe |
| Starts & Completions (Scss) | 1.1.1, 1.2.2, 1.2.3 | CSD (per-municipality query) | housing_starts (total + by type), housing_completions, units_under_construction |

### RMS Coverage Gaps

CMHC's Rental Market Survey uses ~31 survey zones within the Toronto CMA. Not all 25 GTA municipalities fall within a surveyed zone. **10 municipalities have no RMS data at all**:

| Geoid | Municipality | Has RMS? | Has Scss? |
|-------|-------------|----------|-----------|
| 3518009 | Whitby | No | Yes |
| 3518013 | Oshawa | No | Yes |
| 3518017 | Clarington | No | Yes |
| 3518020 | Scugog | No | Yes |
| 3518039 | Brock | No | Yes |
| 3519036 | Markham | No | Yes |
| 3519054 | East Gwillimbury | No | Yes |
| 3519070 | Georgina | No | Yes |
| 3521024 | Caledon | No | Yes |
| 3524002 | Burlington | No | Yes |

These municipalities appear in `ALL_GTA_GEOIDS` for Scss queries but are not mapped in `ZONE_TO_GEOIDS` for RMS data.

**Markham** is mapped in `ZONE_TO_GEOIDS` but shows no RMS data in some years, likely because the HMIP endpoint returns no data for that zone in those periods.

### Census Tract Data Model

- Census tracts **do not have their own CMHC records** in the database.
- At query time, each census tract inherits its parent municipality's CMHC row via the `county` field on the Geography model (county stores the parent municipality name).
- **Count metrics** (starts, completions, under construction, rental universe) are proportionally allocated to census tracts using each tract's share of municipal renter households. The UI labels these allocated values as estimated.
- **Rate metrics** (vacancy, rents, turnover, availability) pass through as reasonable proxies for the local market and are inherited from the parent municipality.

### Why Clarington Shows "No Data" for Rental Market

Clarington (geoid `3518017`) has **zero RMS records across all years** (2018–2025). All 8 rate-based fields are null in every seed record. This is because Clarington is outside CMHC's RMS survey zone coverage for the Toronto CMA. Clarington does have construction data (Scss) — starts, completions, and units under construction are present.

This is a genuine data gap, not a code bug.

## Available Join Keys

| Source | Key | Format | Example |
|--------|-----|--------|---------|
| Geography table | geoid | String, 7 digits | `3520005` |
| Census tracts | geoid | String, 10 digits (PRCDCTUID) | `5350413.01` |
| Census tracts → municipality | county field | Municipality name string | `Toronto` |
| CMHC seed | geoid | String, 7 digits (CSD) | `3520005` |

Census tract geoids use the format `PR + CD + CTUID` (e.g., `5350413.01`). There is no direct census tract key in the CMHC data — the join goes through the county/municipality name.

## Missing but Desirable Data

### Census Tract-Level (from CMHC HMIP)

CMHC's HMIP portal can export some metrics at the census tract level for select markets. However:

- **RMS data** is only available at survey zone level (GEO_TYPE=5), not census tract. Zones are larger than census tracts and don't align to them.
- **Scss data** (starts, completions, under construction) can be queried at CSD level but not census tract.
- **HMIP does not support GEO_TYPE=11 (census tract)** for the Toronto CMA rental market tables.

### Recommended Additional Sources

1. **Statistics Canada Census Profile (SDMX API)**
   - Already used for census tract census metrics (income, rent, population, etc.)
   - Could add: core housing need, shelter-cost-to-income ratio, dwelling type, tenure, period of construction
   - Geography: census tract level
   - Reference period: 2021 Census

2. **CMHC Housing Needs Data (census-based)**
   - Core housing need rates by census tract
   - Available through Statistics Canada or CMHC's Housing Observer datasets
   - Would require a new ETL loader

3. **CMHC Rental Market Survey microdata**
   - Available through the Community Data Program (CDP) for institutional members
   - Would provide census tract-level rental data where sample sizes permit
   - Not freely available via HMIP

4. **CMHC Absorptions data**
   - Completed and unabsorbed units
   - Available at CSD level via HMIP
   - Would extend the housing supply section

## Recommended Next Steps

1. **Add core housing need** from Statistics Canada census profiles — this is freely available at CT level and highly relevant to affordability analysis.

2. **Add dwelling type / tenure breakdown** from census profiles — useful context for understanding housing stock.

3. **Explore CMHC zone-level data allocation** — survey zones could be mapped to census tracts using area-weighted or population-weighted allocation, though this introduces estimation uncertainty.

4. **Add absorptions data** from HMIP Table 1.3.1 — completes the housing construction picture at the CSD level.

5. **Document RMS coverage** in the UI — clearly indicate when a municipality is outside RMS survey coverage vs. when data is genuinely missing for a surveyed area.
