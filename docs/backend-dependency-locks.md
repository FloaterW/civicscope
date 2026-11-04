# Backend dependency locks

Production and CI use CPython 3.12. Both committed locks must include dependencies
for Linux deployment and Windows development. Uvicorn's `standard` extra requires
`uvloop` on CPython Linux, even though Windows does not install it. A Windows-only
`pip-compile` run omits that dependency; a passing base-version check or `pip check`
does not validate requested extras.

Generate portable hash locks using **uv 0.13.7**, installed in a separate tooling
environment. From the repository root:

```sh
python -m pip install uv==0.13.7
uv pip compile backend/requirements.in --universal --python-version 3.12 --generate-hashes --no-strip-markers --index-url https://pypi.org/simple --output-file backend/requirements.lock
uv pip compile backend/requirements-dev.in --universal --python-version 3.12 --generate-hashes --no-strip-markers --index-url https://pypi.org/simple --output-file backend/requirements-dev.lock
```

Existing pins are retained unless inputs require a change or an explicit
`--upgrade-package` is supplied. Generate the runtime lock first: the development
input constrains its runtime packages to that lock. Review conditional packages
and hashes along with version changes. Do not replace universal resolution with
host-only compilation or manually remove foreign-platform entries. Universal
resolution can emit markers for other platforms/interpreters; it does not extend
the project's tested support beyond CPython 3.12 on Linux and Windows.

After installing the development lock with `python -m pip install --require-hashes
-r backend/requirements-dev.lock`, run:

```sh
python backend/scripts/check_dependency_locks.py
python -m pip check
pip-audit --require-hashes -r backend/requirements.lock
pip-audit --require-hashes -r backend/requirements-dev.lock
python -m pytest backend/tests
```

The checker validates input ranges, runtime/development parity and the installed
dependency graph, including requested and transitive extras. It rejects missing
lock entries even when an unrelated installed package happens to satisfy them.
Run it natively on each target OS; Windows metadata cannot prove Linux wheel
compatibility. The existing Linux CI audit step runs this checker after the hashed
install, and the regression suite includes the previously missed Linux-only
Uvicorn dependency. Cross-platform wheel downloads are additional evidence, not
a substitute for Linux CI and the production image check.

References: [Uvicorn 0.54.0 metadata](https://pypi.org/pypi/uvicorn/0.54.0/json),
[uv universal resolution](https://docs.astral.sh/uv/concepts/resolution/),
[pip-tools cross-environment guidance](https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile).
