# Resident and housing-advocate agent usability assessment

Date: 2026-09-04. Target: https://civicscope-gold.vercel.app/.

This is a task-based assessment performed by an AI agent acting as a first-time resident or housing advocate. It is not human participant research. Findings below describe observed interface behavior; predictions about user confusion are identified as usability judgments. The agent used its own browser tab and did not change production data, submit issues, or contact anyone.

## Task outcomes

| Task | Result | Observable evidence |
| --- | --- | --- |
| Find Toronto rent burden and explain it | Pass | Searched `Toronto`, chose `Toronto 3520005`; Housing snapshot, details, and table all displayed `40.0%`, Census 2021. The help button explained that this is the share of renter households spending 30% or more of before-tax income on shelter, and distinguished it from core housing need. |
| Compare Toronto and Oakville | Pass | Selecting Oakville displayed Oakville `45.8%` alongside Toronto `40.0%` and four other default peers. Exact values were available in a table, avoiding dependence on chart reading. |
| Compare two arbitrary municipalities, Oakville and Burlington | Fail: feature gap | Selected Oakville, then searched and selected Burlington. Oakville disappeared from the comparison. Table contained Burlington, Toronto, Mississauga, Brampton, Markham, and Vaughan. No visible add/pin/remove comparison control was present. This is a missing workflow, not a crash. |
| Reset a selected geography | Pass with a status defect | `Clear selected geography` restored GTA overview and removed `geoid` from the URL. After opening a shared view, its old loaded-view announcement remained after clearing and switching geography level. |
| Restore a municipality through its URL | Pass | Reloaded `?level=municipality&metric=rent_burden_pct&geoid=3524002`; Burlington and its `44.9%` rent burden were restored. |
| Restore a tract, metric, and year through its URL | Pass | Reloaded `?level=census_tract&metric=vacancy_rate&geoid=5350001.00&year=2025`; Toronto census tract 0001.00, Vacancy rate, CMHC 2025, and `2.9%` returned. There was no visible Copy/share-view button; browser URL sharing works. |
| Understand observed versus estimated tract data | Partial | Tract 5350001.00 showed Census rent burden `36.4%`, population growth and affordability marked `derived`, and construction counts marked `est.`. Its rental section explained survey-zone vacancy/average rent versus municipality fallback. Bedroom rents themselves had no adjacent fallback badge. |
| Find a familiar neighbourhood name | Partial: unsupported search vocabulary | In Census tracts mode, `Toronto` returned numbered census tracts. Searching `Parkdale` displayed `No census tracts match "Parkdale".` The no-result state provided no suggested valid query or recovery hint. |
| Understand unavailable data | Pass | Burlington details explicitly said `Not covered by the CMHC Rental Market Survey.` rather than presenting zero rent or vacancy. Tract map legends exposed a no-data count. |

## Ranked findings and recommendations

### P1 product opportunity: choose a comparison set

The application already offers a useful fixed peer comparison, but cannot retain two arbitrary places. Reproduction: in municipality mode select Oakville, observe its table row, then select Burlington. Oakville is replaced. The phrase `across selected municipalities` also suggests a user-selected set when only one geography was selected and all other peers are defaults.

Add an explicit `Add to comparison` action, visible removable place chips, a small sensible selection limit, and URL persistence for the chosen set. Keep an explicit explanation when default peers are shown. This recommendation is supported by an observed failed task; there is not yet evidence of demand from actual users.

### P2: put provenance next to inherited rental values

Reproduction: Census tracts → search Toronto → choose `Toronto census tract 0001.00 5350001.00`. In Rental Market, vacancy `2.9%` and average rent `$1,673` use Toronto (East) survey-zone values. Bedroom values show Bachelor `$1,443`, 1-bedroom `$1,746`, 2-bedroom `$2,127`, and 3-bedroom+ `$2,582`; section text says these are parent-municipality fallbacks, but the individual cells do not say so. Construction cells, by contrast, visibly carry `est.`.

Usability judgment: readers scanning or quoting one bedroom value may attribute it to the tract. Add `Municipal fallback` labels or equally clear accessible per-value context. A section note should explain why, while the value label should identify what geography the number describes. Do not label a surveyed municipal value as a directly observed tract value.

### P2: clear stale shared-view announcements when selection changes

Exact reproduction:

1. Open `https://civicscope-gold.vercel.app/?level=municipality&metric=rent_burden_pct&geoid=3524002`.
2. Wait for Burlington details and `Loaded the shared view for Burlington.`
3. Activate `Clear selected geography`.
4. Activate `Census tracts`.
5. The page correctly shows GTA tract overview, while the DOM status still reads `Loaded the shared view for Burlington.`

The announcement is emitted around `frontend/components/CivicDashboard.tsx:519` in the baseline code. Reset or update that status when clearing, changing selection, or changing level so assistive technology has current context. The core reset itself worked.

### P3: improve search vocabulary and recovery guidance

`Parkdale` produced a truthful no-match result, but a resident cannot infer the tract code from a neighbourhood name. A low-cost improvement is helper text such as `Search by municipality or census tract number` and a no-match hint such as `Try Toronto or a census tract number; neighbourhood names are not currently supported.` Address/postcode-to-tract lookup is a larger potential feature requiring a separate source and privacy decision; it should not be implied to exist now.

### P3: explain compact technical labels where they are encountered

The definition help for rent burden was strong. Remaining labels include `Ratio` in the comparison table, `RMS`, `GTFS`, `Rental universe`, `Unabsorbed`, and `Grouped by quantiles`. These are understandable to specialists but may require external research from a resident. Prefer `Rent-to-income` over `Ratio`, expand abbreviations, and give short local explanations for survey and construction terms. The unused Census year dropdown also appears selectable even though only 2021 exists; a static year label may communicate that constraint more directly.

### P3: expose working shared views as a visible action

The two reload tasks passed, so URL state is already a useful foundation. A `Copy view link` action with confirmation would help a first-time user discover that selections can be shared. It should preserve metric, geography level, selected place(s), and CMHC year.

## What worked well

- Search returned useful municipality results and supported discovery without manipulating the map.
- The selected geography name and data vintages appeared in the relevant sections.
- Exact comparison values were exposed in an accessible table next to the chart.
- Rent burden help explained the denominator, threshold, and distinction from core housing need.
- Official, derived, estimated, survey-zone, and missing-data concepts were disclosed in multiple relevant locations, with the per-value gap noted above.
- Clear-selection and deep-link reload paths completed without loss of the selected metric.
- No application console errors or warnings were captured in this tab during the sampled journeys.

## Limitations and exclusions

- This was one simulated resident workflow, not a statistically meaningful completion-rate study, not a substitute for 5–8 human sessions, and not evidence of actual user preferences.
- No production backend mutations, CSV-content audit, authentication flow, independent numeric source verification, or screen-reader audio testing was performed in this role.
- Other agents owned technical/data/accessibility testing. This report does not claim their results.
- A full-page screenshot briefly showed a clipped map canvas and changed responsive layout. A subsequent normal viewport screenshot after reload showed a fully rendered map. No agent reported changing the viewport; the issue could not be separated from screenshot capture behavior and is excluded as an unconfirmed capture artifact.
- No elapsed-time benchmark is claimed. Initial data loaded successfully during the session, but the backend might already have been warm.
- These are baseline production observations before the current implementation work. Fixes require a separate retest.
