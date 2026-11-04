# Dashboard follow-up verification — November 4, 2026

Three agents independently reviewed the live `e9ec11f` release: desktop user journeys, mobile/cross-browser accessibility, and API/data consistency. They used the real production services with paced requests. This report records the review and resulting fixes; [PR #80](https://github.com/FloaterW/civicscope/pull/80) contains the current verification status for the follow-up changes.

## Findings addressed

### Tract construction source labels

The 2025 tract housing-starts map said “official + estimated” even though every displayed value used an estimated allocation. The numeric values were consistent between the map and comparison API; the source-quality banner was misleading. The prior quality classification depended on the metric name rather than the selected year's actual values and sources.

The follow-up classifies tract starts/completions provenance from the values available for that metric and year. Official, estimated, mixed and unavailable results remain distinct. Genuine zero values count as present. A missing-data result receives a neutral badge rather than the official checkmark. Regression coverage checks both the top-level map metadata and its per-metric catalog.

The desktop review also found that municipal construction badges incorrectly named the Rental Market Survey. Survey labels are now selected by metric family. Unabsorbed inventory uses the Market Absorption Survey, while starts, completions and units under construction use the Starts and Completions Survey; rental-universe counts remain part of the Rental Market Survey. The corresponding export attribution is aligned with [CMHC's methodology](https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-research/surveys/methods/methodologies-starts-completions-market-absorption-survey).

### Available transit controls

The transit panel offered an enabled Brampton Transit checkbox even though the published snapshot and coverage note exclude that agency. Controls must reflect agencies represented in the loaded snapshot. This correction does not publish the unreviewed transit candidate or imply that the existing partial snapshot covers every GTA operator.

### CI execution budget

The post-merge [CI run](https://github.com/FloaterW/civicscope/actions/runs/41861648187) was terminated at the 45-minute job limit. Backend validation, 115 dashboard tests, 51 preview tests, 54 public tests and 58 of the final 60 archive tests had passed before cancellation. GitHub's annotation identifies the maximum execution-time limit; no assertion failure preceded it. The earlier complete run took about 31 minutes on the same application code.

The job budget is now 60 minutes. Test commands, per-test timeouts, retries, failure-on-flakiness, audit thresholds and required checks are unchanged. A parsed before/after YAML comparison verified that this was the workflow's only semantic change, and a second agent reviewed it independently.

## Live user journeys

- Desktop: all 12 visible metric options, municipality and tract searches, clear selection, concurrent right-panel sections, source details, transit overlay, historical CMHC years, geography/comparison CSVs, comparison add/remove, and copied/reopened share URLs.
- Resale: annual and monthly TRREB views, including 2021 annual and June values checked against the bundled archive. Rental and resale figures retain separate sources and periods.
- Responsive interaction: WebKit and Firefox at representative 320, 390 and 768px widths, light/dark themes, keyboard search and dismissal, comparison-chart tooltips, browser history and reload. Five automated accessibility scans reported no violations.
- Layout: opening several desktop sections kept the map and detail panel at 720px while the detail content scrolled internally. Narrow layouts did not create horizontal page overflow.
- Exports: source dates remained explicit, corrected Toronto 2025 bedroom rents appeared in CSV, missing values stayed unavailable, and the transit snapshot remained marked partial.

The mobile review recorded no HTTP error responses or uncaught page errors across 54 paced API attempts. An initially blank map in a full-page WebKit screenshot was investigated: viewport and map-element captures painted the basemap, civic polygons and selected boundary, without WebGL context loss. It was an offscreen capture artifact, not a reproduced application defect.

The production health workflow also [passed](https://github.com/FloaterW/civicscope/actions/runs/41862127279). Its separate source-verification issue accurately tracks the unreviewed transit refresh; it does not indicate an availability outage.

## Fix verification

The final backend suite passed 472 tests; six tests requiring PostgreSQL/PostGIS are exercised separately in CI. A before/after replay compared nine map responses containing 8,079 feature dictionaries: all feature data and non-source metadata were identical. The live API also matched all 90 previously corrected CMHC cells across the 24 affected municipality/year records. The new tests cover selected-year provenance, zero/null values, missing supplemental data, source-family labels and catalog consistency.

Independent agents reviewed the backend classification and frontend unavailable/transit/export changes. Hosted integration results and post-deployment checks are recorded with PR #80 so a local pass is not confused with a deployed result.

The final frontend suite passed 146 unit tests, TypeScript and affected-file lint. The focused transit browser regression passed failure/retry, absent-agency controls, bulk selection, keyboard interaction and theme/year persistence. Real SCSS labels and the MAS tooltip were inspected at 320px; explicit layout-only fixtures also checked the MAS/unavailable badges without overflow. Those fixtures establish layout behavior, not the availability of a production dataset.

## Limits and optional refinements

These were agent-driven browser and API checks, not recruited human sessions or tests on physical mobile devices. The review does not establish that every interaction or future dataset is defect-free. The free backend can still cold-start, and the published transit snapshot remains partial.

Two nonblocking refinements remain: a collapsible legend on small maps, and retaining one decimal place in compact thousands labels. Exact chart values remain available in the table and tooltip. These refinements are separate from the source-label, transit-control and CI corrections.

The importer and packaged seed retain a legacy “unsold/unrented” descriptive note for unabsorbed units. The displayed tooltip, API survey attribution and CSV now use the correct ownership/condominium scope. Align the two internal artifact notes during the next reviewed source refresh, with the required packaged-hash reconciliation; this follow-up does not rewrite the hash-pinned data snapshot.

Local screenshots, traces, CSVs and detailed agent reports are retained under `output/playwright/desktop-review-20261104`, `output/playwright/mobile-review-20261104` and `output/api-review-20261104`; they are not application assets.
