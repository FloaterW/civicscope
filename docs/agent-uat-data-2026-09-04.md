# Independent backend and data reliability assessment

Assessment started 2026-09-04 and continued 2026-09-05. This is an agent simulation and engineering assessment, not evidence from human user interviews. It used local source inspection, disposable in-memory databases, existing automated tests, and three bounded production reads. No production data was written.

## Verified baseline

- Existing backend suite: **158 passed, 3 skipped** in 162.25 seconds. The skipped tests require a separate PostGIS integration database; this run does not certify production database migrations or spatial behavior.
- Production `/health`: HTTP 200, database `ok`, 0.147 seconds during this warm-service observation. This is not a cold-start or uptime guarantee.
- Production municipality map: 25 features, Census observation year 2021, CMHC available years 2018–2025.
- Invalid geography type: HTTP 400 with a useful validation message.
- Production transit metadata honestly discloses partial coverage, Brampton Transit missing, and a packaged snapshot dated 2026-06-24 with unknown upstream retrieval timestamps.

## Strengths

The API preserves source-suppressed Census values and attaches provenance to derived and estimated values. Existing tests cover null handling, zero values, conservative allocation, geographic coverage, consistent map/compare results, unsafe partial publications, request validation, and database health failures. Most ETL writers already stage individual artifacts before replacing canonical files. Canonical tract and CMHC loaders have useful coverage gates. These are substantive controls, not just smoke tests.

## Findings and required behavior

| Priority | Finding | Evidence and consequence | Required behavior |
| --- | --- | --- | --- |
| P1 | Survey-zone rental values ignore observation year | Original `routes._load_zone_rms()` keyed rows by zone name, discarding CSV year 2024; selected 2018/2025 therefore received 2024 values. This was also reported independently by the researcher agent. | Index and retrieve by `(zone, year)` in serialization, map values, and map domains. For unavailable zone years, use that year's municipal value and label `inherited_municipality`. |
| P1 | Packaged Census corrections can fail to reach an existing database | Original `_demo_seed_content_changed()` sampled four fields and omitted rent burden, dwelling types, and tenure. A disposable DB with Toronto rent burden changed from 40.0 to 41.0 remained 41.0 after a no-force reseed, which returned zero rows. | Compare all canonical records and published fields, including value-to-null suppression changes and small rate corrections; unchanged input remains a no-op. |
| P1 before unattended refresh | Transit generation does not refresh its route overlay | `load_transit.py --generate-csv` produces scores and a score manifest, but does not generate `transit_routes.geojson`. The new manifest would replace old metadata without representing the still-old overlay. | Generate and validate routes, scores, and their manifest as one coherent release, or keep explicit separate timestamps and coverage for each artifact. Never advertise a complete overlay based only on score coverage. |
| P2 | Municipal Census publication validation lacks identifier/vintage gates | In-memory diagnostics demonstrated acceptance of wrong year 2026, a duplicate expected CSDUID, and an extra unexpected CSDUID. | Reject all three before canonical publication; retain existing expected-geography and mandatory-field checks. |
| P2 | No operational freshness reporting or refresh schedule | The baseline only has a keep-alive workflow. `/health` executes `SELECT 1`; it cannot detect stale datasets, missing application tables, partial transit coverage, or empty data. | Add independent readiness and dataset status, expected refresh cadence by source, scheduled validation, and failure notification. Keep process/database health separate from source-age warnings. |
| P2 | Individual writes and failure records are not uniformly safe | Original municipal seed writer directly overwrote the canonical JSON. Census network fetch/parse happens before the loader's failure-record block. Transit no-score generation returns success. | Stage writes before replacement; record failures from download through publication; exit nonzero for empty required output. Preserve last successful publication and its timestamp. |
| P2 | Direct database refresh and packaged startup seeding can conflict | When `SEED_ON_STARTUP` is enabled, the seed functions restore packaged values on drift, undoing newer DB-only refresh results. Seed functions individually commit; the outer startup rollback cannot undo earlier commits. `render.yaml` declares seeding off, so the actual deployment setting must be checked separately. | Choose a documented source of truth. A validated packaged-artifact release followed by deploy is compatible with current seeding. A DB-first pipeline needs versioned seeding and one publication transaction. |
| P2 | Cache behavior matters for update visibility | Transit artifact loaders cache for process lifetime. Cacheable API endpoints use a one-hour browser/CDN max age and a day of stale revalidation. | Restart or version artifacts when publishing; bound freshness-status caching separately. Explain publication time distinctly from when an existing visitor may refetch. |

## Freshness semantics

The Census **observation year** remains 2021 even after a successful check today. CMHC municipal files contain 2018–2025 with a recorded fetch date of 2026-05-13. The original tract-CMHC command default is 2018–2024, so an unattended command must derive explicit validated years instead of silently relying on that default. Transit is a schedule snapshot, not real-time service or frequency information.

Expose source observation period, last successful retrieval, and publication date separately. When retrieval was not recorded, show “unknown” rather than a build/startup timestamp. A failed refresh should retain the last valid data and should never advance its successful-refresh date. A successful check that finds no changes may advance `last_checked_at`, not the source observation year.

## Regression coverage added

`backend/tests/test_launch_regressions.py` contains 15 tests:

- Reject wrong-vintage, duplicate, and unexpected municipal Census inputs.
- Apply rent-burden corrections of 0.1 points, suppression to null, dwelling total, high-rise dwelling count, and ownership corrections to a previously seeded DB; a further identical seed remains a no-op.
- Retain multiple survey-zone years, use same-year zone observations, and fall back to municipal values with correct provenance for unmatched years.
- Verify both map color values and map/compare detail values against the selected observation year for Toronto tract 5350017.01 in 2018, 2024, and 2025.

Initial run against the first in-progress fixes: **14 passed, 1 failed** in 12.09 seconds. The remaining failure was 2024 map vacancy 2.3 instead of the matching zone's 3.5 because map domain/feature code retained old zone-only lookups. This was reported immediately to the implementing agent. The baseline tests alone had not covered this cross-year failure.

## Recommended publication gate

Before scheduling data refreshes, reproduce and fix the findings above, regenerate only validated source artifacts, compare record counts/years/null rates/provenance with the previous release, and run the API regressions. Schedule refreshes at appropriate source cadences and fail closed when an agency or expected year is missing. Use monitoring that checks meaningful application responses as well as HTTP reachability. Browser-agent observations should be followed by actual target-user sessions when possible; this assessment cannot establish comprehension or trust among human users.
