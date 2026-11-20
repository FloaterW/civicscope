# Backend dependency locks

Production and CI use CPython 3.12. Both committed locks must include dependencies
for Linux deployment and Windows development. Uvicorn's `standard` extra requires
`uvloop` on CPython Linux, even though Windows does not install it. A Windows-only
`pip-compile` run omits that dependency; a passing base-version check or `pip check`
does not validate requested extras.

The canonical pairs are `requirements.in` / `requirements.txt` and
`requirements-dev.in` / `requirements-dev.txt`. The `.txt` files remain fully
hashed locks, not loose inputs. Dependabot discovers pip-compile pairs by these
extensions and must stage the runtime `.txt` constraint alongside the development
input. `backend/.python-version` declares the supported Python 3.12 series.

Generate portable hash locks using **uv 0.13.7**, installed in a separate tooling
environment. From the repository root:

```sh
python -m pip install uv==0.13.7
uv pip compile backend/requirements.in --universal --python-version 3.12 --generate-hashes --no-strip-markers --index-url https://pypi.org/simple --output-file backend/requirements.txt
uv pip compile backend/requirements-dev.in --universal --python-version 3.12 --generate-hashes --no-strip-markers --index-url https://pypi.org/simple --output-file backend/requirements-dev.txt
```

Existing pins are retained unless inputs require a change or an explicit
`--upgrade-package` is supplied. Generate the runtime lock first: the development
input constrains its runtime packages to that lock. Review conditional packages
and hashes along with version changes. Do not replace universal resolution with
host-only compilation or manually remove foreign-platform entries. Universal
resolution can emit markers for other platforms/interpreters; it does not extend
the project's tested support beyond CPython 3.12 on Linux and Windows.

After installing the development lock with `python -m pip install --require-hashes
-r backend/requirements-dev.txt`, run:

```sh
python backend/scripts/check_dependency_locks.py
python -m pip check
pip-audit --require-hashes -r backend/requirements.txt
pip-audit --require-hashes -r backend/requirements-dev.txt
python -m pytest backend/tests
```

The checker validates input ranges, runtime/development parity and the installed
dependency graph, including requested and transitive extras. It rejects missing
lock entries even when an unrelated installed package happens to satisfy them.
Run it natively on each target OS; Windows metadata cannot prove Linux wheel
compatibility. Linux backend CI and the Windows dependency job run this checker
after hashed installs. The regression suite includes the previously missed
Linux-only Uvicorn dependency and supported-file discovery. Cross-platform wheel
downloads are additional evidence, not a substitute for Linux CI and the
production image check.

Dependabot can now stage the complete input/constraint pairs. Its native
`pip-compile` updater does not promise universal resolution, so review its lock
diffs and require both OS checks before merging. If a bot update loses platform
entries, regenerate both locks with the commands above on the update branch.
Python minor/major Docker upgrades and Node type majors beyond the Node 22
runtime require a deliberate compatibility migration rather than an automatic
version bump. CodeQL init/analyze updates are grouped so their versions stay equal.

References: [Uvicorn 0.54.0 metadata](https://pypi.org/pypi/uvicorn/0.54.0/json),
[uv universal resolution](https://docs.astral.sh/uv/concepts/resolution/),
[pip-tools cross-environment guidance](https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile),
[Dependabot file discovery](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/shared_file_fetcher.rb),
[Dependabot lock pairing](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/pip_compile_file_matcher.rb),
[Dependabot pip-compile updater](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/file_updater/pip_compile_file_updater.rb).
