# Census tenure and source-data correction

## Cause and definitions

The Census SDMX importer used characteristic **1406 (Not condominium)** for
`owner_households`. The correct tenure characteristic is **1401 (Owner)**.
`renter_households` remains **1476**, the tenant shelter-cost universe excluding
farm/reserve private dwellings; CMHC allocation weights continue using that field.
The new `tenure_renter_households` uses **1402 (Renter)** so the UI no longer mixes
different populations when calculating owner/renter shares.

Toronto's official 2021 values are 602,925 owners and 557,970 tenure renters;
557,975 is the separate tenant shelter-cost count. Occupied private dwellings are
1,160,890. Rounded sample counts need not sum exactly to a 100% Census total;
the implementation does not alter values to force a reconciliation.

Sources: [Statistics Canada Toronto Census Profile](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/page.cfm?DGUIDlist=2021A00053520005&Lang=E&GENDERlist=1&STATISTIClist=1&HEADERlist=0)
and [Census Profile Web Data Service guide](https://www12.statcan.gc.ca/wds-sdw/2021profile-profil2021-eng.cfm).

## Independently checked official bulk fallback

SDMX repeatedly timed out during this audit. Instead of publishing a partial
response, the candidate was built from official bulk downloads:

- [Ontario CSD archive](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger/comp/GetFile.cfm?FILETYPE=CSV&GEONO=021&Lang=E)
- [CMA/CA/Census tract archive](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger/comp/GetFile.cfm?FILETYPE=CSV&GEONO=007&Lang=E)

Bulk characteristic IDs differ from SDMX IDs: for example, Owner/Renter are
1415/1416, and household median income is 243. The fallback validates every
selected ID against its exact characteristic label. It reads the symbol directly
after `C1_COUNT_TOTAL`; the repeated `SYMBOL` columns for gender/rates must not
overwrite that total-count symbol.

Candidate coverage is **25 municipalities and 1,334 tracts**, with no missing or
duplicate geography rows and no changes to geometry, boundaries, names or source
descriptions. Tract field coverage: population 100%, previous population 100%,
income 99.6%, median rent 98.7%, tenant households 99.6%, rent burden 99.4%.
Suppressed/unavailable values remain null; genuine unflagged zeros remain zero.

Compared with the pre-correction seed:

- Corrected owner values and newly populated renter tenure: 1,354 non-null rows
  each (25 municipalities plus 1,329 tracts).
- Added official dwelling totals and each of six housing-type counts to 1,332
  tract rows that previously lacked them.
- Restored 36 genuine unflagged zeros previously stored as null: 30 rent-burden,
  three tenant-household, two previous-population and one population values.
- No previously populated numeric values changed except the incorrect municipal
  owner values; no previously populated numeric value became null.

`backend/app/data/census_source_manifest.json` records archive SHA-256s, coverage,
retrieval time and exact dataset hashes. Raw downloads remain in ignored `out/`.

## Deployment and preservation

Migration `0011_add_tenure_renter` follows `0010_add_trreb_releases`, adds the
nullable tenure-renter column and applies a narrow whitelist of audited Census
2021 corrections. It verifies the immutable `census_corrections_20260924.json`
against a SHA-256 pinned in the migration, not a mutable future seed. Each update
requires matching geography ID, type, exact official boundary-source description,
and Census year. The correction snapshot has no geometry and does not change
when a later source refresh replaces the packaged seed.
It does not call the destructive full reseed path, delete geographies, or change
CMHC, transit, TRREB, other Census vintages or unrelated geography records.
Repeated application is safe. If a production startup detects remaining seed
drift, it fails closed rather than automatically deleting/reseeding existing
data. An explicit force-reseed remains a separate operator action.
Downgrading removes the new column but does not
restore known-incorrect source values.

The frontend uses only the dedicated tenure pair and shows unavailable shares
when either component is missing; it never falls back to shelter-cost tenants.
It explains the rounded 25% sample versus 100% occupied-dwelling universe.

For future source refreshes, generate and inspect an isolated candidate before
promotion. Ship the seed, tract CSV and matching source manifest together.
Database migration and post-deployment API checks are required to update an
existing production database; changing importer code alone is insufficient.

Core frontend requests carry a release-specific `data_revision` and request
HTTP revalidation. This bypasses pre-correction browser/CDN payloads and avoids
retaining an older API response if the frontend deploys first. Existing
in-memory map reuse remains unchanged. Already-open tabs running the old
JavaScript must reload to receive the new data contract.

The corrected corpus has official or unavailable tract rent burden, and no
estimated burden rows. Map/catalog badges now inspect the actual rows rather
than always advertising mixed provenance. Synthetic regression fixtures still
exercise the estimated fallback and prove it remains visibly distinguished.
