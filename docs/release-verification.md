# Verify a deployed CivicScope release

The maintained smoke command checks the exact frontend and backend Git revisions,
then exercises a small set of real read-only dashboard/API flows. Use it after
normal CI and deployment. It records structured results and screenshots so a
healthy older deployment cannot be mistaken for the requested release.

## Setup and offline checks

Supported tooling is Node 22, the committed frontend npm lock, and its matching
Playwright Chromium browser. The backend's supported runtime remains CPython 3.12
on Linux and Windows; see [backend dependency locks](backend-dependency-locks.md).

From `frontend/` in a clean checkout:

```sh
npm ci
npx playwright install chromium
npm run test:release-tools
npm run smoke:release -- --check
```

Linux runners may need `npx playwright install --with-deps chromium`. Browser
installation is a setup action; the verification command itself installs nothing.
The unit tests and `--check` are offline and do not contact production.

## Run against an exact release

Replace both example SHAs with the full 40-character Git commit expected on each
service. The CLI verifies each exact identity independently. The automated
workflow uses current main unless it proves that an already deployed ancestor
has identical code and deployment inputs for that service, as described below.
From `frontend/`:

```sh
npm run smoke:release -- --run \
  --base=https://civicscope-gold.vercel.app \
  --api=https://civicscope.onrender.com \
  --expected-frontend-sha=0123456789abcdef0123456789abcdef01234567 \
  --expected-backend-sha=0123456789abcdef0123456789abcdef01234567 \
  --wait-for-release-seconds=1200 \
  --output=output/release-verification
```

Use a new output directory for every run. Relative paths are resolved against the
working directory: the example writes `frontend/output/release-verification/`.
Without `--output`, the script chooses a timestamped directory in the repository's
`output/release-smoke/`. Existing `results.json` evidence is never overwritten.

URLs must be credential-free origins without paths, queries or fragments. HTTPS
is required except for loopback development services. Full expected SHAs are
mandatory; missing or invalid release identity fails verification. Unknown and
duplicate CLI options are rejected.

The identity endpoints are frontend `/api/release` and backend `/health`.
Both send `Cache-Control: no-store`, and probe requests ask caches to revalidate.
The frontend uses `VERCEL_GIT_COMMIT_SHA`; the backend uses `RENDER_GIT_COMMIT`.
For local verification only, each supports `CIVICSCOPE_BUILD_SHA` when its hosting
provider variable is absent. Provider values are authoritative; malformed values
produce a null identity instead of exposing arbitrary environment content.
Backend identity must also report a healthy database. Identity is checked before
the user flows and again at the end.

The optional wait is bounded to 0–1,800 seconds (default zero). The automated run
allows 1,200 seconds for both resolved exact identities to become ready. A healthy
service with different or unverifiable code cannot satisfy the check.

## Scope, pacing and evidence

The command verifies selected CMHC API provenance/year cases, map/detail badges,
320px layout, municipality/tract changes, search, comparison/CSV behavior,
historical URL-state reloads and the TRREB archive. It records browser errors and classifies only
explicitly justified navigation cancellations and external map limitations.
Unexplained application/network errors fail the run, including errors observed
during browser cleanup.

Direct API and browser API starts share a pacing queue: public checks are at
least 3,500ms apart. Lower pacing is allowed only when both origins are loopback.
It uses anonymous reads, blocks application mutation requests, and does not
write to production data or promote source candidates. This is functional
verification, not a load test or a claim about continuous uptime. External map
assets remain browser-managed and are outside the API pacing queue.

Optional Vercel telemetry is excluded in the owned test browser: only same-origin
GET requests for `/_vercel/insights/script.js` and
`/_vercel/speed-insights/script.js` receive an empty script. Each exclusion is
recorded in `excludedTelemetryScripts`. This avoids generating test analytics
writes and means telemetry delivery itself is outside the verification scope.
All POST requests, including `/api/client-errors`, are still blocked and fail the
run. All application data responses come from the real verified services.

`results.json` includes expected/observed release identities, check outcomes,
request timing, error classifications and screenshot names. Screenshots and
accessibility snapshots support visual diagnosis. No login or production secrets
are supplied. Inspect failures before rerunning: increasing retries or accepting
unknown identities would conceal the condition this command is meant to detect.

## GitHub automation

[Verify deployed release](../.github/workflows/release-verification.yml) runs
after successful `CivicScope CI` **pushes to main in this repository**. PR runs,
forks and unsuccessful CI completions cannot execute it. Manual dispatch is
restricted to main. The workflow resolves the current main SHA from GitHub,
rejects an obsolete triggering revision, checks out that exact SHA without
persisted credentials and with full Git history, and checks again after setup
before contacting production.

Render's configured `rootDir: backend` can leave its deployed commit unchanged
when a commit only changes the frontend. The service-target resolver therefore
makes bounded anonymous reads of the fixed production identity endpoints (no
redirects, at most 75 seconds and 16KiB each). An older observed identity is used
only if the service is healthy, its full commit exists in the checkout, Git proves
it is an ancestor of target main, and a Git diff proves its service inputs are
unchanged. Backend comparison covers `backend/` and `render.yaml`; frontend
comparison covers `frontend/` and the explicit root build/runtime configuration
paths in `SERVICES.frontend.paths`. Both also compare root `.gitattributes` and
`.gitmodules`, which can affect checkout/submodule content. Pathspecs are anchored to the repository root,
independent of the workflow's `frontend/` working directory. External diff and
text-conversion programs, ignored submodule configuration and replacement objects
cannot mask differences.

Missing/invalid identity, unknown or nonancestor commits, changed service inputs,
and failed equivalence checks require target main instead. An unavailable target
commit stops the resolver. The strict smoke CLI still checks each resolved exact
SHA before and after the user flows. `release-targets.json` and the job summary
record target main, observed/expected service identities, compared paths and the
equivalence decision. This proof covers tracked code/configuration; external host
settings and secrets are not inferred from Git. Update the compared paths when
introducing new shared build inputs. See
[Render monorepo support](https://render.com/docs/monorepo-support).

A fixed concurrency group prevents overlapping production verification runs and
does not cancel an active probe. Queued stale revisions are skipped. The job has
read-only repository permissions; the GitHub token is supplied only to the two
revision-resolution steps, never to npm or browser verification. Evidence uploads
run even after failure and retain files for 30 days. A skipped or setup-failed run
may have no browser evidence.

The workflow verifies deployments; it does not trigger or promote them. A failed
probe is attached to that exact run/revision and does not reconcile operational
incident issues, so an obsolete run cannot close a newer incident. If main or a
deployment changes during a live probe, exact identity checks may fail; inspect
the recorded identities and verify the latest eligible release.

This targeted Chromium smoke complements full local/CI backend, PostGIS,
container and three-browser regression suites. It does not replace them, human
usability testing or independent data review. Transit/CMHC refresh artifacts stay
held as candidates until their definitions, provenance, deltas and replay have
been reviewed; successful release verification does not approve a candidate.
