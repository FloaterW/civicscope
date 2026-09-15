"""Deterministic response/transport diagnostics; never fetch live data."""
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from etl.load_cmhc_tracts import _fetch, fetch_validated_slice, validate_generation_coverage


def test_archived_series_reports_slice_not_unpublished():
    with patch("etl.load_cmhc_tracts._fetch", return_value="2024\r\nThis data series is now archived.\r\n"):
        with pytest.raises(ValueError, match=r"archived series .*housing_completions, CMA=2270, year=2024"):
            fetch_validated_slice("housing_completions", "2270", 2024)


def test_html_response_is_not_treated_as_missing_data():
    with patch("etl.load_cmhc_tracts._fetch", return_value="<!DOCTYPE html><html>Unavailable</html>"):
        with pytest.raises(ValueError, match="HTML instead of CSV"):
            fetch_validated_slice("housing_starts_total", "2270", 2024)


def test_transient_http_failure_retries_then_returns_response():
    error = HTTPError("https://example.test", 503, "Unavailable", None, None)
    with patch("etl.load_cmhc_tracts.urlopen", side_effect=[error, BytesIO(b"csv")]) as fetch, patch("etl.load_cmhc_tracts.time.sleep"):
        assert _fetch("1.1.1.11", "2270", 2024) == "csv"
        assert fetch.call_count == 2


@pytest.mark.parametrize("status, attempts", [(403, 1), (503, 3)])
def test_retry_is_bounded_and_never_bypasses_access_errors(status, attempts):
    error = HTTPError("https://example.test", status, "failure", None, None)
    with patch("etl.load_cmhc_tracts.urlopen", side_effect=error) as fetch, patch("etl.load_cmhc_tracts.time.sleep"):
        with pytest.raises(HTTPError):
            _fetch("1.1.1.11", "2270", 2024)
        assert fetch.call_count == attempts


def test_coverage_error_identifies_missing_slice():
    with pytest.raises(ValueError, match="housing_completions/CMA 2270/2024"):
        validate_generation_coverage({"a"}, {"a"}, [("housing_completions", "2270", 2024)], 42)


def test_generation_requests_only_explicit_supported_metric_years(tmp_path):
    from etl.load_cmhc_tracts import generate_csv
    years = {"housing_starts_total": [2022, 2023], "housing_completions": [2022]}
    with patch("etl.load_cmhc_tracts.CMA_PREFIX", {"2270": "535"}), patch("etl.load_cmhc_tracts._load_seed_tracts", return_value=({"5350001.00"}, {})), patch("etl.load_cmhc_tracts.fetch_validated_slice", return_value={"0001.00": 0}) as fetch:
        report = generate_csv([2022, 2023], tmp_path / "output.csv", metric_years=years)
    assert report["expected_slices"] == report["validated_slices"] == 3
    assert [call.args for call in fetch.call_args_list] == [
        ("housing_starts_total", "2270", 2022),
        ("housing_starts_total", "2270", 2023),
        ("housing_completions", "2270", 2022),
    ]


def test_missing_supported_slice_still_blocks_generation(tmp_path):
    from etl.load_cmhc_tracts import generate_csv
    output = tmp_path / "output.csv"
    with patch("etl.load_cmhc_tracts.CMA_PREFIX", {"2270": "535"}), patch("etl.load_cmhc_tracts._load_seed_tracts", return_value=({"5350001.00"}, {})), patch("etl.load_cmhc_tracts.fetch_validated_slice", side_effect=[{"0001.00": 0}, None]):
        with pytest.raises(ValueError, match="missing metric slices"):
            generate_csv([2022], output, metric_years={"housing_starts_total": [2022], "housing_completions": [2022]})
    assert not output.exists()
