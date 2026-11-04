# Dependency review — September 15, 2026

## November 4, 2026 audit remediation

The hardening branch updates Next.js, its analyzer and ESLint configuration together to 16.4.5, Vitest to 4.1.12, and compatible transitive security fixes. A new Dependency security workflow audits the complete lockfile on PRs, main pushes and weekly schedules, enforcing high/critical severity for both production and tooling. It complements dependency-change review.

Local checks after these updates: production npm audit reports zero vulnerabilities; the full audit reports 16 moderate affected package entries caused by the minimatch globparts-amplification advisory (GHSA-g3hv-75wg-m249) in development lint tooling. No high/critical entries remain. Do not apply npm's suggested forced ESLint 4 / Next ESLint 12 downgrades: these are incompatible with the application. Keep monitoring upstream compatible resolutions; do not feed untrusted glob patterns to this tooling. This is a documented residual finding, not an audit suppression or claim of zero tooling vulnerabilities.

Major migrations remain separate from the security/reliability patch: Recharts 3 requires chart formatter changes, Tailwind 4 requires CSS/PostCSS migration and visual regression review, and TypeScript 7 must match the supported ESLint integration. Previously green PR checks are not a fresh security audit. No paid hosting or runtime-major change is part of this patch.

November dependency triage: TypeScript 7 is deferred because the active typescript-eslint 8.70.0 supports versions below 6.1; its major Dependabot PR is closed. Node 25 is obsolete and excluded from updates. Node 26 is now Active LTS and supported by Vercel; a migration must update Docker, package engines, CI, `.nvmrc` and typings together. Node 22 remains supported until April 2027, so retaining it during these fixes is supported. Python 3.14 has wheels for the locked native dependencies but still needs coordinated CI and migration testing before replacing 3.12. Backend dependency PR #46 changes inputs without regenerating locks; historical green CI did not exercise its proposed upgrades. Major backend updates are kept out of the routine minor/patch group.

Current references: [Node release schedule](https://raw.githubusercontent.com/nodejs/Release/main/schedule.json), [Vercel Node versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions), [Python 3.14 schedule](https://peps.python.org/pep-0745/), [typescript-eslint compatibility](https://typescript-eslint.io/users/dependency-versions/).

The September decisions below are historical context, not the current dependency inventory.

None of these PRs was merged or closed. Historical green checks do not prove compatibility with current main.

| PR | Evidence | Decision |
| --- | --- | --- |
| [#35 frontend group](https://github.com/FloaterW/civicscope/pull/35) | Recharts label formatter type error; container build fails because Tailwind's PostCSS integration was not migrated. | Do not merge. Split major migrations from routine updates, then test each. |
| [#30 backend group](https://github.com/FloaterW/civicscope/pull/30) | Only .in files change. CI/Docker install hashed .lock files, which are unchanged. | Regenerate and review both locks, audit, then rerun backend/PostGIS/container tests. Current green CI does not validate the proposed resolved versions. |
| [#24 Python 3.14 image](https://github.com/FloaterW/civicscope/pull/24) | Historical image build and CI pass, but tests still run on Python 3.12. | Plausible planned upgrade. Align runtime/tests and validate native dependencies and migrations on 3.14 before merge. |
| [#25 Node 26 image](https://github.com/FloaterW/civicscope/pull/25) | Historical build/CI pass; test runtime remains Node 22 and Vercel alignment is not demonstrated. Node 26 is Current, not LTS. | Hold. Prefer a separately tested Node 24 LTS migration, or retain supported Node 22 for now. |

Primary references: [Node release status](https://nodejs.org/en/about/previous-releases), [Python version status](https://devguide.python.org/versions/). Node recommends LTS for production; Python 3.14 and 3.12 are supported. Do not bundle these runtime changes into data/UI repairs.

Failed frontend evidence: [CI run 34699446816](https://github.com/FloaterW/civicscope/actions/runs/34699446816). No production dependencies were upgraded in this repair.
