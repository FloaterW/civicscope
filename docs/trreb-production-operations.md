# TRREB public resale: controlled release operations

> **September 25, 2026 update:** the owner authorized publishing the aggregate
> figures in the public repository. The dashboard now defaults to the versioned
> Vercel archive described in [Vercel archive operations](trreb-vercel-archive.md).
> The PostgreSQL workflow below remains available as a separately gated option;
> it is no longer a prerequisite for the public historical dashboard. Original
> PDFs, staging databases and private release manifests remain unpublished.

## Scope and invariants

The owner authorized aggregate-statistics display; no further permission
document is required for this implementation. Hosting remains free. Use the
existing application PostgreSQL database, not a Render ephemeral filesystem.
Private source PDFs and staging SQLite stay outside Git and public hosting.

Public scope is the 25 explicitly crosswalked municipal reporting contexts for
2020–2025: 72 monthly and six actual year-end tables, 1,950 observations.
Annual medians are never averages of monthly medians. Census polygons are not
certified TRREB reporting boundaries: no choropleth or tract allocation.
The response retains report URL, page, SHA, period, property type, source
reconciliation warnings and attribution. Quarterly MLS leases remain in the
separate rental importer/archive and never replace CMHC rental measures.

No upload/admin HTTP endpoint, public bulk export, scheduled refresh, new
service or paid storage is introduced. Application tables are
`trreb_releases`, `trreb_observations`, `trreb_publication` and
`trreb_publication_events`. Publication is a singleton pointer. Release data
is append-only through the supported CLI; database administrators remain a
trusted boundary and should not edit release rows manually.

## Prepare and independently review an immutable release

Run from `backend/`, with the normal project Python dependencies. No
production credentials are needed for the first two commands:

```text
python -m etl.trreb_release draft-manifest --root ../out/trreb-history --output ../out/trreb-history/release-manifest-20260924.json
python -m etl.trreb_release prepare --root ../out/trreb-history --manifest ../out/trreb-history/release-manifest-20260924.json --output ../out/trreb-history/release-bundle-20260924.json
```

Files are exclusively created, never silently overwritten. Review the
manifest's archive SHA and every source-family/period/SHA pin before treating
the resulting release ID as approved. The draft command refuses missing or
multiple report vintages. For revisions, explicitly choose one validated SHA
for each of the required 102 tables (72 monthly, six annual, 24 rental); do not
choose by retrieval timestamp. Preparation copies the SQLite database into a
temporary snapshot, selects only those pinned revisions there, audits the full
coverage and original PDF hashes, checks parser versions, then emits the
public resale subset. Original revisions remain intact in the source archive.

The portable bundle is private release material, not a public download. It
contains a canonical SHA over the manifest, audit summary and observations.
This is content integrity, **not a publisher signature or independent audit**.
Import bundles only from the trusted preparation workflow, and pass the exact
previously reviewed release SHA separately. Both import and activation recheck
the complete release hash, coverage, municipal context, source pins and schema.
No self-rehashed malformed bundle is accepted.

## Import and activate

Configure `DATABASE_URL` securely in the operator environment, never in chat,
source files, shell arguments or committed env files. The CLI normalizes the
existing application's supported PostgreSQL URLs. Apply normal application
migrations first (`alembic upgrade head`); schema changes use the existing
deployment process. Importing an artifact is a separate deliberate operation:

```text
python -m etl.trreb_release import-bundle --bundle ../out/trreb-history/release-bundle-20260924.json --approved-release APPROVED_RELEASE_SHA
python -m etl.trreb_release status
python -m etl.trreb_release activate --release APPROVED_RELEASE_SHA --expected-active none --reason "Reviewed initial 2020-2025 release"
```

Alternatively `import --root ... --manifest ...` performs a fresh local
archive audit immediately before the transactional database import. An exact
repeat import is idempotent; a conflicting existing release is rejected.
Any row-write failure rolls back the entire import. Neither command enables
public access or changes the active pointer. `activate` locks/compares the
previous pointer, validates the stored release and records an event in the
same transaction. For replacement releases pass the exact previous SHA as
`--expected-active`, never `none` or an inferred latest version.

Enable backend `TRREB_PUBLIC_ENABLED=1` only after activation; verify:

```text
GET /api/trreb/resale/3520005?year=2020&month=1
GET /api/trreb/resale/3519036?year=2025
```

Verify source values/provenance match the private prepared release, unsupported
tracts return 404, invalid periods return 422, and CSV/compare/map endpoints
remain unchanged. No active release, missing data or corrupt observation returns
503; a disabled flag returns 404. Responses use `Cache-Control: no-store` so
rollback is not delayed by a CDN. The API remains out of OpenAPI listings while
this gated rollout is being verified. No writes are exposed publicly.

Only then build/deploy the frontend with `NEXT_PUBLIC_TRREB_ENABLED=1` and
verify real API-backed desktop/mobile journeys, URL persistence, yearly vs
monthly dates, source links, loading/retry and no tract fallback. The public
switch is separate from `NEXT_PUBLIC_TRREB_PREVIEW_ENABLED`, which remains
development-only. A successful code deployment with flags off is **not** a
completed public data launch.

If the free hosting account has no shell and no authorized database connection
is configured, stop at prepared/import-ready artifacts. Do not expose database
credentials through browser tools, add an unauthenticated import endpoint,
commit the artifact or purchase hosting to bypass that access limitation.

## Rollback and update discipline

To immediately stop serving data while retaining the immutable releases:

```text
python -m etl.trreb_release activate --release none --expected-active CURRENT_RELEASE_SHA --reason "Disable pending investigation"
```

To restore a previously validated release, activate its exact SHA with the
current pointer as `--expected-active`; this revalidates the stored payloads.
Disable backend and frontend flags for a full feature shutdown. An already
open client may retain data it previously received until it changes selection
or reloads; no browser push-revocation mechanism is claimed.

Do not downgrade migrations as a routine data rollback: migration downgrade
deletes these tables and their history. Keep database backups consistent with
the application's existing backup policy. Source-revision updates are manual:
retain PDFs, re-import a changed fingerprint, review pins, prepare/audit a new
release, test it, import and explicitly switch. Never silently refresh the
active release. Rentals require their own later product/release decision.

## Verification

`tests/test_trreb_release.py` exercises complete synthetic history, original
archive immutability, revised report selection, bad hashes/parser versions,
malformed/rehashed bundles, atomic write failure, idempotency, activation,
stale-operator rejection, disable/restore, provenance and HTTP fail-closed
behaviour. `tests/test_trreb_postgres.py` exercises import, publication locking,
reads and rollback in a random temporary PostgreSQL schema; it requires the
dedicated `POSTGIS_TEST_DATABASE_URL` and does not touch seeded public tables.
CI also upgrades/downgrades/upgrades all migrations.

Local SQLite tests do not substitute for Postgres CI. Synthetic browser tests
do not substitute for a real archive/API-backed journey. Record actual results
for the exact proposed commit and production deployment; do not treat this
runbook as evidence that hosted import/activation has already occurred.
