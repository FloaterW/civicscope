# TRREB historical database: 2020–2025

## Delivered

A separate, local SQLite database was built and audited before UI integration.
The source corpus is the public TRREB archive retrieved September 20, 2026.
All figures retain the vintage of the downloaded report; they are not asserted
to be TRREB's currently revised historical series.

| Dataset | Reports/periods | Source-area records | Scope |
| --- | ---: | ---: | --- |
| Monthly resale | 72 of 72 | 2,952 | January 2020–December 2025, all home types combined |
| Annual resale | 6 of 6 | 246 | Actual year-end YTD tables from December reports |
| Quarterly apartment leases | 24 of 24 | 965 | Separate MLS apartment-rental reports |
| Bedroom-specific lease observations | Same 24 quarters | 3,860 | Bachelor, one-, two-, three-bedroom |

Monthly and annual resale tables each have 41 reporting areas: municipal rows,
regional totals and Toronto subdivisions. They must not be summed together.
Rental tables report 41 areas through 2024, then 35, 36, 37 and 37 in the four
2025 quarters. Omitted areas stay absent, not zero. See `full-audit.json` for
every missing area by quarter.

Not included: individual resale property-type tables, Toronto's smaller MLS
district tables, HPI, individual listings, transactions, rental townhouses,
census-tract allocations, or periods outside 2020–2025. All original PDFs are
retained locally, so additional table adapters can be built later.

## Artifacts

Local, ignored artifacts (not uploaded to GitHub or deployed):

- `out/trreb-history/trreb.sqlite`: historical database.
- `out/trreb-history/full-audit.json`: coverage, integrity, fingerprints, missing
  areas, source reconciliation discrepancies and year-end vintage differences.
- `out/trreb-history/resale-downloads.json` and `rental-downloads.json`: URL,
  retrieval timestamp, archive fingerprint, PDF fingerprint and local filename.
- `out/trreb-history/*.pdf`: 96 source PDFs, named with their SHA-256 fingerprints.
- Rendered evidence pages and region crops are retained in the same folder.

Database tables: `reports`, `resale`, `rental`, `rental_bedrooms`,
`quality_issues`, and `settings`. The `reports` table has separate families
for monthly resale, annual resale and quarterly rental; source period, page,
URL and fingerprint accompany each imported table. Foreign keys link figures
to the exact report. Uniqueness prevents accidental duplicate observations.

## Findings

### Actual annual statistics matter

Annual figures come from each December report's year-end table, not
sums/averages of the monthly snapshots. Extracted market figures and the
analysis table remain in ignored private artifacts, not the public repository.
These are nominal, mixed-property statistics, not inflation-adjusted or
same-home price changes. Reporting coverage and transaction mix can change.

Sources: page 5 of the official December [2020](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2012.pdf),
[2021](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2112.pdf),
[2022](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2212.pdf),
[2023](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2312.pdf),
[2024](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2412.pdf), and
[2025](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2512.pdf) reports.

### Vintage differences are material

233 of 246 area/year sales totals differ between the sum of archived monthly
figures and the December YTD figure. The database retains both, and the UI uses the actual annual table for
"Full year". It never averages monthly medians or silently changes vintages.

TRREB's report notes say past monthly and YTD values are revised. Its current
[Market Watch page](https://public.trreb.ca/market-data/market-watch/) also warns
of historic changes following additions to its participating boards. This
database is therefore an archived-report series, not a reconstructed current
history. The exact cause of every individual discrepancy has not been established.

### Source totals do not always reconcile

There are 32 resale parent/child discrepancies across monthly and annual
tables, and two rental discrepancies (Halton, Q4 2024). The affected visible source
rows were spot-checked against rendered PDFs; the data was not altered to
force reconciliation. The report-wide discrepancy inventory is in the audit.

Extraction validation and source reconciliation are separate concepts:
an imported table may be structurally valid while the publisher's totals do
not reconcile. These issues are retained explicitly, and relevant resale
preview periods show a warning. No residual is allocated to a municipality.

### Rental rents are not CMHC rents

The rental series describes MLS apartment leases, not CMHC rental stock,
vacancy or Census shelter costs. Zero leases means no observed average rent.
Older PDFs print `$0` in such cells: the original value is retained in
`raw_average_rent`, while the usable average is null and marked
`no_transactions`. Source blanks remain missing. Quarter-level bedroom lease
counts are checked against the reported total for every imported row.

## Geography matching

The 25 CivicScope municipalities are matched to the corresponding TRREB
municipal reporting rows, with an explicit source-area and parent-region pair.
Tests verify both the municipality ID set and parent-region membership against
the packaged Census geography records. No fuzzy matching is used.

- `City of Toronto` is the city total, not Toronto West/Central/East or the GTA total.
- `Stouffville` and `Whitchurch-Stouffville` are treated as the same reporting
  municipality, supported by TRREB's own naming note (August 2026, page 27,
  note 10) and the full name used by older reports.
- `E. Gwillimbury` in legacy rental tables is normalized to East Gwillimbury,
  distinct from Bradford West Gwillimbury in Simcoe.
- Peel, Halton, York and Durham totals are not substituted for municipal rows.
- Simcoe/Dufferin areas remain in the source database without being invented
  as CivicScope municipalities. Missing quarterly municipality rows stay missing.

The reports' municipal-unit definitions, region grouping and naming notes were
checked. **Exact spatial equivalence to Census polygons is not certified.**
The new section is labeled reporting-area context, not a TRREB choropleth or
tract estimate. A licensed boundary/crosswalk source is still needed before
claiming exact spatial equivalence.

## Import and validation design

- Official HTTPS archive links only; no member login or access-control bypass.
- Bounded downloads with immutable fingerprinted filenames. Normal runs reuse
  verified cached PDFs. Explicit `--refresh` rechecks URLs while retaining old files.
- A new fingerprint creates a separate database report version. The audit
  blocks ambiguous multiple vintages until an explicit selection policy is applied.
- Legacy and modern layouts have separate reviewed adapters. May 2022 contains
  two painted table layers; the adapter excludes the obsolete hidden layer.
- Rental PDFs require handling displaced duplicate labels and a small vertical
  difference between label and numeric baselines. Regression tests cover both.
- Unknown layouts, wrong periods, duplicate source areas, invalid numbers and
  inconsistent row-level price/count relationships fail parsing.
- Aggregate reconciliation discrepancies are recorded, not erased or described
  as fully reconciled. Whole-dollar totals allow only a bounded rounding difference.
- Source hashes, SQLite integrity, foreign keys and period coverage are audited.
- Parser code fingerprints are stored per report; changed monthly parsers
  automatically invalidate the extraction cache. `--reprocess` forces a rebuild
  even when code is unchanged. Original fingerprinted PDFs remain untouched.
- Failed monthly reprocessing marks the report failed and removes its stale
  observations. A fresh successful audit is required before preview reads resume.
- Legacy numeric rows with unknown labels fail closed. Reviewed rental area
  sets distinguish published omissions from accidental lost rows. A narrowly
  scoped exception handles the 2020-Q2 header's superscript footnote row.
- Audits reject stale parser fingerprints, missing per-report resale areas and
  missing rental bedroom records (including zero-transaction records).
- Monthly/rental commands return nonzero for failed downloads or parses. Always
  require the final full audit before accepting a candidate; importer success
  alone is not a full-archive coverage certificate.
- Annual medians are imported from year-end tables. Annual stocks/ratios not
  printed there remain null rather than being summed or averaged.

## Local UI preview

The "Resale market — TRREB" accordion offers 2020–2025 and either a calendar
month or the actual full-year table. It displays median sale price, sales and
property days on market with a direct report/page citation. Requests are lazy,
cancelled on changes and keyed by geography/period to avoid stale numbers.
The existing map retains its height when the section opens or closes.

The preview is **development-only**. Backend access requires the explicit
preview switch, development mode, a local client, a configured SQLite path
and a successful audit matching the database fingerprint. Reads use SQLite
read-only mode and HTTP `no-store`. Production and non-local requests are
rejected. No TRREB figures were added to existing exports or comparison charts.
The separate rental importer is complete, but there is no rental UI in this change.

The owner confirms aggregate-statistics permission and authorized proceeding
without another permission review. As of September 24, a separate default-off
public resale pathway is implemented using immutable approved releases in the
existing PostgreSQL database. Production activation requires an audited,
explicitly selected artifact, authorized database access and verification—not
another permission-clause request. Data downloads and scheduled updates stay
off. See [production operations](trreb-production-operations.md).

## Reproduction

Use an extraction environment with `pdfplumber==0.11.9`; SQLite is included in
Python. From the repository root:

```text
python -m backend.etl.trreb_archive --root out/trreb-history --family resale
python -m backend.etl.trreb_archive --root out/trreb-history --family rental
python -m backend.etl.trreb_history --root out/trreb-history
python -m backend.etl.trreb_annual --root out/trreb-history
python -m backend.etl.trreb_rental --root out/trreb-history
python -m backend.etl.audit_trreb --root out/trreb-history
```

For the local API, set `APP_ENV=development`, `TRREB_PREVIEW_ENABLED=1` and
`TRREB_DATABASE` to the absolute SQLite path. Bind the API to loopback and
allow only the chosen local frontend origin. For the frontend dev server, set
`NEXT_PUBLIC_TRREB_PREVIEW_ENABLED=1` and point `NEXT_PUBLIC_API_URL` at that API.
These switches cannot enable the section in a production frontend build.
The separate public pathway uses `NEXT_PUBLIC_TRREB_ENABLED=1` and
`TRREB_PUBLIC_ENABLED=1`, and never reads workstation SQLite paths.

## Verification performed

- All 96 PDF fingerprints and all 102 imported periods/tables audited.
- Complete 72-month, six-year and 24-quarter coverage; SQLite integrity and
  foreign keys pass. Source discrepancies retained separately.
- All 1,950 municipal/month-or-year service lookups checked for the correct
  geography and nonmissing headline values.
- Full backend suite: 298 passed, four skipped. Latest focused TRREB suite:
  48 passed, including the subsequently added overlapping-row test.
- Frontend: 67 unit tests, type checking, lint and production build passed.
- In-app browser: loaded the local dashboard; checked annual/monthly switches,
  geography changes, light/dark rendering, source warning and no error overlay;
  measured identical map height with the new section open and closed.
- Temporarily stopped only the task's local preview backend, confirmed a clear
  unavailable/retry state without stale values, restarted it and verified recovery.

No claim is made of human usability sessions, an exhaustive manual check of
every PDF cell, or new cross-browser/mobile verification during this task.

The above verification records the initial September 20 implementation.
See [release readiness](trreb-release-readiness.md) for subsequent hardening,
repeatable browser tests, current release gates and the geography evidence review.
