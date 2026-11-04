"""Reject input changes that CI's committed locks do not actually satisfy.

Run from any directory: python backend/scripts/check_dependency_locks.py
pip's --require-hashes installation remains responsible for artifact integrity.
"""

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


def _requirements(path, *, required=True, ancestors=()):
    path = path.resolve()
    if path in ancestors:
        raise ValueError(f"Circular requirements include: {path.name}")
    for line in _lines(path):
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            option, name = line.split(maxsplit=1)
            yield from _requirements(
                path.parent / name, required=required and option in ("-r", "--requirement"),
                ancestors=(*ancestors, path),
            )
        else:
            requirement = Requirement(line)
            if requirement.url:
                raise ValueError(f"Unpinned direct URL in {path.name}: {requirement.name}")
            if requirement.marker is None or requirement.marker.evaluate():
                yield requirement, required


def validate_lock(source, lock):
    pins = {}
    errors = []
    for requirement, _ in _requirements(lock):
        specifiers = list(requirement.specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==" or "*" in specifiers[0].version:
            raise ValueError(f"{lock.name}: {requirement.name} must have one exact version")
        name = canonicalize_name(requirement.name)
        version = specifiers[0].version
        if name in pins and pins[name] != version:
            raise ValueError(f"{lock.name}: conflicting pins for {name}")
        pins[name] = version
    for requirement, required in _requirements(source):
        name = canonicalize_name(requirement.name)
        version = pins.get(name)
        if version is None:
            if required:
                errors.append(f"{lock.name}: missing required package {name}")
        elif version not in requirement.specifier:
            errors.append(f"{lock.name}: {name}=={version} does not satisfy {requirement.specifier}")
    return errors


def main():
    backend = Path(__file__).resolve().parents[1]
    try:
        errors = [error for name in ("requirements", "requirements-dev")
                  for error in validate_lock(backend / f"{name}.in", backend / f"{name}.lock")]
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("Dependency inputs and locks disagree:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print("Dependency inputs and runtime/development locks agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
