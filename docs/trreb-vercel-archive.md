# TRREB historical archive on Vercel

## Decision and publication scope — September 25, 2026

The owner explicitly approved publishing the audited 2020–2025 municipal
aggregate figures in the public GitHub repository. This replaces the production
database connection requirement for the historical dashboard, not for other
CivicScope data. No hosting upgrade, new service or credentials are needed.

The public JSON contains exactly 1,950 unchanged resale observations, source
URLs/pages/fingerprints, and interpretation/reconciliation warnings. Original
PDFs, source/staging databases, the private release manifest and rental data are
excluded. Full aggregate data are downloadable from GitHub as approved; the
dashboard CSV still excludes TRREB. The archive is not current market data.

## Delivery

`GET /api/trreb-archive/resale/{geoid}?year=2025` runs in a Vercel Next.js Node
function. Add `month=1` through `12` for a monthly table. Defaults are the actual
2025 year-end table. Invalid or duplicate periods return 422; unsupported
geographies (including all tracts) return 404. Methods other than GET/HEAD/OPTIONS
are not supported. No outbound fetch, database read or data write is performed.
The entire artifact fingerprint is checked before creating its in-memory index;
integrity failures return 503. Responses use `Cache-Control: no-store` so a code
rollback does not leave old archive responses in CDN caches. The dataset is
imported only by the server reader, not bundled into browser JavaScript.

The browser uses same-origin requests only for this archive. Census, CMHC and
transit requests retain their existing API base URL. Municipal reporting context
does not imply TRREB/Census polygon equivalence, and no tract fallback is added.

## Modes and rollback

- Unset `NEXT_PUBLIC_TRREB_ENABLED` (or `archive`): bundled Vercel archive.
- `0` or an unrecognized value: hide section and disable archive route.
- `1`: legacy PostgreSQL-backed public API, requiring its separate data release.
- Development-only `NEXT_PUBLIC_TRREB_PREVIEW_ENABLED=1`: local preview, unless
  the legacy public mode is explicitly selected.

Do not set the public flag to `1` to enable the bundled archive. If a project has
an existing explicit `0`, remove it or set it to `archive`, then rebuild.
`TRREB_ARCHIVE_DISABLED=1` can also disable the archive API server-side; the UI
will show its retry state until hidden by a build-time flag or rollback.
Promoting the previous tested Vercel deployment rolls back the entire feature.
None of these actions removes figures already published in GitHub history.
No Render flag or production database mutation is required.

## Updates and verification

Prepare/audit a new private release, explicitly review its source revision pins,
export with `python -m etl.export_trreb_web --bundle ... --approved-release ...
--output ...`, review the resulting public rows, and update both pinned hashes.
The exporter exclusively creates its target to avoid silently overwriting data.
Do not silently refresh source reports or synthesize annual medians.

Run the Python archive schema/crosswalk check, frontend unit tests, lint,
typecheck, production build, and `npx playwright test --config
playwright.trreb-archive.config.ts`. The production browser suite exercises real
archive responses and synthetic outage/retry contracts in three engines. CI
also retains the existing dashboard, preview, backend, security and Postgres
checks. After deployment, verify real API values and desktop/mobile browser
journeys on the production alias. Record results separately; this document is
an operations guide, not evidence that deployment has already passed.
