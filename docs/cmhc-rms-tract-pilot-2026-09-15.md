# Official rental-unit counts: diagnostic pilot

Date: 2026-09-15. Decision: **do not promote these records to application data yet**.

## What was actually retrieved

The public CMHC HMIP export table `2.1.26.6` returned October 2025 rental-universe counts by census tract for Toronto, Oshawa and Hamilton. The dwelling filter was explicitly `Row / Apartment`, matching the existing RMS loader. These are rental-unit counts, not average rents, vacancy rates, listings, or counts of all rented homes.

The table identifier and export parameters were discovered from the [official Toronto rental-universe table](https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/TableMatchingCriteria?CategoryLevel1=Primary+Rental+Market&CategoryLevel2=Rental+Universe&ColumnField=2&GeographyId=2270&GeographyType=MetropolitanMajorArea&RowField=23). Raw exports, parsed cells and SHA-256 hashes are retained locally under `out/cmhc-rms-tract-pilot-2025-20260915`. That directory is research output, not packaged application data.

## Observed coverage

| CMHC metropolitan area | Export tract rows | Published units | Sum of tract totals | CivicScope tracts | Exact identifiers with a published total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Toronto | 660 | 343,539 | 343,539 | 1,194 | 646 |
| Oshawa | 30 | 6,231 | 6,231 | 92 | 7 |
| Hamilton | 38 | 22,712 | 22,712 | 48 | 11 |
| Combined | 728 | 372,482 | 372,482 | 1,334 | 664 |

All three published metropolitan totals reconcile. Every exported tract row has a published total, although some bedroom-specific cells are suppressed. Only 664 of the application's 1,334 identifiers match (49.8%). The remaining 670 application tracts are **unresolved, not zero**. Another 64 source identifiers are outside the application's identifier set; the application's GTA selection and metropolitan-area extent are not identical, and historical splits can also matter. This pilot does not assign a cause to each mismatch.

An exact identifier match is only a candidate join. It does not establish equivalent geometry or prove that every count can be called an official value for CivicScope's 2021 tract boundaries.

## Boundary investigation

The source page identifies its breakdown field as historical census-tract geography. Its export footnote refers to 2021 definitions for CMA, CA and CSD; that is not an explicit guarantee of the tract-boundary vintage.

CMHC's public [historical census-tract layer](https://geospatial.cmhc-schl.gc.ca/server/rest/services/CMHC_APPS/HMIP_HISTORIC_CAWD/FeatureServer/0) describes annually accumulated boundaries. A read-only distinct-year query for metropolitan area 2270 returned historical years 2010–2016 and a null current-year field. That layer alone therefore does not verify the 2025 export's geometry. Do not assume its latest returned historical year is the export's vintage.

Statistics Canada publishes [2021 tract boundaries](https://www150.statcan.gc.ca/n1/en/catalogue/92-168-X2021001) and [geographic correspondence products](https://www150.statcan.gc.ca/n1/en/catalogue/92-156-X). The next integration gate is to identify the export's actual geometry/year, compare it with CivicScope's 2021 geometry, and classify exact matches versus changed/split boundaries. A crosswalk can explain a split; distributing a parent's units across children remains an estimate, not a newly published official tract count.

## Safety and verification

The standalone pilot rejects an unexpected table schema, period or dwelling universe; preserves suppression flags and genuine zeros; rejects duplicate rows and unknown numeric formats; and never infers suppressed bedroom cells from totals. Output must be a new directory beneath `out`, is published only after all three responses parse, and cannot overwrite an earlier run. It does not update CSVs, the seed, database or dashboard.

Twelve offline tests pass, including wrong-response handling, duplicates, suppression, zeros, atomic failure, no overwrite and unchanged seed data. The live three-area retrieval succeeded. Raw numerical data are not committed, and no production data were replaced.

## Recommendation

Proceed with a boundary-verified, field-specific integration in a separate change. Use published totals only where geography and period are verified; retain an explicit unavailable or estimated label elsewhere. Keep the source universe and suppression semantics visible. Do not present this pilot as proof that all estimates can be removed or that official tract rents are available. TRREB licensing and its different MLS-market population remain a separate decision.

Reproduce from the repository root:

```text
python backend/etl/pilot_cmhc_rms_tracts.py --year 2025 --output out/a-new-pilot-directory
```
