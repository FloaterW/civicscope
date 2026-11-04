"""Reject input changes that CI's committed locks do not actually satisfy.

Run from any directory: python backend/scripts/check_dependency_locks.py
pip's --require-hashes installation remains responsible for artifact integrity.
Run after installation on the target OS: distribution metadata validates that
platform's requested extras and their transitive dependencies, not just names.
"""

from importlib import metadata
from pathlib import Path
import re
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _lines(path):
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending += line.removesuffix("\\") + " "
        if line.endswith("\\"):
            continue
        yield re.sub(r"\s+--hash=\S+", "", pending).split(" #", 1)[0].strip()
        pending = ""
    if pending:
        raise ValueError(f"Unfinished continuation in {path.name}")


def _requirements(path, *, required=True, ancestors=(), environment=None):
    path = path.resolve()
    if path in ancestors:
        raise ValueError(f"Circular requirements include: {path.name}")
    for line in _lines(path):
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            option, name = line.split(maxsplit=1)
            yield from _requirements(
                path.parent / name, required=required and option in ("-r", "--requirement"),
                ancestors=(*ancestors, path), environment=environment,
            )
        else:
            requirement = Requirement(line)
            if requirement.url:
                raise ValueError(f"Unpinned direct URL in {path.name}: {requirement.name}")
            if requirement.marker is None or requirement.marker.evaluate(environment):
                yield requirement, required


def _pins(lock, environment=None):
    pins = {}
    for requirement, _ in _requirements(lock, environment=environment):
        specifiers = list(requirement.specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==" or "*" in specifiers[0].version:
            raise ValueError(f"{lock.name}: {requirement.name} must have one exact version")
        name = canonicalize_name(requirement.name)
        version = specifiers[0].version
        if name in pins and pins[name] != version:
            raise ValueError(f"{lock.name}: conflicting pins for {name}")
        pins[name] = version
    return pins


def validate_lock(source, lock, *, environment=None):
    pins = _pins(lock, environment)
    errors = []
    for requirement, required in _requirements(source, environment=environment):
        name = canonicalize_name(requirement.name)
        version = pins.get(name)
        if version is None:
            if required:
                errors.append(f"{lock.name}: missing required package {name}")
        elif version not in requirement.specifier:
            errors.append(f"{lock.name}: {name}=={version} does not satisfy {requirement.specifier}")
    return errors


def validate_installed_closure(source, lock, *, environment=None, distribution=metadata.distribution):
    """Check native installed metadata against pins, including requested extras.

    Environment/distribution injection supports offline platform fixtures; a
    foreign marker override alone does not verify foreign wheel metadata.
    """
    pins = _pins(lock, environment)
    pending = [(req, source.name) for req, required in _requirements(source, environment=environment) if required]
    seen, errors = set(), []
    while pending:
        requirement, parent = pending.pop()
        name = canonicalize_name(requirement.name)
        version = pins.get(name)
        if version is None:
            errors.append(f"{lock.name}: {parent} requires missing locked package {name}")
            continue
        if version not in requirement.specifier:
            errors.append(f"{lock.name}: {parent} requires {requirement}, locked {name}=={version}")
            continue
        key = (name, frozenset(requirement.extras))
        if key in seen:
            continue
        seen.add(key)
        try:
            installed = distribution(name)
        except metadata.PackageNotFoundError:
            errors.append(f"{lock.name}: {name}=={version} is not installed")
            continue
        if installed.version != version:
            errors.append(f"{lock.name}: installed {name}=={installed.version}, expected {version}")
            continue
        extras = {canonicalize_name(extra) for extra in requirement.extras}
        provided = {canonicalize_name(extra) for extra in installed.metadata.get_all("Provides-Extra", [])}
        if extras - provided:
            errors.append(f"{lock.name}: {name} does not provide extras {sorted(extras - provided)}")
        for raw in installed.requires or []:
            dependency = Requirement(raw)
            if dependency.marker is None or any(
                dependency.marker.evaluate({**(environment or {}), "extra": extra})
                for extra in {"", *extras}
            ):
                pending.append((dependency, str(requirement)))
    return sorted(set(errors))


def main():
    backend = Path(__file__).resolve().parents[1]
    try:
        errors = [error for name in ("requirements", "requirements-dev")
                  for validate in (validate_lock, validate_installed_closure)
                  for error in validate(backend / f"{name}.in", backend / f"{name}.lock")]
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("Dependency inputs and locks disagree:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print("Dependency inputs, locks and installed dependency closure (including extras) agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
