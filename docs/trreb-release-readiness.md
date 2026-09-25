# TRREB release readiness — September 24, 2026

> Superseded for the public dashboard by the owner-approved September 25
> [Vercel archive release](trreb-vercel-archive.md). The readiness notes below
> describe the earlier PostgreSQL pathway, not the current default delivery.

## Release scope

The repository now includes a separately gated public resale pathway, backed
by immutable approved releases in the existing PostgreSQL database. Both
public flags default off. Importing data does not activate it. See
[production operations](trreb-production-operations.md) for the explicit
prepare/import/activate/rollback sequence and technical release gates.

No TRREB PDFs, extracted market values, database, audit export, release bundle
or credentials are included in Git. Browser fixtures use invented numbers.
The earlier loopback-only development preview remains separate. Public
downloads, rental display and automatic updates remain disabled. No paid
infrastructure is required.

The owner confirms aggregate-statistics permission and explicitly authorized
proceeding without another permission review. Missing clauses are not a
blocker for this scope. This records the owner's instruction, not an
independent legal assessment. Source attribution and market/geography
disclosures remain required implementation safeguards.

## Geography evidence and limitations

The crosswalk is explicit in `backend/app/services/trreb_preview.py` and tested
against the 25 Census IDs and their parent regions in CivicScope's packaged
geographies. It links reporting-area **context**, not spatially interchangeable
polygons. No fuzzy matching, tract allocation or parent-region fallback occurs.

| TRREB reporting grouping | CivicScope municipal rows | Disposition |
| --- | --- | --- |
| City of Toronto | Toronto | Use city total, never Toronto West/Central/East or all-area total |
| Peel Region | Mississauga, Brampton, Caledon | Individual municipal rows only |
| Halton Region | Burlington, Halton Hills, Milton, Oakville | Individual rows; preserve regional reconciliation warnings |
| York Region | Aurora, East Gwillimbury, Georgina, King, Markham, Newmarket, Richmond Hill, Vaughan, Whitchurch-Stouffville | Explicit aliases for Stouffville and legacy E. Gwillimbury |
| Durham Region | Ajax, Brock, Clarington, Oshawa, Pickering, Scugog, Uxbridge, Whitby | Missing rental rows remain unavailable |
| Dufferin/Simcoe and Toronto subdivisions | Outside the 25-municipality detail crosswalk | Retain source records only; no invented municipal/tract joins |

Evidence reviewed:

- [TRREB Market Watch archive](https://trreb.ca/market-data/market-watch/market-watch-archive/): source municipal rows and their region grouping across the retained 2020–2025 corpus.
- [August 2026 Market Watch](https://trreb.ca/wp-content/files/market-stats/market-watch/mw2608.pdf), page 27 note 10: naming clarification for Stouffville/Whitchurch-Stouffville and Bradford/Bradford West Gwillimbury, recorded in the earlier pilot review.
- [TRREB community reports](https://trreb.ca/market-data/community-reports/) lists Whitchurch-Stouffville separately; its [2025 Q2 report](https://trreb.ca/wp-content/files/market-stats/community-reports/2025/Q2/WhitchurchStouffvilleQ22025.pdf) identifies a municipal community breakdown. This corroborates naming, not polygon equivalence. The research search index exposed these references; direct research fetches returned 403 during this review.
- [TRREB's current Market Watch notice](https://public.trreb.ca/market-data/market-watch/) warns that participating-board additions changed current historical data relative to static reports. Preserve the archived-report vintage; do not silently mix it with the revised dashboard series.

**Unresolved:** no authoritative, versioned TRREB-to-Census polygon crosswalk
was established for 2020–2025. Neither matching names nor a current municipal
boundary dataset proves equivalence over that period. Before any polygon join,
obtain the relevant reporting-boundary definitions/vintages and validate
splits, overlaps and exceptions. Until then, retain the explicit reporting-area
disclaimer and do not add TRREB map colouring or census-tract figures.

## Repeatable checks

1. Run backend `pytest`, including `test_trreb_history.py`, `test_trreb_audit.py`,
   `test_trreb_pilot.py` and `test_trreb_preview.py`.
2. Re-import all three report families locally; run `backend.etl.audit_trreb`.
   Only accept a zero exit status, with source reconciliation warnings retained.
3. Run frontend unit tests, typecheck, lint and production build.
4. With the core API available, run `npm run test:e2e:trreb`. Its own loopback
   frontend on port 3105 enables the development-only section and intercepts
   only TRREB responses with synthetic fixtures. Tests cover Chromium, Firefox
   and WebKit; year/month changes, municipality changes, no tract fallback,
   failed requests/retry, source attribution, keyboard navigation, accessibility,
   390px mobile overflow and 1440px desktop map-height stability.
5. Run the existing dashboard regressions with the preview flag off.

These are automated tests, not human usability sessions. Synthetic browser
tests verify UI behaviour; the separate real-corpus audit and local API checks
verify source extraction and data delivery. Neither substitutes for the other.

## Controlled release checklist

### Historical preview verification (September 23)

- Re-extracted 72 monthly tables, six year-end tables and 24 rental tables;
  the strict audit reports no errors, with all source discrepancies retained.
- All 1,950 supported municipal month/year lookups return the matching geography
  and nonmissing headline metrics from the newly audited database.
- 59 TRREB backend regression tests passed on the isolated release branch.
- All 15 dedicated TRREB browser cases passed across Chromium, Firefox and
  WebKit, including 390px/1440px keyboard, overflow, accessibility and map sizing.
- 67 frontend unit tests, typecheck, lint and production build passed.
- The existing dashboard suite and hosted CI are additional release gates;
  their results must be checked on the proposed commit, not inferred from these.

- [ ] All CI checks green on the exact proposed commit.
- [x] Owner authorized proceeding with aggregate-statistics display.
- [x] Geographic use limited to labeled reporting context; authoritative
  vintage-specific boundary equivalence would still be required before any map joins.
- [x] Explicit per-period SHA selection, including functional selection among
  multiple retained revisions; no implicit latest-wins.
- [x] Transactional import and immutable-release/pointer tables implemented in
  existing PostgreSQL. Local SQLite lifecycle tests are separate from real
  Postgres CI tests.
- [x] Read-only public API and independent default-off backend/frontend flags.
- [ ] Approved artifact imported into production's durable database. This
  requires an authorized database connection; free Render shell limitations
  do not justify upgrading hosting or publishing private files in Git.
- [ ] Preview acceptance, then deliberate production activation and smoke checks.
- [ ] Rollback rehearsed: disable the section/API and restore the prior approved
  artifact/version, preserving the source archive and audit trail.

Code can be deployed with flags off before data activation. Do not enable the
frontend until the selected backend release is imported, activated and verified.
Passing local tests or a prepared private bundle does not prove hosted activation.
No claim of Census polygon equivalence is made.
