# Official data source review — September 15, 2026

## Recommendation

Use **official-source-first data with explicit geography, period, method and missingness**. More published tract data is feasible; a complete official number for every metric and tract is not established. No dataset is promoted by this research.

CMHC's official survey estimates are different from CivicScope allocating municipal counts to tracts. Eliminating the latter can improve fidelity; eliminating all statistical estimation is not realistic. A published-only view would intentionally show more gaps and omit custom scores.

## Source matrix

| Measures | Primary source | Decision / limitation |
| --- | --- | --- |
| Population, income, shelter costs, rent burden, dwellings and tenure | Statistics Canada 2021 Census Profile | Already used. Prefer published CT/CSD values; preserve suppression and audit remaining modeled rent-burden fallbacks. |
| Average rents, vacancy, rental universe | CMHC RMS / HMIP | Tract tables exist, but not every cell is available or reliable. Pilot direct tract rental-universe counts, then rent/vacancy with quality flags and boundary checks. |
| Starts and completions | CMHC Starts and Completions Survey | Published tract values already ingested for supported periods. Validate individual metric-years before expanding coverage. |
| Under construction / unabsorbed inventory | CMHC construction / absorption tables | December stocks, not calendar-year flows. Verify tract availability table by table; broader-area context must not masquerade as a tract observation. |
| Condo lease rents / transactions | TRREB Rental Market Report | Potential separate MLS lease-market context, not a replacement for CMHC vacancy, rental stock or Census rent burden. Verify reuse rights first. |
| Affordability, rent-to-income, growth | CivicScope calculations from Census inputs | Derived indicators, not directly published official statistics. Keep formulas and periods visible. |
| Transit score / nearby routes | Agency GTFS plus CivicScope spatial calculation | Official inputs do not make our custom index an official agency statistic. Preserve partial-coverage labels. |

Primary references: [Census Profile downloads](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm), [Statistics Canada developer services](https://www.statcan.gc.ca/en/developers), [CMHC RMS tables](https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/rental-market/rental-market-report-data-tables), [CMHC construction tables](https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/housing-market-data).

The official [Toronto tract rental-universe table](https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/TableMatchingCriteria?CategoryLevel1=Primary+Rental+Market&CategoryLevel2=Rental+Universe&ColumnField=2&GeographyId=2270&GeographyType=MetropolitanMajorArea&RowField=23) demonstrates that tract-level rental data exists. This does not establish complete, exact-boundary coverage of our 1,334 tracts.

## Methodology corrections

RMS is an annual October sample of eligible rental structures. Average rents include occupied and vacant units, not simply new-lease asking rents. Confidentiality and reliability rules suppress some estimates. Preserve reliability grades. The 10% coefficient-of-variation threshold for averages/totals is **not** the universal rule for vacancy rates: proportions have different criteria. CMHC discontinued availability rates in 2018. See [official RMS methodology](https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-research/surveys/methods/methodology-rental-market-survey).

The older `cmhc-census-tract-data-audit.md` is historical; its blanket CV rule must not guide a new loader. Coverage including parent allocations is not all exact-tract official data. Check boundary correspondence against [Statistics Canada geography documentation](https://www150.statcan.gc.ca/n1/pub/92-160-g/92-160-g2021001-eng.pdf), not just similarly named identifiers.

## Incident #42

The September 14 refresh required two metrics × three CMAs × seven years: 42 slices. A September 15 read-only rerun validated 36 and found six empty completions slices: 2023–2024 for Toronto, Oshawa and Hamilton. Direct Toronto exports explicitly reported an archived series. The linked intended-market alternative and December cumulative variant also supplied no replacement for that Toronto annual slice.

The packaged CSV already has **no nonempty completions cells for 2023 or 2024**. Starts cover 2018–2024; completions cover 2018–2022. The refresh incorrectly turned the union of years into a requirement for both metrics in every year. This is not evidence that six previously packaged slices disappeared.

The fix derives supported years separately for each metric, validates every requested slice against its CMHC total, and rejects loss of any previously nonempty tract/metric/year cell. Explicit archived-data requests still fail with an actionable error. Transport retries are bounded; access errors are not bypassed. No partial-publication override is used.

Evidence: [incident #42](https://github.com/FloaterW/civicscope/issues/42), [September 14 failed run](https://github.com/FloaterW/civicscope/actions/runs/34854129316), packaged CSV and September 15 direct export probes. Candidate results are recorded in the work report.

## TRREB

[TRREB Rental Market Report](https://public.trreb.ca/market-data/rental-market-report/) reports MLS condo lease transactions and rents; [Market Watch](https://public.trreb.ca/market-data/market-watch/) addresses resale activity. These are primary industry sources, not government Census data or the entire rental market.

Public report content was discoverable through search, but direct retrieval was restricted during this investigation. I have not verified an unrestricted bulk API or redistribution licence for CivicScope. Confirm the exact permission, permitted ingestion method, reporting geography and revision policy before adding a feed. Do not scrape member systems, accept paid terms or contact providers without authorization. Initially, link to reports as separate context rather than mixing their values into CMHC fields.

## Follow-up implementation sequence

1. Validate the supported-period refresh correction and review its isolated candidate before promotion.
2. Pilot official RMS tract-universe ingestion for Toronto, Oshawa and Hamilton, retaining raw responses, quality flags, identifiers and reference periods.
3. Measure coverage and boundary compatibility. Use validated published values; preserve missing cells and separate broader-zone context.
4. Add direct tract rents/vacancy only after quality checks. Consider a CMHC custom extract where public exports are insufficient; confidentiality restrictions may still prevent publication.
5. Add TRREB only as a separately named layer after permission review. Keep custom affordability/transit measures labelled derived.

Acceptance gates: matching measure/universe and period; correct boundaries; preserved zero versus missing; no reconstruction of suppressed values; no lost supported cells; matching provenance across map, detail, comparison and export; reproducible refresh and source evidence.
