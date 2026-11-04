from pathlib import Path

import pytest

from scripts.check_dependency_locks import validate_lock


def test_committed_locks_satisfy_inputs_and_runtime_constraints():
    backend = Path(__file__).resolve().parents[1]
    for name in ("requirements", "requirements-dev"):
        assert validate_lock(backend / f"{name}.in", backend / f"{name}.lock") == []


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
