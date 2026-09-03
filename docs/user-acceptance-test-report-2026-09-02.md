# CivicScope Comprehensive User Acceptance Test Report

**Test date:** September 2, 2026  
**Scope:** Local source tree, production builds and containers, frontend user journeys, backend API, PostgreSQL/PostGIS integration, data provenance, accessibility, responsiveness, resilience, performance, security controls, and the public deployment.  
**Release verdict:** **Not ready for public release without remediation**

## Executive summary

CivicScope's core implementation is in strong condition. All 31 frontend unit tests, all 43 browser tests, all 157 ordinary backend tests, and both opt-in PostGIS integration tests passed. Production builds and production Docker images succeeded. The live API returned the correct status codes and data for municipal, census-tract, CMHC, transit, comparison, search, and export workflows. Database migrations survived a full upgrade/downgrade/upgrade cycle, and the service degraded quickly and correctly when its database was removed.

The release gate fails because testing found three material user-facing issues:

1. The basemap is covered by repeated `API KEY REQUIRED` watermarks in both themes.
2. The transit interface says it includes all GTA agencies even though the API correctly identifies the current snapshot as partial and explicitly lists Brampton Transit as missing.
3. A selected, data-populated mobile view has a serious WCAG 2.x AA color-contrast violation affecting at least 52 rendered elements.

The configured public deployment is also behind the tested local build. It does not expose the newer transit metrics or current provenance wording, and it has the same basemap watermark. The public backend cold start took approximately 7.5 seconds during this run.

## Product story exercised

A user opens CivicScope, chooses a geography level and a housing or transit metric, searches or selects a place, inspects map and detail data with provenance, compares municipalities, switches themes, and exports selected or comparison data as CSV. The browser retrieves typed responses from FastAPI, which queries validated PostgreSQL/PostGIS data and returns explicit quality and coverage metadata.

## Overall test results

| Area | Result | Evidence |
|---|---:|---|
| Frontend lint | Pass | ESLint completed with no errors |
| Frontend type safety | Pass | Next.js type generation and TypeScript checking completed |
| Frontend unit tests | Pass | 31/31 tests in 4 files |
| Frontend production build | Pass | Next.js 16.3.4 production build completed |
| Frontend browser suite | Pass | 43/43 Playwright tests in 48.7 seconds against the production build and live API |
| Backend unit/integration suite | Pass | 157 passed, 2 optional tests skipped in the ordinary run |
| Real PostGIS integration | Pass | 2/2 opt-in tests passed against PostgreSQL/PostGIS |
| Python dependency consistency | Pass | No broken installed dependencies |
| Python vulnerability audit | Pass | No known vulnerabilities in the locked production dependency set |
| JavaScript vulnerability audit | Pass | 0 known high-severity or lower vulnerabilities reported |
| Database migrations | Pass | Upgrade to head, downgrade to base, and second upgrade to head all succeeded |
| Seed/data integrity | Pass | 1,359 geographies/metric records, 1,334 transit scores, 200 CMHC municipal records, and 8,198 CMHC tract records loaded |
| Production containers | Pass | Frontend and backend images built and ran as non-root users |
| API functional matrix | Pass | Success, validation, not-found, search, map, summary, comparison, transit, and CMHC cases returned expected responses |
| CSV exports | Pass | Selected-place and comparison downloads opened with correct headings, values, periods, sources, methods, and statuses |
| Keyboard interaction | Pass | Search selection worked with Arrow Down and Enter |
| Theme persistence | Pass | Dark preference survived a reload |
| Responsive layout | Pass with note | Fresh 390 x 844 load had no page overflow; dynamic desktop-to-mobile resizing can leave an off-screen chart tooltip |
| Accessibility | **Fail** | Initial automated screen passed critical/serious checks, but a populated mobile transit state failed serious color contrast |
| Basemap rendering | **Fail** | Light and dark tiles display an API-key watermark |
| Transit-data communication | **Fail** | UI claims all GTA agencies while the API reports partial coverage |
| Public deployment parity | **Fail** | Public frontend is older than the locally tested build and carries the map defect |

## User journeys tested

### Geography, search, and map

- Loaded the default municipality view and verified all 25 GTA municipalities.
- Switched to census-tract view and verified 1,334 tracts.
- Searched for census tract `5350001.00`, selected it, and confirmed the map, summary, comparison, and detail panels updated together.
- Searched for Toronto and selected it using the keyboard.
- Clicked map features, changed metrics and years, and verified stale requests did not overwrite newer choices.
- Exercised census, CMHC, transit-score, transit-route, unavailable, suppressed, low-confidence, official, mixed, derived, estimated, parent-tract, municipality-fallback, and survey-zone states.
- Verified map legends, data-source content, empty search results, retry behavior, and the accessible map alternative.

### Details, comparison, and exports

- Confirmed selected-geography identity and quality labels.
- Verified metric formatting, period labels, source/method/status provenance, CMHC granular periods, and unavailable values.
- Confirmed the default comparison response contains six items and that comparison controls update the data.
- Downloaded and inspected the selected-geography CSV.
- Downloaded and inspected the comparison CSV.

### Mobile, keyboard, and appearance

- Loaded the production application directly at 390 x 844 and found no body/document horizontal overflow.
- Exercised a selected transit state at the mobile viewport.
- Switched light/dark themes and verified persistence after reload.
- Verified the browser console remained free of errors and warnings during the manual flow.
- Performed WCAG 2.0/2.1 A and AA automated analysis on a populated mobile state.

### Failure and recovery behavior

- Verified the frontend differentiates API failures from ordinary no-results states and offers retry behavior.
- Verified invalid metric and geography requests return 400, missing resources return 404, and unsupported POST requests return 405.
- Stopped PostgreSQL while the production backend was running: `/health` returned 503 with a degraded/database-unavailable payload in approximately 12 ms.
- Verified allowed CORS preflight behavior and confirmed a disallowed origin received no `Access-Control-Allow-Origin` header.

## Backend and data assessment

### What is working well

- The API fails closed when no database URL is provided.
- PostgreSQL/PostGIS migrations are reversible from the current head all the way to base and reapply cleanly.
- All seeded geography geometries were present, valid, and stored as a native PostGIS geometry type.
- Data coverage and provenance are modeled explicitly. The API identifies transit coverage as `partial`, lists included and missing agencies, and distinguishes official, mixed, derived, estimated, and unavailable civic data.
- Both municipal and tract map endpoints return valid GeoJSON at realistic data volume.
- Response compression and caching are active. A tract map response compressed from roughly 3.08 MB of JSON to about 218 KB and included public cache/revalidation directives.
- Security headers, rate limiting, input validation, CORS allowlisting, and read-only method restrictions behaved as intended.
- The production image runs as `appuser`, not root.

### API matrix sampled

The live production backend returned expected results for health, OpenAPI, geography search, tract search, municipal and tract summaries, comparisons, municipality/tract/transit/CMHC maps, and transit routes. Negative checks covered an invalid metric, invalid geography type, missing geography, disallowed origin, and unsupported HTTP method.

### Data volume verified

| Dataset | Loaded count |
|---|---:|
| Municipalities | 25 |
| Census tracts | 1,334 |
| Geography metric records | 1,359 |
| Transit score records | 1,334 |
| Transit route features | 381 |
| CMHC municipal records | 200 |
| CMHC tract records | 8,198 |

The transit snapshot included TTC (227 routes), MiWay (72), GO Transit (43), and Durham Region Transit (39), while Brampton Transit was explicitly missing.

### Performance sampling

These are local single-machine smoke/load measurements, not capacity guarantees:

| Request | Sample | Outcome |
|---|---:|---:|
| Health | 50 concurrent | 0 failures; 204 ms total; ~245.7 requests/sec |
| Municipality map | 20 concurrent | 0 failures; 864 ms total; ~23.2 requests/sec |
| Census-tract map | 10 concurrent | 0 failures; 2.87 sec total; ~3.5 requests/sec |
| Gzipped municipality map | Single request | ~176 ms; 43.5 KB transferred |
| Gzipped census-tract map | Single request | ~499 ms; 217.9 KB transferred |
| Gzipped transit routes | Single request | ~39 ms; 78.8 KB transferred |

## Findings and recommendations

### UAT-01 — Basemap is visibly watermarked — High / release blocker

**Observed:** Repeated `API KEY REQUIRED carto.com/basemaps/apikey` tiles cover the map in local production containers and the public deployment, in both light and dark themes.

**Cause:** `CivicMap.tsx` uses CARTO raster tile URLs without a current API-key integration. CARTO's current [basemap API-key guidance](https://carto.com/basemaps/apikey/) confirms that authenticated tile access is required.

**User impact:** The main product surface looks broken and untrustworthy even though CivicScope's own data layer renders correctly.

**Required fix:** Configure an authorized basemap key through deployment configuration or migrate to a supported tile provider/vector-basemap integration. Add a browser assertion that inspects rendered map imagery or tile responses for provider error/watermark content; status 200 alone is insufficient.

### UAT-02 — Transit UI overstates source coverage — High / release blocker

**Observed:** The route-count tooltip says data includes routes “from all GTA transit agencies,” and the detail panel generically describes GTA agency coverage. The API correctly reports a partial snapshot with Brampton Transit missing.

**User impact:** A civic-data user can reasonably interpret route counts and scores as complete when they are not. This can lead to incorrect comparisons and erodes the strong provenance guarantees implemented in the backend.

**Required fix:** Show the API's `coverage_status`, included agencies, missing agencies, and snapshot date in the ordinary transit UI. Remove the hard-coded “all” claim. Mark transit values as partial anywhere they are summarized or exported.

### UAT-03 — Populated mobile state fails WCAG color contrast — High / release blocker

**Observed:** Automated WCAG 2.x A/AA testing found a serious `color-contrast` violation affecting at least 52 nodes in a selected mobile transit state. Representative failures included muted text at approximately 3.0–3.23:1, teal text at approximately 3.34:1, and a section heading at approximately 2.51:1 where 4.5:1 is required for normal text.

**Affected content:** Summary captions, period badges, cards, section headings, selected geography identifiers, and export controls.

**Why existing checks missed it:** The existing initial-screen accessibility test passed, but it did not audit a fully populated selected-geography state across viewport/theme combinations.

**Required fix:** Adjust the light-theme semantic color tokens and any opacity variants until normal text reaches 4.5:1 and large text reaches 3:1. Add Axe coverage for selected municipality, selected tract, transit, CMHC, light/dark, and mobile states.

### UAT-04 — Public deployment does not match the tested build — High / operational blocker

**Observed:** `https://civicscope-gold.vercel.app/` is reachable but exposes an older frontend: it lacks the newer transit metrics and current provenance wording and uses the old theme control. It also displays the basemap watermark. The Render backend took approximately 7.5 seconds to wake during this run, during which the frontend initially presented zero/empty data.

**User impact:** Improvements validated locally are not available to public users, and cold-start behavior can resemble a valid empty dataset.

**Required fix:** Merge and deploy the tested revision, fix the tile integration before promotion, run migrations/seed checks in the target environment, and execute the same production-browser suite against the deployed URLs. Present an explicit loading/waking state rather than a meaningful-looking zero count while the API is unavailable.

### UAT-05 — Duplicate health operation ID in OpenAPI — Medium

**Observed:** Both GET and HEAD `/health` are emitted with `health_health_get`. FastAPI warns about the duplicate while generating the schema.

**User impact:** Generated API clients may overwrite or ambiguously name one of these operations.

**Required fix:** Register GET and HEAD separately with unique operation IDs, or omit the HEAD operation from the public schema.

### UAT-06 — Package start command conflicts with standalone output — Low

**Observed:** `npm start` invokes `next start`, but Next.js warns that this is not the correct runner when `output: "standalone"` is configured. The Dockerfile correctly runs the generated standalone server and passed.

**User impact:** An operator following the package script gets a warning and does not exercise the same runtime used in the container.

**Required fix:** Make the start script run `.next/standalone/server.js`, or document separate local and standalone production commands.

### UAT-07 — Dynamic desktop-to-mobile resize can retain an off-screen chart tooltip — Low

**Observed:** A fresh mobile load did not overflow. After interacting with a chart at desktop width and then resizing to mobile, a Recharts tooltip remained positioned beyond the viewport and temporarily expanded scroll width.

**User impact:** Primarily affects desktop window resizing and device emulation rather than ordinary direct mobile navigation.

**Required fix:** Dismiss/recalculate the tooltip on resize and add a desktop-interaction-to-mobile-resize regression check.

## Integration boundary status

| Boundary | Status | Assessment |
|---|---:|---|
| Browser controls → frontend state | Pass | Search, selectors, map clicks, keyboard, theme, and exports behaved correctly |
| Frontend state → API request | Pass | Requests used the intended geography, metric, and year; stale responses were rejected |
| API → PostgreSQL/PostGIS | Pass | Real queries, geometry validation, migrations, seeds, and failure behavior passed |
| API provenance → frontend disclosure | **Partial** | CMHC treatment is detailed; transit partial coverage is not surfaced and is contradicted by tooltip copy |
| API response → visual map | **Partial** | Civic data layer renders, but the third-party basemap is visibly invalid |
| Local tested build → public deployment | **Fail** | The deployed frontend is stale and not equivalent to the tested build |

## Recommended remediation order

1. Replace or authenticate the basemap integration and add a visual/tile-content regression test.
2. Surface transit snapshot coverage and remove the false all-agencies statement.
3. Correct the light-theme contrast tokens and expand stateful accessibility coverage.
4. Deploy the tested revision with explicit cold-start/loading behavior, then repeat browser UAT against production.
5. Resolve the duplicate OpenAPI operation ID.
6. Align the production start script with the standalone build.
7. Stabilize chart tooltips across viewport resizing.

## Release acceptance criteria

The product can be reconsidered for release when:

- No provider error or API-key watermark is visible at any supported theme or viewport.
- Transit screens and exports display the actual snapshot status and missing agencies.
- Axe reports no serious or critical violations in every selected-data state, theme, and mobile/desktop viewport in the release matrix.
- The public frontend matches the tested revision and completes the core user story against the public API.
- The full 31-unit, 43-browser, 157-backend, and 2-PostGIS test baseline remains green.

## Test limitations

- Performance results are local smoke/load samples and do not replace production load testing with representative geography and concurrency patterns.
- Screen-reader output was assessed through semantics, accessible names, keyboard operation, and automated analysis; a manual NVDA/JAWS/VoiceOver session was not performed.
- Cross-browser automated testing used the repository's configured Playwright browser project; dedicated Safari/iOS and physical Android device testing remains advisable before a broad public launch.
- GitHub-hosted CI and repository settings could not be revalidated during this run because the local GitHub authentication token is expired. Local source, build, container, and public deployment behavior were tested directly.
