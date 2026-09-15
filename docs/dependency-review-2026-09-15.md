# Dependency review — September 15, 2026

None of these PRs was merged or closed. Historical green checks do not prove compatibility with current main.

| PR | Evidence | Decision |
| --- | --- | --- |
| [#35 frontend group](https://github.com/FloaterW/civicscope/pull/35) | Recharts label formatter type error; container build fails because Tailwind's PostCSS integration was not migrated. | Do not merge. Split major migrations from routine updates, then test each. |
| [#30 backend group](https://github.com/FloaterW/civicscope/pull/30) | Only .in files change. CI/Docker install hashed .lock files, which are unchanged. | Regenerate and review both locks, audit, then rerun backend/PostGIS/container tests. Current green CI does not validate the proposed resolved versions. |
| [#24 Python 3.14 image](https://github.com/FloaterW/civicscope/pull/24) | Historical image build and CI pass, but tests still run on Python 3.12. | Plausible planned upgrade. Align runtime/tests and validate native dependencies and migrations on 3.14 before merge. |
| [#25 Node 26 image](https://github.com/FloaterW/civicscope/pull/25) | Historical build/CI pass; test runtime remains Node 22 and Vercel alignment is not demonstrated. Node 26 is Current, not LTS. | Hold. Prefer a separately tested Node 24 LTS migration, or retain supported Node 22 for now. |

Primary references: [Node release status](https://nodejs.org/en/about/previous-releases), [Python version status](https://devguide.python.org/versions/). Node recommends LTS for production; Python 3.14 and 3.12 are supported. Do not bundle these runtime changes into data/UI repairs.

Failed frontend evidence: [CI run 34699446816](https://github.com/FloaterW/civicscope/actions/runs/34699446816). No production dependencies were upgraded in this repair.
