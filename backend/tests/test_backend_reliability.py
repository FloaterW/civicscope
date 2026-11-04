"""Regression tests for deployment, identifier and optional-source failures."""

import importlib
from dataclasses import replace
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
from unittest.mock import MagicMock

from alembic import context
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import config as app_config
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import Geography, Metric


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENCODED_URL = "postgresql+psycopg://fixture:p%40ss%25word@localhost:5432/fixture"


def test_migration_helper_preserves_encoded_credentials(monkeypatch):
    module = importlib.import_module("app.db.init_db")
    monkeypatch.setattr(module, "settings", replace(app_config.settings, database_url=ENCODED_URL))
    config = module.alembic_config()
    assert config.get_main_option("sqlalchemy.url") == ENCODED_URL
    assert config.get_section(config.config_ini_section)["sqlalchemy.url"] == ENCODED_URL


def test_alembic_env_preserves_encoded_credentials_offline(monkeypatch):
    monkeypatch.setattr(app_config, "settings", replace(app_config.settings, database_url=ENCODED_URL))
    config = Config()
    configure = MagicMock()
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", MagicMock())
    monkeypatch.setattr(context, "run_migrations", MagicMock())
    runpy.run_path(str(BACKEND_ROOT / "alembic/env.py"))
    assert config.get_main_option("sqlalchemy.url") == ENCODED_URL
    assert configure.call_args.kwargs["url"] == ENCODED_URL


@pytest.mark.parametrize("forwarded", ["*", "127.0.0.1,10.0.0.1", None])
def test_container_startup_passes_proxy_setting_as_one_argument(tmp_path, forwarded):
    shell = shutil.which("sh")
    if shell is None:
        git_shell = Path("C:/Program Files/Git/bin/bash.exe")
        shell = str(git_shell) if git_shell.exists() else None
    if shell is None:
        pytest.skip("POSIX shell needed to verify Docker argument expansion")
    command_line = next(
        line.removeprefix("CMD ")
        for line in (BACKEND_ROOT / "Dockerfile").read_text().splitlines()
        if line.startswith("CMD ")
    )
    entrypoint = json.loads(command_line)
    assert entrypoint[:2] == ["sh", "-c"]
    prefix = "alembic upgrade head && exec uvicorn "
    assert entrypoint[2].startswith(prefix)
    # Print exactly the arguments the shell would pass, without starting a DB
    # migration or server. These files expose accidental wildcard expansion.
    (tmp_path / "app").mkdir()
    (tmp_path / "alembic.ini").touch()
    env = {**os.environ, "PORT": "9011"}
    if forwarded is None:
        env.pop("FORWARDED_ALLOW_IPS", None)
    else:
        env["FORWARDED_ALLOW_IPS"] = forwarded
    command = "printf '%s\\n' " + entrypoint[2][len(prefix):]
    result = subprocess.run(
        [shell, "-c", command], cwd=tmp_path, env=env,
        text=True, capture_output=True, check=True, timeout=10,
    )
    assert result.stdout.splitlines() == [
        "app.main:app", "--host", "0.0.0.0", "--port", "9011",
        "--proxy-headers", "--forwarded-allow-ips", forwarded or "127.0.0.1",
    ]


@pytest.fixture()
def census_only_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        geometry = {"type": "Polygon", "coordinates": [[
            [-79.5, 43.6], [-79.4, 43.6], [-79.4, 43.7], [-79.5, 43.6],
        ]]}
        for index, (geoid, kind, name, county) in enumerate([
            ("3520005", "municipality", "Toronto", None),
            ("5350001.00", "census_tract", "Toronto tract", "Toronto"),
        ], 1):
            db.add(Geography(
                id=index, geoid=geoid, name=name, type=kind, county=county,
                geometry=geometry, bbox=[-79.5, 43.6, -79.4, 43.7],
            ))
            db.add(Metric(
                geoid=geoid, year=2021, population=1000, previous_population=900,
                median_income=50000, median_rent=1000, renter_households=100,
                rent_burden_pct=30, transit_score=20, transit_route_count=2,
            ))
        db.commit()
        app = create_app(auto_initialize=False)
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client
    engine.dispose()


@pytest.mark.parametrize("identifier", ["²", "١", "１２", "9" * 5000, "2147483648", "-1", "0"])
def test_malformed_geography_ids_return_not_found(census_only_client, identifier):
    response = census_only_client.get(f"/api/geographies/{identifier}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Geography not found."}


@pytest.mark.parametrize("identifier,geoid", [("3520005", "3520005"), ("1", "3520005"), ("5350001.00", "5350001.00")])
def test_geoid_and_legacy_numeric_lookup_remain_supported(census_only_client, identifier, geoid):
    response = census_only_client.get(f"/api/geographies/{identifier}")
    assert response.status_code == 200
    assert response.json()["geoid"] == geoid


@pytest.mark.parametrize("kind", ["municipality", "census_tract"])
@pytest.mark.parametrize("metric", ["population", "transit_score"])
def test_census_and_transit_map_do_not_require_cmhc(census_only_client, kind, metric):
    response = census_only_client.get(f"/api/map-data?type={kind}&metric={metric}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["year"] == 2021
    assert payload["metadata"]["cmhc_year"] is None
    assert payload["metadata"]["available_years"] == []
    assert len(payload["features"]) == 1
    assert payload["features"][0]["properties"]["value"] is not None
    assert payload["features"][0]["properties"].get("cmhc_metrics") is None


@pytest.mark.parametrize("kind", ["municipality", "census_tract"])
def test_summary_and_comparison_allow_missing_supplemental_cmhc(census_only_client, kind):
    summary = census_only_client.get(f"/api/summary?type={kind}")
    assert summary.status_code == 200
    assert summary.json()["population"] == 1000
    assert summary.json()["average_rent_total"] is None
    comparison = census_only_client.get(f"/api/compare?type={kind}")
    assert comparison.status_code == 200
    assert len(comparison.json()["items"]) == 1
    assert comparison.json()["items"][0]["cmhc_metrics"] is None


def test_cmhc_map_still_requires_a_source_when_year_is_implicit(census_only_client):
    response = census_only_client.get("/api/map-data?metric=average_rent_total")
    assert response.status_code == 404
    assert response.json()["detail"] == "No CMHC metrics have been loaded."


def test_explicit_unavailable_cmhc_year_is_not_silently_substituted(census_only_client):
    response = census_only_client.get("/api/map-data?metric=average_rent_total&year=2024")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["year"] == 2024
    assert payload["metadata"]["domain"] == {"min": None, "max": None}
    assert all(feature["properties"]["value"] is None for feature in payload["features"])
