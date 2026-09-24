import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import CmhcMetric, Geography, Metric
from app.services.seed import load_demo_seed
import app.services.seed as seed_service

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("census_migration", ROOT / "alembic/versions/0011_add_tenure_renter.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def correction_snapshot():
    raw = (ROOT / "app/data/census_corrections_20260924.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == migration.CORRECTION_SHA256
    return json.loads(raw)


def test_census_source_artifacts_match_reviewed_hashes_and_csv_has_portable_newlines():
    manifest = json.loads((ROOT / "app/data/census_source_manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        assert hashlib.sha256((ROOT / "app/data" / name).read_bytes()).hexdigest() == expected
    assert b"\r\n" not in (ROOT / "app/data/statcan_ct_metrics.csv").read_bytes()
    assert manifest["municipalities"] == 25 and manifest["tracts"] == 1334
    assert manifest["coverage"]["partial"] is False
    assert len(correction_snapshot()["geographies"]) == 1359


def test_existing_row_correction_is_scoped_repeatable_and_preserves_related_data(db_session):
    original_ids = dict(db_session.execute(select(Geography.geoid, Geography.id)).all())
    cmhc_before = db_session.execute(select(CmhcMetric.__table__)).all()
    toronto = db_session.query(Metric).filter_by(geoid="3520005", year=2021).one()
    toronto.owner_households = 807670
    toronto.tenure_renter_households = None
    toronto.transit_score = 12.3
    toronto.transit_route_count = 8
    other_year = Metric(geoid="3520005", year=2026, owner_households=123)
    db_session.add(other_year)
    wrong_source = db_session.query(Geography).filter_by(geoid="3521005").one()
    wrong_source.geometry_source = "User supplied custom boundary"
    untouched = db_session.query(Metric).filter_by(geoid=wrong_source.geoid, year=2021).one()
    untouched.owner_households = 456
    wrong_level = db_session.query(Geography).filter_by(geoid="5350403.16").one()
    wrong_level.type = "custom_area"
    level_metric = db_session.query(Metric).filter_by(geoid=wrong_level.geoid, year=2021).one()
    level_metric.owner_households = 789
    db_session.flush()
    connection = db_session.connection()
    for _ in range(2):
        migration.apply_census_corrections(connection, correction_snapshot())
    db_session.expire_all()
    assert toronto.owner_households == 602925
    assert toronto.tenure_renter_households == 557970
    assert toronto.renter_households == 557975
    assert toronto.transit_score == 12.3 and toronto.transit_route_count == 8
    assert other_year.owner_households == 123
    assert untouched.owner_households == 456
    assert level_metric.owner_households == 789
    assert dict(db_session.execute(select(Geography.geoid, Geography.id)).all()) == original_ids
    assert db_session.execute(select(CmhcMetric.__table__)).all() == cmhc_before


def test_production_seed_drift_fails_closed_without_deleting_data(db_session, monkeypatch):
    toronto = db_session.query(Metric).filter_by(geoid="3520005", year=2021).one()
    toronto.owner_households = 807670
    db_session.commit()
    geo_ids = dict(db_session.execute(select(Geography.geoid, Geography.id)).all())
    cmhc_before = db_session.execute(select(CmhcMetric.__table__)).all()
    monkeypatch.setattr(seed_service, "settings", SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="automatic destructive reseeding is disabled"):
        seed_service.seed_demo_data(db_session)
    assert toronto.owner_households == 807670
    assert dict(db_session.execute(select(Geography.geoid, Geography.id)).all()) == geo_ids
    assert db_session.execute(select(CmhcMetric.__table__)).all() == cmhc_before


def test_tenure_map_detail_compare_parity_and_genuine_zero_provenance(client):
    mapped = client.get("/api/map-data?type=municipality&metric=population").json()
    toronto = next(row["properties"]["metrics"] for row in mapped["features"] if row["properties"]["geoid"] == "3520005")
    detail = client.get("/api/geographies/3520005").json()["metrics"]
    compare = client.get("/api/compare?ids=3520005").json()["items"][0]["metrics"]
    for field, expected in {"owner_households": 602925, "tenure_renter_households": 557970, "renter_households": 557975}.items():
        assert toronto[field] == detail[field] == compare[field] == expected
    zero = client.get("/api/geographies/5320105.17").json()["metrics"]
    assert zero["rent_burden_pct"] == 0
    assert zero["data_quality"]["rent_burden_pct"] == "official"


def test_seed_and_frozen_migration_agree_for_all_correction_fields():
    current = {row["geoid"]: row for row in load_demo_seed()["geographies"]}
    for row in correction_snapshot()["geographies"]:
        for field in migration.CORRECTED_FIELDS:
            assert current[row["geoid"]]["metrics"][0][field] == row["metrics"][0][field]
