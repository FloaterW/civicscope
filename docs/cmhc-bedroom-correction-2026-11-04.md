# CMHC bedroom-rent correction — November 4, 2026

The municipal importer previously weighted each bedroom rent with all-bedroom rental stock. It now uses the unit count for the corresponding bedroom. A missing or suppressed contributing rent or count produces a null aggregate, rather than a partial average presented as complete.

## Evidence and scope

Forty official CMHC Housing Market Information Portal Rental Market Survey CSVs were downloaded: Total, Studio, 1 Bedroom, 2 Bedroom and 3 Bedroom Plus for each year from 2018 through 2025, using table 2.1.31.3 for Toronto CMA survey zones (Row / Apartment). Replaying the previous algorithm against those files reproduced the packaged bedroom values exactly. Replaying the corrected algorithm matched the replacement seed exactly.

The full isolated refresh contains all 200 municipality/year rows and all 36 required tract slices. The tract file is unchanged (8,198 rows). Across the municipal seed, 90 bedroom-rent values change in 24 rows: Toronto, Mississauga and Brampton in each of the eight years. Eight values become null because the contributing source inputs are suppressed or unavailable. All other numerical fields and municipality/year keys are unchanged, including total rent, vacancy, rental stock and construction figures. These remain municipal aggregations of official survey-zone inputs, not newly published tract measurements.

For example, Toronto's 2025 one-bedroom average changes from $1,746 to $1,761 and its two-bedroom average from $2,127 to $2,061. The [immutable correction snapshot](../backend/app/data/cmhc_bedroom_corrections_20261104.json) contains all 90 before/after cells and SHA-256 hashes of the 40 source files. The [importer](../backend/etl/load_cmhc.py) defines the request parameters and zone membership. Raw downloaded files and replay diagnostics are retained locally under `out/cmhc-audit-rms-2018-2025-20261104` and `out/cmhc-audit-replay-20261104.json`.

| Artifact | SHA-256 (LF text) |
| --- | --- |
| Corrected municipal seed | `fe8d24d569b681d7962be3b66e812139a9faf4b351c7e757168bcbc56e362a58` |
| Unchanged tract metrics | `118a34ea6819a6826349e994d0ea9c15f531f71dfec8cb7afe59d4fe4ee496cb` |
| Immutable correction snapshot | `25cb2242f7c6e236c87e266c89895e0d553ffaa526d7e034f89fd6d77f482543` |

The CMHC source-check record uses the actual candidate verification time. Census and transit verification dates are not advanced by this correction. The separate survey-zone RMS snapshot is outside this refresh's scope.

## Safe promotion and verification

Migration `0012_cmhc_bedroom_weights` verifies the snapshot hash and the complete scope before any writes. Each update requires the expected municipality type, boundary source and recorded old value; a compare-and-swap condition protects against intervening changes. Already-corrected cells are safe to rerun. Missing rows, custom boundaries, custom values and newer years are retained. No production reseeding is needed.

Regression tests compare every stored cell before and after the migration, exercise suppressed/null values, reject a modified snapshot, verify idempotence, and preserve conflicting values and unknown geographies. The same correction assertions run against SQLite and an isolated schema in the CI PostgreSQL service. Production startup seeding has a separate fail-closed test so a skipped conflict cannot trigger destructive replacement.

After release, verify the API's CMHC years and all 90 changed values, confirm representative unchanged totals and Census figures, and inspect `/api/data-status`. A passing refresh or migration test is not evidence that production has been updated; deployment and API checks must be recorded separately.
