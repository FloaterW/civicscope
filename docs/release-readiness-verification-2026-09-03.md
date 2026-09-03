# CivicScope Release-Readiness Verification

**Date:** 2026-09-03  
**Branch:** `codex/release-readiness`  
**Baseline:** `5e61ea4`  
**Status:** Locally verified and ready for authenticated protected CI promotion.

## Remediation status

Every finding in the 2026-09-02 user-acceptance report has been addressed:

| Finding | Result | Verification |
| --- | --- | --- |
| F-01 basemap watermark | Resolved | Migrated to OpenFreeMap vector styles; light and dark real-tile screenshots showed no provider watermark; all tile/style/font requests returned 200. |
| F-02 incomplete transit coverage not disclosed | Resolved | Map, detail, tooltip, and CSV surfaces identify partial coverage, included agencies, missing Brampton Transit, and the 2026-06-24 snapshot date. |
| F-03 populated-state contrast failures | Resolved | Stateful mobile light/dark axe-core scans pass; muted, teal, and estimated-value label colors meet the tested WCAG 2 AA rules. |
| F-04 stale deployment/cold-start empty state | Code resolved | Slow API startup now shows loading and wake-up copy rather than a meaningful-looking zero; production behavior will be rechecked after promotion. |
| F-05 duplicate OpenAPI health operation ID | Resolved | GET `/health` has the unique `health_check` operation ID; HEAD remains supported but is omitted from the schema. |
| F-06 incompatible standalone start command | Resolved | `npm start` runs the generated standalone server and serves the root and static assets successfully. |
| F-07 chart tooltip viewport overflow | Resolved | Active tooltips close on resize and the mobile document remains within its viewport. |

Additional release issues found during remediation were also fixed:

- A failed summary request now says data is unavailable instead of showing zero municipalities.
- Collapsed mobile details are removed from the keyboard and accessibility tree.
- Dark-basemap style ordering and URL-to-URL style diffing no longer hide CivicScope polygons.
- The packaged seed command now loads Census, municipal CMHC, tract CMHC, and transit data—not only Census rows.
- Production frontend images accept their public API URL and timeout as build arguments.
- Runtime logs and browser-test output are excluded from production image contexts.

## Final verification evidence

| Gate | Result |
| --- | --- |
| Backend suite | **158 passed, 3 skipped** in 157.34 seconds. The skips require PostGIS and were executed separately below. |
| Real PostgreSQL/PostGIS | **3 passed**; PostGIS extension, geometry validity, and complete application-dataset counts verified. |
| Migration reversibility | **Passed**; all migrations upgraded to head, downgraded to base, and upgraded to head again. |
| Packaged seed | **Passed**; Census 2,718 rows, municipal CMHC 200, tract CMHC 8,198, and transit 1,334. |
| Frontend unit suite | **31 passed**. |
| Frontend type/lint gates | **Passed**. |
| Browser/UAT suite | **48 passed** in 3.1 minutes, single worker. |
| Accessibility | **Passed** for initial and populated mobile light/dark states; no critical or serious axe-core findings. |
| Frontend dependency audit | **0 vulnerabilities**. |
| Production builds | **Passed** for Next.js standalone, frontend container, and backend container. |
| Container runtime | **Passed**; both images run as non-root, API/dashboard return 200, security headers are present, and static assets load. |
| Real basemap/runtime | **Passed**; 25 municipal and 1,334 tract features render in both themes, layer order stays valid, and API/OpenFreeMap requests return 200. |
| Secret scan | **Passed** for high-confidence GitHub, OpenAI, AWS, and private-key patterns; no non-example `.env` files found. |

The locked Python dependency audit could not be repeated during the final pass because the approval service returned an infrastructure 404. The production dependency lock was unchanged by this remediation; the repository CI still treats `pip-audit` as a required gate.

## Production-artifact observations

- Backend health, summary, comparison, and map endpoints returned HTTP 200 against the disposable PostGIS database.
- The frontend CSP contained only the configured API origin and OpenFreeMap for external map assets; the retired CARTO endpoints were absent.
- Light and dark production views were visually inspected. Civic polygons, labels, legends, comparisons, attribution, and transit coverage disclosure were present without horizontal overflow.
- MapLibre reports one non-fatal numeric-null warning originating from the OpenFreeMap vector worker. It reproduces with empty CivicScope geography/transit collections, so it is upstream basemap data/style behavior rather than a CivicScope payload or layer error. There were no browser console errors.

## Remote promotion plan

GitHub CLI and Git transport authentication for `FloaterW` were verified before promotion. No Vercel CLI or linked `.vercel/project.json` is available locally, so deployment is expected to proceed through the repository integrations after the protected merge. The promotion sequence is:

1. Push `codex/release-readiness` and require the GitHub backend/frontend/browser, PostGIS, container, CodeQL, and secret-scan checks.
2. Review and merge through the protected `main` flow.
3. Confirm Render completes migrations and reports healthy.
4. Confirm Vercel builds with `NEXT_PUBLIC_API_URL=https://civicscope.onrender.com`.
5. Repeat the production smoke, real-tile light/dark check, transit disclosure check, and console/network inspection on the public URLs.

Do not deploy by bypassing the protected branch or by introducing credentials into the repository.
