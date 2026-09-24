# TRREB public-report import pilot

Historical pilot record. For the current approved scope, explicit revision
selection, public-release implementation and remaining technical activation
gates, see [release readiness](trreb-release-readiness.md). The owner has since
authorized proceeding without another permission review; the historical
permission follow-up below is superseded, not an active blocker.

## Outcome

Public PDF extraction is feasible. A normal direct HTTPS download succeeded,
although the research browser returned HTTP 403. No access controls were bypassed.
The user reports written permission for aggregate statistics; its attribution,
public-display, retention and redistribution conditions have not been reviewed.
No production data, API responses, UI or public CSV exports were changed.

## Tested reports

| Report | Source | Result |
| --- | --- | --- |
| March 2026 | https://trreb.ca/hlfiles/pdf/mw_march_2026_546717147136789.pdf | 41 source areas, page 3 |
| July 2026 | https://trreb.ca/wp-content/files/market-stats/market-watch/mw2607.pdf | 41 source areas, page 3 |
| August 2026 | https://trreb.ca/wp-content/files/market-stats/market-watch/mw2608.pdf | 41 source areas, page 3 |
| August 2025 | https://trreb.ca/wp-content/files/market-stats/market-watch/mw2508.pdf | 41 source areas, page 3 |

The archive supplied these canonical month links during a direct request:
https://trreb.ca/market-data/market-watch/market-watch-archive/
This is a four-report compatibility sample, not certification of the entire archive.
Downloaded PDFs and candidates are local, ignored artifacts under `out/`.
Each candidate records its source URL, SHA-256, extraction timestamp, page,
report period, property type, market universe and as-published vintage.

## Extraction and validation

`backend/etl/pilot_trreb.py` extracts the monthly **all-home-types resale** table:
sales, dollar volume, average and median prices, new and active listings,
SNLR trend, inventory trend, sale/list ratio, listing days and property days.
Trend measures retain their labels; they are not recomputed as simple monthly ratios.

Naive PDF text extraction interleaves invisible duplicate figures with visible
rows and includes oversized invisible `Abc` marks. The parser uses the source
area label baseline, small body glyphs and fixed column positions instead.
All four summary pages were rendered and visually inspected.
Visible Toronto subdivision figures in August independently round to a dollar
more than the printed Toronto total. Dollar reconciliation permits only the
mathematical whole-dollar rounding bound; count reconciliation remains exact.

Checks reject unexpected columns, dimensions, areas, duplicates, missing rows,
wrong periods, ambiguous/YTD summaries, invalid numbers and broken totals.
Average price is checked against dollar volume / sales within one printed dollar.
Suppression markers stay null and are not back-calculated from totals.
Synthetic tests exercise hidden glyphs, units, missingness and validation failures.
No copyrighted PDF or full extracted table is committed to the repository.

Verification: the final parser passed all four downloaded reports. The focused
TRREB/Census/refresh run passed 54 tests. The full backend suite passed 277 tests
with 4 skipped; skipped tests are not counted as verified. No frontend changes
were made, so browser testing was not part of this isolated parser pilot.

## Geography assessment

The 41 rows include regional totals and Toronto subdivisions. There are candidate
labels for all 25 packaged CivicScope municipalities: 23 name matches plus
`City of Toronto` -> `Toronto` and `Stouffville` -> `Whitchurch-Stouffville`.
August 2026 report page 27, note 10 explicitly confirms the Stouffville alias
(and Bradford for Bradford West Gwillimbury). This resolves the name ambiguity,
but name correspondence is not a geometric boundary-equivalence check.
The importer deliberately emits source labels, not Census IDs. Region totals
must never be added to their child municipalities. Toronto districts and additional
Simcoe/Dufferin areas remain separate; there is no census-tract allocation.
Verify geographic definitions before joining report values to Census polygons.

## Reproducible local pilot

Use an extraction environment with `pdfplumber==0.11.9` (tested here). This is
optional tooling, not a new production API dependency. Run from the repository root:

```text
python backend/etl/pilot_trreb.py --pdf out/trreb-mw2608.pdf --period 2026-08 --source-url https://trreb.ca/wp-content/files/market-stats/market-watch/mw2608.pdf --output out/trreb-august-reviewed-candidate.json
```

Output is exclusively created; existing files cannot be overwritten. Every
candidate is explicitly staging-only, with public display and public export false.
The script accepts a locally downloaded PDF and does not autonomously fetch or
schedule reports. A changed layout fails closed and needs a new reviewed adapter.

## Next publication gates

1. Review permitted-use conditions when available. User-reported permission is
   acknowledged, not treated as absent; exact attribution/export terms are pending.
2. Verify municipal boundary definitions before polygon joins; the Stouffville
   name alias is confirmed by the source's own notes.
3. Add a separate TRREB resale data model and UI section. Do not reuse Census
   affordability or CMHC rental fields. Keep periods and property types explicit.
4. Review extraction across the desired archive interval before enabling refresh.
   Store immutable report hashes and replacement versions; no silent overwrites.
5. Decide a historical series policy: TRREB warns that additions to its participating
   boards changed historical data. Do not mix revised dashboard history with static
   reports without identifying vintages. See https://public.trreb.ca/market-data/market-watch/.
6. Treat the separate rental report as another adapter and quarterly lease-market
   universe. It is not covered by this resale parser and cannot replace CMHC vacancy,
   rental-stock measures or Census rent burden. See https://trreb.ca/market-data/.

No scheduled scraping, bulk archive ingestion, public deployment or rental parser
has been enabled by this pilot. These are explicit remaining steps, not completed work.
