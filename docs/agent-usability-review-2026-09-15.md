# Five-agent usability review — September 15, 2026

Five distinct agents were requested by the user. This is agent-based testing, not five human participants, physical-device testing or screen-reader certification. Agents were read-only; the main agent implemented repairs and regression tests.

| Perspective | Work actually performed | Findings |
| --- | --- | --- |
| First-time renter | Production browser: Toronto search, topics, metric changes and help activation | Confirmed invisible activated tooltip and transient false missing-data message. Historical rents and ratio wording needed clarity. |
| Policy analyst | Source review; 30 existing export/format/URL tests passed | Construction stock/flow period mismatch; comparison provenance hidden; overbroad full-profile CSV promise; negative numeric CSV cells escaped as text. Live API verification was blocked for this agent. |
| Keyboard/accessibility | Static code, existing-test coverage and CSS contrast calculations | Visible/accessibility name mismatch; Escape explicitly blurred search. Tab-to-result focus and transit disclosure order flagged for follow-up, not claimed as live observations. No screen reader used. |
| Mobile resident | Production browser at 390×844 and 320px width; search, comparison, guidance, transit controls | Confirmed expanded transit panel clipping. No horizontal document overflow. Search selection opens details below viewport; some secondary targets are small. |
| Slow connection / recovery | Source/test review; six deadline/cancellation tests passed | Technical network messages and raw proxy-error text; cancellation/keyed state protections present. No measured live cold-start duration. |

## Repairs and verification

- Preserve tooltip position when an already-open preview is activated. Added hover/focus/click/keyboard visibility regression.
- Preserve search focus on Escape and restore it after result activation; accessible name includes the visible label.
- Show pending/failed CMHC requests distinctly from confirmed missing values.
- Constrain the expanded transit panel to its map container and scroll its content. Added containment and Clear all interaction regression.
- Explain annual starts/completions versus December construction/inventory snapshots.
- Add historical-survey-versus-current-listing warning, explicit rent-to-income heading, and field provenance in comparison rows.
- Narrow CSV documentation to exported topics; keep negative decimal numbers numeric while still neutralizing formula-like cells.
- Replace raw HTML/oversized proxy errors and technical connectivity copy with bounded recovery messages.

The first focused browser run passed six checks and failed one new test because its generic tooltip locator matched two briefly overlapping help previews. The assertion was narrowed to the intended tooltip; this was not concealed by retries. Complete rerun counts and release status are recorded in `reliability-work-2026-09-15.md`.

## Remaining usability opportunities

- Mobile selection could offer a visible jump to details and an easier add-to-comparison action. Do not automatically move focus/scroll without testing the intended flow.
- Review secondary touch targets and transit disclosure keyboard order separately.
- Add full dwelling/tenure CSV coverage if useful; the current export now states its narrower scope honestly.
- Real-person sessions remain valuable: ask unfamiliar participants to choose an area, explain rent burden versus rent-to-income, identify each figure's source/year, compare two areas, and find/export details on a phone. Record unassisted completion, misunderstandings and obstacles; do not turn agent results into human success rates.
