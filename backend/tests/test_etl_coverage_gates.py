"""Tests for fail-closed coverage gates in ETL loaders."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from etl.load_tract_census import (
    MIN_COVERAGE_PCT,
    TractMetric,
    fetch_all_tract_metrics,
    validate_tract_coverage,
    write_csv,
)
from etl.load_cmhc import SEED_PATH as CMHC_SEED_PATH
from etl.load_cmhc import write_seed as write_cmhc_seed
from etl.load_cmhc import CmhcRow, validate_seed_coverage
from etl.load_cmhc_tracts import validate_generation_coverage
from etl.load_transit import (
    DEFAULT_CACHE_MAX_AGE_HOURS,
    GTFS_FEEDS,
    MIN_AGENCIES,
    download_feed,
    merge_stop_routes,
    parse_gtfs_stop_routes,
)


# --- load_tract_census coverage gate ---


def _make_metric(geoid: str) -> TractMetric:
    return TractMetric(
        geoid=geoid,
        year=2021,
        population=1000,
        previous_population=900,
        median_income=50000.0,
        median_rent=1200.0,
        renter_households=300,
        rent_burden_pct=35.0,
    )


def test_tract_census_write_csv_produces_output(tmp_path: Path):
    metrics = [_make_metric("5350001.00"), _make_metric("5350002.00")]
    out = tmp_path / "out.csv"
    write_csv(metrics, out)
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3  # header + 2 rows


def test_tract_census_fetch_batch_returns_empty_on_http_error():
    with patch("etl.load_tract_census.urlopen") as mock_urlopen:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="http://test", code=500, msg="error", hdrs=None, fp=None
        )
        from etl.load_tract_census import fetch_batch

        result = fetch_batch(["2021S05075350001_00"])
        assert result == []


def test_tract_census_coverage_gate_blocks_low_coverage():
    """Simulate main() refusing to write when coverage < MIN_COVERAGE_PCT."""
    geoids = [f"535000{i}.00" for i in range(10)]
    # Only 1/10 tracts returned => 10% coverage, well below 80%
    metrics = [_make_metric(geoids[0])]
    coverage_pct = len(metrics) / len(geoids) * 100
    assert coverage_pct < MIN_COVERAGE_PCT


def test_tract_census_coverage_gate_passes_full_coverage():
    geoids = [f"535000{i}.00" for i in range(5)]
    metrics = [_make_metric(g) for g in geoids]
    coverage_pct = len(metrics) / len(geoids) * 100
    assert coverage_pct >= MIN_COVERAGE_PCT


def test_tract_census_field_gate_rejects_complete_rows_with_missing_values():
    geoids = [f"535000{i}.00" for i in range(100)]
    metrics = [replace(_make_metric(geoid), median_rent=None) for geoid in geoids]

    with pytest.raises(ValueError, match="median_rent coverage"):
        validate_tract_coverage(metrics, geoids)


def test_tract_census_field_gate_allows_expected_suppression_rate():
    geoids = [f"535000{i}.00" for i in range(100)]
    metrics = [_make_metric(geoid) for geoid in geoids]
    metrics[0] = replace(metrics[0], median_rent=None)
    metrics[1] = replace(metrics[1], median_rent=None)

    report = validate_tract_coverage(metrics, geoids)

    assert report["partial"] is False
    assert report["field_coverage_pct"]["median_rent"] == 98.0


def test_tract_census_gate_rejects_unexpected_identifiers():
    geoids = ["5350001.00", "5350002.00"]
    metrics = [_make_metric("5350001.00"), _make_metric("9999999.99")]

    with pytest.raises(ValueError, match="unexpected tract identifiers"):
        validate_tract_coverage(metrics, geoids)


# --- CMHC municipality and tract coverage gates ---


def test_cmhc_seed_gate_rejects_missing_scss_fields():
    rows = [CmhcRow(geoid="test", year=2024)]

    with pytest.raises(ValueError, match="missing both starts and completions"):
        validate_seed_coverage(rows, {"test"}, [2024])


def test_cmhc_seed_gate_accepts_complete_unsurveyed_row():
    rows = [
        CmhcRow(
            geoid="test",
            year=2024,
            housing_starts_total=1,
            housing_completions=2,
        )
    ]

    report = validate_seed_coverage(rows, {"test"}, [2024])

    assert report["partial"] is False
    assert report["actual_rows"] == 1


def test_cmhc_seed_writer_supports_noncanonical_diagnostic_output(tmp_path: Path):
    output = tmp_path / "cmhc-diagnostic.json"
    rows = [
        CmhcRow(
            geoid="test",
            year=2024,
            housing_starts_total=1,
            housing_completions=2,
        )
    ]

    assert output != CMHC_SEED_PATH
    assert write_cmhc_seed(rows, [2024], {"partial": True}, output) == 1
    assert output.exists()


def test_cmhc_tract_gate_rejects_missing_slices():
    with pytest.raises(ValueError, match="missing metric slices"):
        validate_generation_coverage(
            {"a", "b"}, {"a", "b"}, [("starts", "2270", 2024)], 6
        )


def test_cmhc_tract_gate_requires_minimum_coverage():
    with pytest.raises(ValueError, match="tract coverage"):
        validate_generation_coverage(set("abcdefghij"), {"a"}, [], 6)


# --- load_transit coverage gate ---


def test_transit_download_feed_reports_failure(tmp_path: Path):
    with patch("etl.load_transit.GTFS_CACHE_DIR", tmp_path):
        with patch("etl.load_transit.urlopen", side_effect=OSError("network error")):
            _, ok = download_feed("test_agency", "http://fake")
            assert ok is False


def test_transit_download_feed_reports_success(tmp_path: Path):
    import io

    with patch("etl.load_transit.GTFS_CACHE_DIR", tmp_path):
        mock_resp = io.BytesIO(b"PK\x03\x04fake zip data")
        mock_resp.read = lambda: b"PK\x03\x04fake zip data"
        with patch("etl.load_transit.urlopen", return_value=mock_resp):
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = lambda s, *a: None
            _, ok = download_feed("test_agency", "http://fake")
            assert ok is True


def test_transit_min_agencies_gate():
    """Verify the MIN_AGENCIES constant is enforced."""
    assert MIN_AGENCIES == len(GTFS_FEEDS)
    agencies_with_data = ["ttc", "miway"]
    assert len(agencies_with_data) < MIN_AGENCIES


def test_transit_stale_cache_is_refreshed(tmp_path: Path):
    import io
    cached = tmp_path / "test_agency.zip"
    cached.write_bytes(b"old")
    import os
    import time

    stale = time.time() - ((DEFAULT_CACHE_MAX_AGE_HOURS + 1) * 3600)
    os.utime(cached, (stale, stale))
    with patch("etl.load_transit.GTFS_CACHE_DIR", tmp_path):
        mock_response = io.BytesIO(b"new")
        with patch("etl.load_transit.urlopen", return_value=mock_response):
            mock_response.__enter__ = lambda value: value
            mock_response.__exit__ = lambda value, *args: None
            path, ok = download_feed("test_agency", "http://fake")

    assert ok is True
    assert path.read_bytes() == b"new"


def test_transit_parse_empty_zip_returns_empty():
    result = parse_gtfs_stop_routes(Path("/nonexistent/file.zip"))
    assert result == {}


def test_transit_merge_preserves_routes():
    feed_a = {(43.65, -79.38): {"ttc:501", "ttc:504"}}
    feed_b = {(43.65, -79.38): {"go:01"}, (43.73, -79.76): {"brampton:2"}}
    merged = merge_stop_routes({"a": feed_a, "b": feed_b})
    assert merged[(43.65, -79.38)] == {"ttc:501", "ttc:504", "go:01"}
    assert merged[(43.73, -79.76)] == {"brampton:2"}
