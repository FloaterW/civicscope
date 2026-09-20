# Launch reliability and operations

Hosting remains on the existing free Render and Vercel plans. No paid upgrade is authorized. Render can sleep and scheduled GitHub checks can be delayed; this is not an always-on service or an uptime guarantee.

## Monitoring

The Production health checks workflow checks frontend content, backend database health, population data and the expected 1,359 geographies. It retries once for cold starts, records latency and source-check status, and opens one GitHub incident issue on persistent failure. Recovery closes the bot-created incident. GitHub notification delivery depends on repository notification preferences. Slow responses and unknown source dates are reported, not treated as outages.

Frontend error reporting sends only fixed error categories to a same-origin endpoint. It excludes search text, URLs, stack traces and user payloads. Logging is deduplicated per browser load and per server instance, not globally rate-limited. Vercel runtime logs and backend structured logs require manual investigation; they are not a full error-tracking service.

Production-only Vercel Web Analytics and Speed Insights integrations strip query strings and fragments. Web Analytics on Hobby was enabled on September 12, 2026; the existing Speed Insights dashboard is available and awaits the deployed integration. Stay within free plan limits; do not enable paid add-ons.

## Data refresh

The weekly Validate data refresh workflow fetches Census, CMHC and transit into isolated temporary directories. Transit uses a disposable local PostGIS database, never the production database. Failed or partial candidates are rejected and raise a source-specific GitHub issue. Validated candidate artifacts are retained for 30 days. Production data is not automatically replaced.

To promote a candidate:

1. Review source coverage, observation years, changed values, route geometry and the manifest hashes. A successful download is not proof that upstream values are correct.
2. Merge only the relevant source artifacts into `backend/app/data`. If promoting multiple candidates, merge their source entries in `refresh_manifest.json`; do not overwrite one source's history with another candidate's manifest.
3. Run backend tests and browser regressions, review the diff, then commit and deploy the packaged artifacts together.
4. Confirm `/api/data-status`, representative map values and transit overlays after deployment.

Refresh checks preserve configured supported periods. They do not discover every future Census release or CMHC observation year. Survey-zone RMS data remains a separately maintained snapshot: a zone value is used only for its actual observation year, with municipality fallback clearly labelled for other years. The current transit snapshot remains explicitly partial until a complete candidate is validated and promoted.

The public Data dates and update status disclosure separates observation years, source checks, packaging dates and database load times. Missing refresh records remain unknown; deployment alone never marks data freshly checked.

### Recording an unchanged candidate

For a successful, reviewed workflow candidate whose values match production, run
`python -m etl.record_source_check --source cmhc --candidate ../out/candidate-cmhc`
from `backend`. Review the JSON output and apply it to `app/data/refresh_manifest.json`.
The helper checks candidate hashes, rejects changed values, and preserves other source records.
It only ignores CMHC fetch timestamps/coverage diagnostics and harmless row ordering or line endings;
it never treats a missing or suppressed number as zero. Other JSON/geometry files must match exactly.
Changed data still needs the full promotion review above. Do not copy a candidate's check date alone.

The API verifies all required packaged file hashes before accepting a source record.
Text hashes normalize CRLF to LF for consistent Windows/Linux checkout behavior, and are cached
for the immutable deployment's process lifetime. Missing, malformed or mismatched evidence stays unknown.
CMHC verification covers the municipality and tract artifacts, not the separate survey-zone snapshot.

On September 20, the successful September 15 CMHC candidate from workflow
https://github.com/FloaterW/civicscope/actions/runs/34987098673 was compared against
the packaged data. All values matched; its original check timestamp was retained.
No statistics were replaced. Census and the partial transit snapshot remain unverified.

Frontend dependency groups now include only minor/patch upgrades. Major upgrades remain separate
review items, not silently bundled migrations. The September 20 repair retains the existing major
versions of Tailwind, Recharts, ESLint, TypeScript, Vitest, Node types and icons. Recharts 2 and
ESLint 9 report maintenance deprecations; their migrations remain follow-up work, not completed upgrades.

## User-testing results

The September 15 [five-agent review](agent-usability-review-2026-09-15.md) and [official-source investigation](official-data-source-review-2026-09-15.md) record further findings and verification. CMHC refresh requirements are metric-specific: the packaged tract starts cover 2018–2024, while tract completions cover 2018–2022. Candidates must preserve every previously populated tract/metric/year cell; an archived, never-populated combination is not a required refresh slice.

The September 4 reports in this directory describe agent-simulated resident and researcher workflows, not recruited human participants. They led to year-correct survey values, clearer field-level provenance, corrected selection announcements, selectable comparison groups, shareable links and export period/source/method columns. The test suite also covers mobile accessibility, navigation, downloads, backend validation and refresh failure isolation. Real resident/researcher sessions remain valuable before making broader usability claims.

Comparison groups support up to six areas of one geography level. Changing levels clears the group. Shared links contain the comparison and dashboard state; no account is required.
