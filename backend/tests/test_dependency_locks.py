from email.message import Message
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_dependency_locks import validate_installed_closure, validate_lock


def test_committed_locks_satisfy_inputs_and_runtime_constraints():
    backend = Path(__file__).resolve().parents[1]
    for name in ("requirements", "requirements-dev"):
        assert validate_lock(backend / f"{name}.in", backend / f"{name}.lock") == []
        assert validate_installed_closure(backend / f"{name}.in", backend / f"{name}.lock") == []


def test_input_minimum_cannot_silently_exceed_tested_lock(tmp_path):
    source, lock = tmp_path / "requirements.in", tmp_path / "requirements.lock"
    source.write_text("uvicorn[standard]>=0.53,<1\n", encoding="utf-8")
    lock.write_text("uvicorn==0.52.4 \\\n    --hash=sha256:abc\n    # via requirements.in\n", encoding="utf-8")
    assert validate_lock(source, lock) == [
        "requirements.lock: uvicorn==0.52.4 does not satisfy <1,>=0.53",
    ]


def test_development_lock_must_match_runtime_without_installing_constraint_only_packages(tmp_path):
    source, lock = tmp_path / "dev.in", tmp_path / "dev.lock"
    (tmp_path / "runtime.in").write_text("SQLAlchemy>=2,<3\n", encoding="utf-8")
    (tmp_path / "runtime.lock").write_text("sqlalchemy==2.0.54\noptional==1.0\n", encoding="utf-8")
    source.write_text("-c runtime.lock\n-r runtime.in\npytest>=8,<9\n", encoding="utf-8")
    lock.write_text("sqlalchemy==2.0.52\npytest==8.4.2\n", encoding="utf-8")
    assert validate_lock(source, lock) == ["dev.lock: sqlalchemy==2.0.52 does not satisfy ==2.0.54"]


def test_missing_active_requirement_is_rejected_and_inactive_marker_is_ignored(tmp_path):
    source, lock = tmp_path / "runtime.in", tmp_path / "runtime.lock"
    source.write_text('pytest>=8\nunsupported>=1; python_version < "2"\n', encoding="utf-8")
    lock.write_text("", encoding="utf-8")
    assert validate_lock(source, lock) == ["runtime.lock: missing required package pytest"]


def test_circular_include_fails_closed(tmp_path):
    source, lock = tmp_path / "runtime.in", tmp_path / "runtime.lock"
    source.write_text("-r runtime.in\n", encoding="utf-8")
    lock.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Circular"):
        validate_lock(source, lock)


def _distribution(version, requires=(), extras=()):
    fields = Message()
    for extra in extras:
        fields["Provides-Extra"] = extra
    return SimpleNamespace(version=version, requires=requires, metadata=fields)


def test_linux_standard_extra_requires_a_locked_and_installed_uvloop(tmp_path):
    source, lock = tmp_path / "runtime.in", tmp_path / "runtime.lock"
    source.write_text("uvicorn[standard]>=0.53,<1\n", encoding="utf-8")
    lock.write_text("uvicorn==0.54.0\n", encoding="utf-8")
    # Uvicorn 0.54.0's published Requires-Dist marker, with offline metadata.
    packages = {
        "uvicorn": _distribution("0.54.0", [
            'uvloop>=0.15.1; (sys_platform != "win32" and (sys_platform != "cygwin" '
            'and platform_python_implementation != "PyPy")) and extra == "standard"',
        ], ["standard"]),
        "uvloop": _distribution("0.23.0"),
    }
    linux = {"sys_platform": "linux", "platform_python_implementation": "CPython"}
    assert validate_lock(source, lock, environment=linux) == []
    assert "missing locked package uvloop" in validate_installed_closure(
        source, lock, environment=linux, distribution=packages.__getitem__,
    )[0]
    assert validate_installed_closure(
        source, lock, environment={**linux, "sys_platform": "win32"}, distribution=packages.__getitem__,
    ) == []
    lock.write_text('uvicorn==0.54.0\nuvloop==0.23.0; sys_platform != "win32"\n', encoding="utf-8")
    assert validate_installed_closure(source, lock, environment=linux, distribution=packages.__getitem__) == []

    def missing_uvloop(name):
        if name == "uvloop":
            raise metadata.PackageNotFoundError(name)
        return packages[name]

    assert validate_installed_closure(source, lock, environment=linux, distribution=missing_uvloop) == [
        "runtime.lock: uvloop==0.23.0 is not installed",
    ]


def test_transitive_extras_are_revisited_and_versions_checked(tmp_path):
    source, lock = tmp_path / "runtime.in", tmp_path / "runtime.lock"
    source.write_text("parent\nchild\n", encoding="utf-8")
    lock.write_text("parent==1\nchild==1\nleaf==1\n", encoding="utf-8")
    packages = {
        "parent": _distribution("1", ["child[optional]>=1"]),
        "child": _distribution("1", ['leaf>=2; extra == "optional"'], ["optional"]),
        "leaf": _distribution("1"),
    }
    assert validate_installed_closure(source, lock, distribution=packages.__getitem__) == [
        'runtime.lock: child[optional]>=1 requires leaf>=2; extra == "optional", locked leaf==1',
    ]
    lock.write_text("parent==1\nchild==1\nleaf==2\n", encoding="utf-8")
    assert validate_installed_closure(source, lock, distribution=packages.__getitem__) == [
        "runtime.lock: installed leaf==1, expected 2",
    ]
    packages["leaf"] = _distribution("2")
    assert validate_installed_closure(source, lock, distribution=packages.__getitem__) == []
