# Release checklist

CivicScope is already hosted. Do not create a second repository, replace origin, amend old authorship, or provision duplicate services.

- Repository: https://github.com/FloaterW/civicscope
- Frontend: https://civicscope-gold.vercel.app/
- Backend health: https://civicscope.onrender.com/health
- Hosting stays free; cold starts remain possible. No paid upgrades are authorized.

## Before a release

1. Inspect local changes and preserve unrelated work. Use a focused `codex/` branch and review the diff.
2. Run frontend unit tests, type check, lint, production build, browser tests and backend tests. CI must also cover PostgreSQL/PostGIS and production containers. Record skipped or flaky checks.
3. Review data changes separately: periods, boundaries, provenance, suppression, coverage and candidate hashes. Successful refresh does not automatically promote data. Follow [launch operations](launch-operations.md).
4. Review dependency updates individually. Input manifests and resolved locks must agree; major upgrades require separate validation.
5. Push the branch and open a PR. Require current review/CI checks; do not bypass branch protection or force-push main.

## Deploy and verify

1. Merge only after required checks pass. Confirm Git-integrated Vercel and Render deployments refer to the intended commit; merge alone does not prove deployment.
2. Check backend health and an uncached production dashboard visit. Verify free-host cold-start recovery and clear error/retry messaging.
3. Test search, geography/metric/year switching, selected details, comparison, shared links and CSV exports.
4. Expand desktop topics: map size stays stable while details scroll. On mobile, test transit-panel containment, tooltips and keyboard access without horizontal page overflow.
5. Check data dates and representative values against the approved candidate. Missing values stay missing; zeros stay zero; estimates stay labelled.
6. Inspect browser errors and relevant server logs. Confirm a healthy Production health checks workflow result.

## Operations

- Validate data refresh creates isolated candidates; it never automatically promotes them.
- Production health checks uses best-effort scheduling and incident/recovery issues, not an always-on guarantee.
- Keep release and testing evidence dated. Agent simulations are not recruited human testing.
- Revert confirmed regressions through the reviewed workflow. Do not erase local files or overwrite data to hide a failed check.
