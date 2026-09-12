# Agent-simulated researcher usability testing

Session began September 4, 2026; report persisted September 5, 2026 after a session interruption.

Target: https://civicscope-gold.vercel.app/

Persona: municipal researcher with an emphasis on interpreting source periods, comparing areas, exporting evidence, and keyboard access.

This is an agent-simulated usability review, not a study with human participants. Findings describe observed interactions and targeted source inspection. They do not establish how frequently real users would encounter a problem, constitute a complete accessibility audit, or prove every export works.

## Results

The interface supports routine geography lookup, metric changes, historical municipal CMHC data, readable source explanations, keyboard definitions, and responsive browsing. One confirmed data correctness bug mislabels 2024 tract survey-zone data as other years. Custom multi-area comparison cannot be completed with the available controls. Comparison exports also omit information needed to interpret a saved file independently.

| Task | Result | Evidence |
| --- | --- | --- |
| Search and select Toronto using the keyboard | Passed | Search announced one result and arrow-key guidance. ArrowDown set `aria-activedescendant=search-option-3520005`; Enter selected Toronto, closed results, updated details and URL. |
| Interpret Toronto affordability | Passed | Details showed 40.0% rent burden, $84,000 median household income, $1,500 median rent, and Census 2021. Rent-burden definition explained the 30% threshold and distinguished it from core housing need. |
| Change municipal metric and year | Passed | Vacancy rate exposed a CMHC year selector with 2018–2025. Toronto changed from 2.8% in 2025 to 1.1% in 2018. Snapshot cards retained their explicit Census 2021 label. |
| Interpret missing municipal data | Passed with limitation | Markham vacancy in the 2025 comparison read `Not available`; caption and introductory text announced one missing area. The table does not state the specific reason for that missing value. |
| Compare Toronto, Ajax, and Oakville as a custom set | Not supported | Selecting Ajax added Ajax to five defaults; selecting Oakville replaced Ajax with Oakville. No add, pin, or remove controls were present. See R2. |
| Switch to census tracts and inspect source detail | Passed except historical zone values | Search for `0576.98` found Brampton census tract 0576.98 (`5350576.98`). Details explained survey-zone values, parent-municipality fallbacks, construction allocations, and partial transit coverage. See R1. |
| Reopen a shared tract view | Passed | Opening the observed URL `/?level=census_tract&metric=rent_burden_pct&geoid=5350576.98` in a separate tab restored Census tracts and the Brampton tract details. |
| Open and dismiss a definition by keyboard | Passed | Enter expanded the rent-burden definition, linked its text through `aria-describedby`, and showed a clear focus ring. Escape changed `aria-expanded` to false. |
| Export comparison CSV | Inconclusive browser delivery; content limitation confirmed in code | The download event did not arrive within 15 seconds after activating Export CSV. No console warning/error accompanied the attempt. This alone does not prove an app export failure. Source review confirmed missing period/provenance columns; see R3. |
| Phone layout, requested viewport 390×844 | Passed inspected flows | No document horizontal overflow: document/client width both 375px after scrollbar. Controls stacked, values wrapped, map controls and legend remained usable, selected details collapsed and reopened, and the comparison table fit. |
| Tablet layout, requested viewport 768×1024 | Passed overflow check | Document/client width both 753px after scrollbar. A screenshot captured during scrolling is insufficient for a complete visual verdict. |

Browser viewport overrides were coordinated with the other tester and reset when finished. Testing used isolated agent-created tabs; the existing user tab was not changed.

## R1 — P1: tract survey-zone values use the wrong year

Reproduction:

1. Choose Vacancy rate and CMHC year 2018.
2. Choose Census tracts, search `0576.98`, and select Brampton census tract 0576.98.
3. Read the `Rental Market — Oct 2018 RMS` section: vacancy is 3.6% and average rent is $1,870.
4. Change CMHC year to 2025. The section says `Oct 2025 RMS`, but vacancy remains 3.6% and average rent remains $1,870. Bedroom rents, rental-universe counts, and construction values change with the year.

Confirmed cause at the time of inspection: `backend/app/data/cmhc_zone_rms.csv` records Brampton (West), year **2024**, vacancy 3.6%, average rent 1870. `backend/app/api/routes.py` function `_load_zone_rms` discarded the CSV year and keyed records by zone name. The CMHC serializer selected that zone record without matching the requested year, then returned the municipality record's year. The UI and comparison therefore present a 2024 observation under both 2018 and 2025 labels.

Impact: historical and current tract rent/vacancy analysis can reach incorrect conclusions, and exports inherit the mismatched period. This is a correctness issue rather than merely unclear copy.

Recommended correction: key zone records by zone and year. Use zone values only for the requested year; otherwise use the matching-year municipal fallback and label it inherited, or show unavailable if no matching-year value exists. Cover 2018, 2024, and 2025 in API/serialization and relevant UI regression tests.

## R2 — P2: the comparison set cannot be chosen explicitly

Reproduction:

1. Select Toronto and inspect the panel labelled `selected municipalities`.
2. Search Ajax and select it. The comparison contains Ajax, Toronto, Mississauga, Brampton, Markham, and Vaughan.
3. Search Oakville and select it. Oakville replaces Ajax; the five defaults remain.
4. Try retaining Toronto, Ajax, and Oakville together. No visible add, remove, or pin action supports that task.

The wording implies that the user chose the whole comparison set, although five members are defaults. Tract selection similarly narrows the table to the current tract instead of enabling deliberate multi-tract comparison.

Highest-value next feature supported by this session: an explicit comparison set with Add to comparison, Remove, Clear/reset, and URL persistence. This solves a directly attempted analytical task. A period-aware CSV should travel with that set. This evidence does not yet justify accounts, saved collections, or a PDF reporting system.

## R3 — P2: comparison CSV lacks period and provenance

After the browser export attempt, source inspection of `frontend/components/ComparisonPanel.tsx` confirmed the exported headers contain Area, Geoid, the metric, Status, and optionally transit metadata or rent-to-income ratio. They omit the selected data year, measurement period, and CMHC source/method. The filename also omits the year.

A saved vacancy CSV therefore cannot distinguish 2018 from 2025 on its own. The generic `available` status also loses whether a tract value is a survey-zone measurement or municipal fallback. By comparison, the geography export builder in `frontend/lib/csv-export.ts` already includes Period, Source, Method, and Status.

Recommended correction: give comparison CSV the same period and provenance discipline as geography CSV, and include a meaningful period in the filename. Verify that missing values remain empty with an explicit status rather than becoming zero.

## Additional usability notes

- Census 2021 is the only Census year and its disabled selector has no descriptive explanation. A short explanation could make the disabled control less puzzling.
- Brampton tract transit details correctly warn that the packaged snapshot omits Brampton Transit. A displayed zero route count is consequently not proof of no local transit; preserve that warning whenever the metric is exported or compared.
- Brief intermediate states during metric changes displayed unavailable CMHC/unknown transit wording before the request settled. These were transient and are not evidence of persisted missing data, but loading-specific wording would be clearer.
- No console warnings/errors were captured in the focused check following the CSV attempt. This is not a comprehensive performance or error-monitoring result.

## Retest status

The findings above describe the production baseline observed during the initial session. Corrections and a targeted retest should be recorded below without replacing that baseline evidence.
