"""Offline safety contracts for reviewed refreshes and source freshness."""
import json
import importlib.util
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services import data_status
from etl import refresh_candidate as refresh
from etl import transit_routes


def put_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def artifact_dirs(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    seed = {"geographies": [{"geoid": "city", "type": "municipality"}, {"geoid": "tract", "type": "census_tract"}]}
    for directory in (before, after):
        directory.mkdir()
        put_json(directory / "demo_seed.json", seed)
        (directory / "statcan_ct_metrics.csv").write_text("geoid,year\ntract,2021\n")
        (directory / "transit_scores.csv").write_text("geoid,transit_score\ntract,42\n")
        put_json(directory / "transit_routes.geojson", {"type": "FeatureCollection", "features": [{"properties": {"agency_id": "ttc"}}]})
        put_json(directory / "transit_manifest.json", {
            "coverage_status": "complete", "included_agencies": [{"id": "ttc"}],
            "artifacts": {name: {"sha256": refresh.digest(directory / name)} for name in ("transit_scores.csv", "transit_routes.geojson")},
        })
    return before, after


def test_complete_transit_candidate_passes(artifact_dirs):
    refresh.validate_candidate("transit", *artifact_dirs)


def test_cmhc_supported_cells_exclude_unpublished_years_and_keep_zero(tmp_path):
    path = tmp_path / "tracts.csv"
    path.write_text("geoid,year,housing_starts_total,housing_completions\n5350001.00,2022,1,0\n5350001.00,2023,2,\n")
    assert refresh.cmhc_tract_cells(path) == {
        ("5350001.00", 2022, "housing_starts_total"),
        ("5350001.00", 2022, "housing_completions"),
        ("5350001.00", 2023, "housing_starts_total"),
    }


def test_cmhc_candidate_cannot_drop_an_existing_tract_value(artifact_dirs):
    before, after = artifact_dirs
    for directory in (before, after):
        put_json(directory / "cmhc_seed.json", {"metadata": {"years": [2022, 2023]}})
        (directory / "cmhc_ct_metrics.csv").write_text("geoid,year,housing_starts_total,housing_completions\ntract,2022,1,0\ntract,2023,2,\n")
    refresh.validate_candidate("cmhc", before, after)
    (after / "cmhc_ct_metrics.csv").write_text("geoid,year,housing_starts_total,housing_completions\ntract,2022,1,0\ntract,2023,,\n")
    with pytest.raises(ValueError, match="removed 1 supported CMHC tract cells"):
        refresh.validate_candidate("cmhc", before, after)


@pytest.mark.parametrize("fault", ["partial", "agency", "missing_tract", "duplicate_tract", "hash", "geographies", "missing_artifact"])
def test_rejects_invalid_transit_candidate(artifact_dirs, fault):
    before, after = artifact_dirs
    manifest = json.loads((after / "transit_manifest.json").read_text())
    if fault == "partial":
        manifest["coverage_status"] = "partial"
    elif fault == "agency":
        manifest["included_agencies"].append({"id": "miway"})
    elif fault == "missing_tract":
        (after / "transit_scores.csv").write_text("geoid,transit_score\n")
    elif fault == "duplicate_tract":
        (after / "transit_scores.csv").write_text("geoid,transit_score\ntract,42\ntract,42\n")
    elif fault == "hash":
        manifest["artifacts"]["transit_routes.geojson"]["sha256"] = "incorrect"
    elif fault == "geographies":
        put_json(after / "demo_seed.json", {"geographies": []})
    else:
        (after / "transit_routes.geojson").unlink()
    put_json(after / "transit_manifest.json", manifest)
    with pytest.raises(ValueError):
        refresh.validate_candidate("transit", before, after)


@pytest.fixture
def isolated_root(tmp_path, artifact_dirs, monkeypatch):
    import shutil
    root = tmp_path / "root"
    shutil.copytree(artifact_dirs[0], root / "app" / "data")
    (root / "etl").mkdir()
    (root / "alembic").mkdir()
    (root / "alembic.ini").write_text("[alembic]\n")
    monkeypatch.setattr(refresh, "ROOT", root)
    return root


def test_existing_destination_is_untouched(isolated_root, tmp_path, monkeypatch):
    output = tmp_path / "candidate"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("existing")
    run = MagicMock()
    monkeypatch.setattr(refresh.subprocess, "run", run)
    with pytest.raises(ValueError, match="existing"):
        refresh.refresh("census", output)
    assert sentinel.read_text() == "existing"
    run.assert_not_called()


def test_failed_etl_never_changes_canonical_data_or_creates_output(isolated_root, tmp_path, monkeypatch):
    canonical = isolated_root / "app/data/demo_seed.json"
    original = canonical.read_bytes()
    def fail(*args, **kwargs):
        (kwargs["cwd"] / "app/data/demo_seed.json").write_text("broken candidate")
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(refresh.subprocess, "run", fail)
    output = tmp_path / "candidate"
    with pytest.raises(subprocess.CalledProcessError):
        refresh.refresh("census", output)
    assert canonical.read_bytes() == original
    assert not output.exists()


def test_validation_failure_never_creates_output(isolated_root, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh.subprocess, "run", MagicMock())
    def reject(*args):
        raise ValueError("invalid artifact")
    monkeypatch.setattr(refresh, "validate_candidate", reject)
    output = tmp_path / "candidate"
    with pytest.raises(ValueError, match="invalid artifact"):
        refresh.refresh("census", output)
    assert not output.exists()


@pytest.mark.parametrize("url", ["", "postgresql://user:127.0.0.1@remote.example/db", "postgresql://remote.example/127.0.0.1", "postgresql://127.0.0.1.evil.example/db"])
def test_transit_rejects_nonlocal_database_before_running_etl(isolated_root, tmp_path, monkeypatch, url):
    monkeypatch.setenv("REFRESH_POSTGIS_URL", url)
    run = MagicMock()
    monkeypatch.setattr(refresh.subprocess, "run", run)
    with pytest.raises(ValueError, match="local"):
        refresh.refresh("transit", tmp_path / "candidate")
    run.assert_not_called()


def test_publish_copy_failure_does_not_leave_partial_candidate(isolated_root, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh.subprocess, "run", MagicMock())
    output = tmp_path / "candidate"
    original_copy = refresh.shutil.copy2
    def fail_publish(source, destination, *args, **kwargs):
        if str(destination).endswith("statcan_ct_metrics.csv"):
            raise OSError("disk full")
        return original_copy(source, destination, *args, **kwargs)
    monkeypatch.setattr(refresh.shutil, "copy2", fail_publish)
    with pytest.raises(OSError, match="disk full"):
        refresh.refresh("census", output)
    assert not output.exists()


def gtfs(path, *, missing=None, longitude="-79.4", points=2):
    contents = {
        "routes.txt": "route_id,route_type,route_short_name\nr1,3,10\n",
        "trips.txt": "route_id,shape_id\nr1,s1\nr1,s1\nr1,unused\n",
        "shapes.txt": "shape_id,shape_pt_lon,shape_pt_lat,shape_pt_sequence\n" + "".join(f"s1,{longitude},43.7,{i}\n" for i in range(points)),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in contents.items():
            if name != missing:
                archive.writestr("nested/" + name, content)


@pytest.mark.parametrize("missing", ["routes.txt", "trips.txt", "shapes.txt"])
def test_gtfs_requires_shape_inputs(tmp_path, missing):
    path = tmp_path / "ttc.zip"
    gtfs(path, missing=missing)
    with pytest.raises(ValueError, match="missing"):
        transit_routes.route_features("ttc", path)


@pytest.mark.parametrize("longitude", ["nan", "inf", "181", "-181"])
def test_gtfs_rejects_invalid_coordinates(tmp_path, longitude):
    path = tmp_path / "ttc.zip"
    gtfs(path, longitude=longitude)
    with pytest.raises(ValueError, match="invalid route coordinates"):
        transit_routes.route_features("ttc", path)


def test_gtfs_rejects_incomplete_shape(tmp_path):
    path = tmp_path / "ttc.zip"
    gtfs(path, points=1)
    with pytest.raises(ValueError, match="incomplete shape"):
        transit_routes.route_features("ttc", path)


def test_routes_use_exact_selected_cached_agencies(tmp_path, monkeypatch):
    monkeypatch.setattr(transit_routes, "GTFS_CACHE_DIR", tmp_path)
    for agency in ("ttc", "miway"):
        gtfs(tmp_path / f"{agency}.zip")
    output = tmp_path / "routes.geojson"
    assert transit_routes.write_routes(["ttc", "miway"], output) == 2
    features = json.loads(output.read_text())["features"]
    assert {f["properties"]["agency_id"] for f in features} == {"ttc", "miway"}
    assert all(len(f["geometry"]["coordinates"]) == 2 for f in features)


@pytest.mark.parametrize("checked,expected", [(None, "unknown"), (123, "unknown"), (["date"], "unknown"), ({"date": "2026-01-01"}, "unknown"), ("bad-date", "unknown"), ("2026-01-01", "unknown"), ("future", "unknown"), ("recent", "checked"), ("old", "overdue")])
def test_freshness_uses_verified_checks_not_observation_year(tmp_path, monkeypatch, checked, expected):
    if checked in ("future", "recent", "old"):
        days = {"future": 2, "recent": -1, "old": -200}[checked]
        checked = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    put_json(tmp_path / "refresh_manifest.json", {"sources": {name: {"last_checked_at": checked} for name in ("census", "cmhc", "transit")}})
    monkeypatch.setattr(data_status, "files", lambda package: tmp_path)
    monkeypatch.setattr(data_status, "load_transit_manifest", lambda: {"packaged_at": "2026-09-01", "coverage_status": "complete"})
    db = MagicMock()
    db.query.return_value.scalar.side_effect = [2021, 2025]
    db.query.return_value.filter.return_value.scalar.return_value = None
    db.query.return_value.count.return_value = 1359
    result = data_status.build_data_status(db)
    assert [s["observation_year"] for s in result["sources"]] == [2021, 2025, None]
    assert all(s["check_status"] == expected for s in result["sources"])
    assert result["last_database_load_at"] is None
    if expected == "unknown":
        assert all(s["last_checked_at"] is None for s in result["sources"])


@pytest.fixture
def monitor():
    spec = importlib.util.spec_from_file_location("civicscope_monitor_test", Path(__file__).resolve().parents[2] / "scripts/monitor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_recovers_cold_start_without_masking_retry(monitor, monkeypatch):
    responses = iter([TimeoutError("sleeping"), (b'{"status":"ok"}', 0.2), (b'CivicScope', 0.1), (b'{"population":100}', 0.1), (b'{"geography_count":1359}', 0.1)])
    def read(url):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(monitor, "read", read)
    monkeypatch.setattr(monitor.time, "sleep", MagicMock())
    results = monitor.check("https://api.example", "https://frontend.example")
    assert len(results) == 4
    assert results[0]["retried"] is True
    assert not any("error" in result for result in results)


def test_monitor_reports_persistent_invalid_content_and_continues(monitor, monkeypatch):
    def read(url):
        if url.endswith("/health"):
            return b'{"status":"degraded"}', 0.1
        if "summary" in url:
            return b'{"population":100}', 0.1
        if "data-status" in url:
            return b'{"geography_count":1359}', 0.1
        return b'CivicScope', 0.1
    monkeypatch.setattr(monitor, "read", read)
    monkeypatch.setattr(monitor.time, "sleep", MagicMock())
    results = monitor.check("https://api.example", "https://frontend.example")
    assert results[0] == {"check": "api_health", "error": "ValueError"}
    assert len(results) == 4
    assert all("error" not in result for result in results[1:])
