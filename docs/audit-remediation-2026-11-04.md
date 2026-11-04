# Audit remediation — November 4, 2026

This release addresses the reviewed application, dependency, data-quality and GitHub Actions findings. The fixes retain separate commits and are tested together before production. The [CI workflow](https://github.com/FloaterW/civicscope/actions/workflows/ci.yml) and [dependency-security workflow](https://github.com/FloaterW/civicscope/actions/workflows/dependency-security.yml) hold the authoritative results for each commit; a local pass is not a production deployment claim.

## Changes

| Area | Result |
| --- | --- |
| Security | Next.js and its companion tooling updated together to 16.4.5; Vitest to 4.1.12. Python runtime and development locks audited, with pytest 9 replacing the unpatched pytest 8 line. No incompatible forced ESLint downgrade. |
| Backend reliability | Quoted production proxy arguments and process handoff; safe Alembic URL interpolation; bounded ASCII geography IDs; Census and transit endpoints tolerate absent supplemental CMHC data. |
| Dashboard recovery | Local map style is available immediately, external basemap loading has a timeout and retry, and civic/transit layers survive style recovery. CSV export is blocked while requested CMHC data is pending or failed; rental/construction retry is explicit. |
| Statistical meaning | Regional weighted approximations are identified rather than presented as exact regional medians. Selected-geography values and source notes remain separate from regional summaries. |
| Card and search behavior | Census, CMHC and resale cards share typography and two-line label space. The WebKit search race is fixed without selecting on mouse press; drag cancellation, keyboard navigation, taps and outside dismissal remain usable. |
| Chart/style maintenance | Recharts 3.10.1 and Tailwind/PostCSS 4.3.3 retain the dashboard palette, layout and focus affordances. Chart labels stay readable at narrow widths while tables/tooltips retain exact values. Map attribution remains readable in both themes. |
| CMHC corrections | Ninety audited bedroom-rent cells corrected across three municipalities and eight years, including eight newly null values. A hash-pinned, guarded migration preserves unrelated/custom data and never reseeds production. |
| Source evidence | The unchanged Census observations were independently checked against the official November 2 SDMX refresh while preserving original bulk-CSV provenance. Changed transit data remains unpublished. Future transit exports use LF before hashing. |
| Dependency consistency | Development resolution is constrained to the runtime versions. Lock validation checks requested versions and native installed dependency closure, including extras. Portable lock generation includes Linux-only Uvicorn dependencies. |
| CI and operations | Real container startup, PostgreSQL migration tests, immutable Action references, and scheduled runtime/tooling vulnerability checks complement browser/build tests. Availability incidents and source-verification issues are tracked separately. |

## Verification

Backend tests cover API validation, supplemental-data failures, seed protection, all-cell CMHC migration comparisons, custom-value preservation, concurrent updates, source hashes and dependency-lock regressions. PostgreSQL-specific checks run against disposable CI databases; local skips are not counted as PostgreSQL verification.

Frontend verification includes unit tests, lint, strict types, clean production builds and Chromium/Firefox/WebKit journeys. It covers desktop and mobile layouts, light/dark themes, map and panel sizing, data recovery, comparison charts, keyboard tooltips, report history, real bundled TRREB archive values, accessibility and the reproducible search failure. The final CI suite reruns the integrated code, including the newly added search regressions. Test fixtures and agent testing are not recruited human usability sessions.

Native touch-scroll cancellation is automated through Chromium's protocol; Firefox/WebKit tap and keyboard journeys are covered separately. Windows WebKit's thin variable-font rendering was reproduced on the pre-upgrade application and in a plain-font test; it was not corrected by changing unrelated application styles. Real devices remain useful for additional usability testing.

Production release verification checks the deployed Git commit, representative real browser journeys, API responses and all corrected CMHC values. Evidence is recorded with the release PR after deployment. Protected Vercel runtime logs require the owner's team authorization and are not inferred from a successful public smoke test.

## Remaining work and intentional holds

- The full npm audit retains moderate minimatch findings in development lint tooling. Production npm audit and high/critical gates are separate checks; do not describe this as zero vulnerabilities everywhere. Keep compatible upstream fixes under review.
- TypeScript 7 remains outside the active ESLint integration's supported range. Node 22 and Python 3.12 remain the deployment targets. Future Node 26/Python 3.14 migrations must align runtime, typings, lock generation and CI together.
- The refreshed transit candidate changes agency coverage, route counts and relative scores. Preserve raw feeds, evaluate service calendars and review the normalization/method disclosure before a separately reviewed data promotion. See the [source review](source-refresh-review-2026-11-04.md).
- Tailwind 4 targets modern browsers (Safari 16.4+, Chrome 111+, Firefox 128+). Automated browser engines are not proof of support for every older browser or physical device.
- Hosting remains free. Render cold starts and delayed scheduled workflows remain possible; monitoring and recovery improvements do not create an always-on service.

Further evidence: [CMHC correction](cmhc-bedroom-correction-2026-11-04.md), [dependency review](dependency-review-2026-09-15.md), [operations](launch-operations.md).
