"""Regression coverage for the audited, non-destructive CMHC data migration."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models import CmhcMetric, Geography
import app.services.seed as seed_service

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "cmhc_correction_migration", ROOT / "alembic/versions/0012_correct_cmhc_bedroom_weights.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def add_geographies(connection):
    geoids = sorted({row["geoid"] for row in seed_service.load_cmhc_seed()["metrics"]})
    connection.execute(Geography.__table__.insert(), [
        {"geoid": geoid, "name": geoid, "type": "municipality", "state": "ON",
         "geometry": {}, "bbox": [], "geometry_source": migration.GEOMETRY_SOURCE}
        for geoid in geoids
    ])


def populate_cmhc(connection):
    add_geographies(connection)
    connection.execute(CmhcMetric.__table__.insert(), seed_service.load_cmhc_seed()["metrics"])


def restore_audited_old_values(connection):
    for record in migration.load_corrections()["corrections"]:
        assert record["field"] in migration.CORRECTED_FIELDS
        connection.execute(text(
            f"UPDATE cmhc_metrics SET {record['field']} = :before "
            "WHERE geoid = :geoid AND year = :year"
        ), record)


def rows_by_key(connection):
    return {(row["geoid"], row["year"]): dict(row) for row in connection.execute(
        select(CmhcMetric.__table__)
    ).mappings()}


@pytest.fixture
def empty_cmhc_db():
    engine = create_engine("sqlite://")
    Geography.__table__.create(engine)
    CmhcMetric.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def cmhc_db(empty_cmhc_db):
    populate_cmhc(empty_cmhc_db.connection())
    empty_cmhc_db.commit()
    return empty_cmhc_db


def test_correction_snapshot_and_seed_match_audited_hashes_and_scope():
    snapshot = migration.load_corrections()
    records = migration._validated_records(snapshot)
    data = ROOT / "app/data"
    raw_seed = (data / "cmhc_seed.json").read_bytes()
    assert b"\r\n" not in raw_seed
    assert len(records) == 90
    assert sum(row["after"] is None for row in records) == 8
    assert len(snapshot["source_files"]) == 40
    assert {row["file"] for row in snapshot["source_files"]} == {
        f"{year}/{bedroom}.csv" for year in range(2018, 2026)
        for bedroom in ("Total", "Studio", "1_Bedroom", "2_Bedroom", "3_Bedroom_plus")
    }
    assert all(len(row["sha256"]) == 64 for row in snapshot["source_files"])
    manifest = json.loads((data / "refresh_manifest.json").read_bytes())["sources"]["cmhc"]
    # Verify this reviewed release exactly, without freezing all future source
    # refreshes (which replace the source manifest entry and its release pointer).
    evidence = manifest.get("correction_snapshot")
    if evidence and evidence["file"] == migration.CORRECTION_FILE:
        assert evidence["sha256"] == migration.CORRECTION_SHA256
        assert hashlib.sha256(raw_seed).hexdigest() == snapshot["corrected_seed_sha256"]
        seed = {(row["geoid"], row["year"]): row for row in json.loads(raw_seed)["metrics"]}
        for row in records:
            assert seed[(row["geoid"], row["year"])][row["field"]] == row["after"]
    for name, artifact in manifest["artifacts"].items():
        assert hashlib.sha256((data / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == artifact["sha256"]


def assert_scoped_correction_round_trip(connection):
    """Run unchanged against SQLite and real Postgres; compare every stored cell."""
    restore_audited_old_values(connection)
    before = rows_by_key(connection)
    geographies = connection.execute(select(Geography.__table__)).all()
    result = migration.apply_cmhc_corrections(connection, migration.load_corrections())
    assert result == {"applied": 90, "already_corrected": 0, "missing": 0,
                      "skipped_context": 0, "skipped_conflict": 0}
    expected = deepcopy(before)
    for correction in migration.load_corrections()["corrections"]:
        expected[(correction["geoid"], correction["year"])][correction["field"]] = correction["after"]
    assert rows_by_key(connection) == expected
    assert connection.execute(select(Geography.__table__)).all() == geographies
    repeated = migration.apply_cmhc_corrections(connection, migration.load_corrections())
    assert repeated["applied"] == 0 and repeated["already_corrected"] == 90
    assert rows_by_key(connection) == expected


def test_migration_updates_only_audited_cells_and_is_idempotent(cmhc_db):
    assert_scoped_correction_round_trip(cmhc_db.connection())


def test_compare_and_swap_preserves_change_between_read_and_update(cmhc_db):
    connection = cmhc_db.connection()
    restore_audited_old_values(connection)
    target = migration.load_corrections()["corrections"][0]

    class RacingConnection:
        changed = False

        def execute(self, statement, params=None):
            if str(statement).startswith("UPDATE cmhc_metrics") and not self.changed:
                self.changed = True
                connection.execute(text(
                    f"UPDATE cmhc_metrics SET {target['field']} = 654321 "
                    "WHERE geoid = :geoid AND year = :year"
                ), target)
            return connection.execute(statement, params)

    result = migration.apply_cmhc_corrections(RacingConnection(), migration.load_corrections())
    assert result["applied"] == 89 and result["skipped_conflict"] == 1
    assert rows_by_key(connection)[(target["geoid"], target["year"])][target["field"]] == 654321


def assert_custom_values_preserved(connection):
    restore_audited_old_values(connection)
    connection.execute(text(
        "UPDATE geographies SET geometry_source = 'Custom boundary' WHERE geoid = '3521005'"
    ))
    connection.execute(text("UPDATE geographies SET type = 'custom_area' WHERE geoid = '3521010'"))
    connection.execute(text(
        "UPDATE cmhc_metrics SET average_rent_1br = 99999, average_rent_bachelor = NULL, "
        "vacancy_rate = 88, housing_starts_total = 765432 WHERE geoid = '3520005' AND year = 2025"
    ))
    connection.execute(CmhcMetric.__table__.insert().values(
        geoid="3520005", year=2026, average_rent_1br=54321, rms_surveyed=True,
    ))
    # A geography outside the audited set is never inserted, deleted or changed.
    connection.execute(Geography.__table__.insert().values(
        geoid="custom", name="Custom", type="municipality", state="ON", geometry={},
        bbox=[], geometry_source=migration.GEOMETRY_SOURCE,
    ))
    connection.execute(CmhcMetric.__table__.insert().values(
        geoid="custom", year=2025, average_rent_1br=23456, rms_surveyed=True,
    ))
    before = rows_by_key(connection)
    geo_before = connection.execute(select(Geography.__table__)).all()
    expected = deepcopy(before)
    eligible = [row for row in migration.load_corrections()["corrections"]
                if row["geoid"] == "3520005" and not (
                    row["year"] == 2025 and row["field"] in ("average_rent_1br", "average_rent_bachelor")
                )]
    for correction in eligible:
        expected[(correction["geoid"], correction["year"])][correction["field"]] = correction["after"]
    result = migration.apply_cmhc_corrections(connection, migration.load_corrections())
    assert result["applied"] == len(eligible)
    assert result["skipped_conflict"] == 2
    assert result["skipped_context"] == 90 - len(eligible) - 2
    assert rows_by_key(connection) == expected
    assert connection.execute(select(Geography.__table__)).all() == geo_before


def test_custom_newer_unknown_and_null_values_are_preserved(cmhc_db, caplog):
    assert_custom_values_preserved(cmhc_db.connection())
    assert "skipped_conflict: geoid=3520005 year=2025" in caplog.text
    assert "retained existing data" in caplog.text


def test_missing_existing_row_is_preserved_without_inserting(cmhc_db):
    connection = cmhc_db.connection()
    connection.execute(text("DELETE FROM cmhc_metrics WHERE geoid = '3520005' AND year = 2018"))
    before = rows_by_key(connection)
    result = migration.apply_cmhc_corrections(connection, migration.load_corrections())
    assert result["missing"] == sum(
        row["geoid"] == "3520005" and row["year"] == 2018
        for row in migration.load_corrections()["corrections"]
    )
    assert rows_by_key(connection) == before


def test_empty_database_migration_and_first_production_seed_are_safe(empty_cmhc_db, monkeypatch):
    connection = empty_cmhc_db.connection()
    assert migration.apply_cmhc_corrections(connection, migration.load_corrections())["missing"] == 90
    assert rows_by_key(connection) == {}
    add_geographies(connection)
    monkeypatch.setattr(seed_service, "settings", SimpleNamespace(app_env="production"))
    assert seed_service.seed_cmhc_data(empty_cmhc_db) == 200
    assert seed_service.seed_cmhc_data(empty_cmhc_db) == 0


def test_snapshot_tampering_fails_before_updating(cmhc_db, monkeypatch, tmp_path):
    path = tmp_path / "tampered.json"
    snapshot = migration.load_corrections()
    snapshot["corrections"][0]["after"] += 1
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(migration, "CORRECTION_FILE", str(path))
    monkeypatch.setattr(migration.op, "get_bind", lambda: cmhc_db.connection())
    before = rows_by_key(cmhc_db.connection())
    with pytest.raises(ValueError, match="audited hash"):
        migration.upgrade()
    assert rows_by_key(cmhc_db.connection()) == before


@pytest.mark.parametrize("fault", ["duplicate", "field", "geoid", "year", "before", "after", "count"])
def test_invalid_snapshot_is_rejected_before_any_write(cmhc_db, fault):
    connection = cmhc_db.connection()
    restore_audited_old_values(connection)
    before = rows_by_key(connection)
    snapshot = migration.load_corrections()
    last = snapshot["corrections"][-1]
    if fault == "duplicate":
        snapshot["corrections"][-1] = snapshot["corrections"][0]
    elif fault == "count":
        snapshot["corrections"].pop()
    else:
        last[fault] = {"field": "housing_completions", "geoid": "custom", "year": 2026,
                       "before": None, "after": -5}[fault]
    with pytest.raises(ValueError):
        migration.apply_cmhc_corrections(connection, snapshot)
    assert rows_by_key(connection) == before


def test_downgrade_never_restores_incorrect_values(cmhc_db, monkeypatch):
    monkeypatch.setattr(migration.op, "get_bind", lambda: pytest.fail("Downgrade must not write"))
    before = rows_by_key(cmhc_db.connection())
    migration.downgrade()
    assert rows_by_key(cmhc_db.connection()) == before


def test_migration_then_production_startup_does_not_reseed(cmhc_db, monkeypatch):
    connection = cmhc_db.connection()
    restore_audited_old_values(connection)
    migration.apply_cmhc_corrections(connection, migration.load_corrections())
    cmhc_db.commit()
    before = rows_by_key(cmhc_db.connection())
    monkeypatch.setattr(seed_service, "settings", SimpleNamespace(app_env="production"))
    assert seed_service.seed_cmhc_data(cmhc_db) == 0
    assert rows_by_key(cmhc_db.connection()) == before


@pytest.mark.parametrize("drift", ["value", "null", "new_year", "missing_row"])
def test_production_drift_fails_closed_without_deleting_data(cmhc_db, monkeypatch, drift):
    connection = cmhc_db.connection()
    if drift == "new_year":
        connection.execute(CmhcMetric.__table__.insert().values(
            geoid="3520005", year=2026, average_rent_1br=54321, rms_surveyed=True,
        ))
    elif drift == "missing_row":
        connection.execute(text("DELETE FROM cmhc_metrics WHERE geoid = '3520005' AND year = 2025"))
    else:
        connection.execute(text(
            "UPDATE cmhc_metrics SET average_rent_1br = :value WHERE geoid = '3520005' AND year = 2025"
        ), {"value": None if drift == "null" else 54321})
    cmhc_db.commit()
    before = rows_by_key(cmhc_db.connection())
    monkeypatch.setattr(seed_service, "settings", SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="automatic destructive reseeding is disabled"):
        seed_service.seed_cmhc_data(cmhc_db)
    assert rows_by_key(cmhc_db.connection()) == before


def test_explicit_force_contract_is_preserved(cmhc_db, monkeypatch):
    cmhc_db.connection().execute(text(
        "UPDATE cmhc_metrics SET average_rent_1br = 54321 WHERE geoid = '3520005' AND year = 2025"
    ))
    cmhc_db.commit()
    monkeypatch.setattr(seed_service, "settings", SimpleNamespace(app_env="production"))
    assert seed_service.seed_cmhc_data(cmhc_db, force=True) == 200
    assert rows_by_key(cmhc_db.connection())[("3520005", 2025)]["average_rent_1br"] == 1761
