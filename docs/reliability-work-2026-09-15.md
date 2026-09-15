# Reliability and official-source review

## Scope and status

- Completed locally: investigate and fix CMHC refresh requirements; research official sources. See `official-data-source-review-2026-09-15.md`.
- Completed locally: fix false missing-data messages during loading and improve network/proxy error copy. Free-host latency remains; no always-on claim.
- Completed: review PRs #24, #25, #30 and #35 individually; none merged. See `dependency-review-2026-09-15.md`.
- Completed: replace stale launch instructions with a release checklist and update operations references.
- Completed: five user-requested testing agents, consolidated findings and regression repairs. See `agent-usability-review-2026-09-15.md`. No recruited humans were tested.

## Evidence log

- The September 13 UI release is deployed as `0a8ef7f`; post-merge CI passed.
- September 14 CMHC candidate validation rejected 6/42 missing tract metric slices. Municipality ingestion completed; the candidate was not promoted and production data was not overwritten.
- September 15 direct probes returned 2018 and 2019 starts tables for Toronto, Oshawa and Hamilton. Historical-year withdrawal is therefore not established as the cause.
- The full probe found 36 valid slices. Six 2023–2024 completions slices were empty, with an explicit archived-series response verified for Toronto. Existing packaged data already has no completions for those two years: the requirement was a mistaken year cross-product, not lost packaged observations.
- The corrected loader requests separate supported metric-years, retries transient transport failures only, identifies archived/HTML/empty responses, and retains strict coverage validation. Candidate validation additionally rejects losing any previously populated tract/metric/year cell, including zeros.
- Live isolated CMHC refresh passed: 36/36 slices, 8,198 rows, 1,244 covered tracts (93.3%), 13,639 official metric values plus 269 parent allocations, no partial-output override. All existing tract records match the candidate semantically; file hash differs. Candidate remains in `out/cmhc-candidate-2026-09-15`, not promoted.
- All 200 municipal metric records also match the candidate semantically; changes are metadata/serialization rather than new observations.
- Public municipality map probe: 200 response in 33.18 seconds, repeat 200 in 1.11 seconds (193,517 bytes each). Consistent with warm-up latency, not conclusive proof of its full cause. Hosting remains free.

## Verification and handoff

- Backend: 223 passed, 4 skipped (PostGIS integration needs POSTGIS_TEST_DATABASE_URL; no disposable PostGIS configured locally).
- Frontend unit tests: 66 passed. Type check, lint and production build passed.
- Browser regression: 79 Chromium + 3 Firefox + 3 WebKit passed with no retries on the full rerun.
- First focused browser pass exposed an overly broad new tooltip test locator, corrected before the clean full rerun; no failing result hidden.
- Local production build loaded the selected Toronto profile with no captured browser errors. New tests cover persistent tooltip visibility, pending CMHC state, mobile transit containment, retained search focus, error-copy sanitization, CSV negative decimals, archived responses and supported-period refresh protection.
- Independent follow-up by the policy agent found no blocking issue in the refresh safety changes (static review).
- React review checklist applied to the component fixes; no new dependencies or runtime upgrades.
- Release authorized by the user after local verification. Preparing `codex/data-reliability-review` for PR/CI; deployment and remote refresh verification are pending. GitHub incident #42 must not be marked resolved until the corrected remote workflow succeeds.
- Local production frontend runs at http://127.0.0.1:3101 with the local test API on port 8000. These processes are temporary, not hosting replacements.

## Deferred intentionally

Official RMS tract ingestion remains a documented pilot, not an unvalidated migration. TRREB bulk access/redistribution permission is unverified. Existing estimates have not been silently removed or relabelled. Secondary mobile navigation/touch-target refinements and real-person testing remain opportunities, not claimed completions.

## Safety boundaries

Preserve official suppression markers, observation periods and geography definitions. Never relabel allocated values as official, substitute MLS lease data for all-rental vacancy rates, or promote partial candidates. Keep hosting free. No contact with data providers or test participants without authorization.
