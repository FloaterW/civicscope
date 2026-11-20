import io
import json
import ssl
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

import pytest

from etl import http_retry, load_census, load_tract_census


def error(status, retry_after=None):
    return HTTPError("https://example.test/?token=secret", status, "sensitive upstream text",
                     {"Retry-After": retry_after} if retry_after else {}, None)


@pytest.mark.parametrize("failure", [error(429, "3"), error(503), TimeoutError(), URLError("temporary DNS error")])
def test_transient_fetch_recovers_and_records_sanitized_attempts(monkeypatch, tmp_path, failure):
    evidence = tmp_path / "events.jsonl"
    monkeypatch.setenv("REFRESH_DIAGNOSTICS_FILE", str(evidence))
    sleep = Mock()
    monkeypatch.setattr(http_retry.time, "sleep", sleep)
    opener = Mock(side_effect=[failure, io.BytesIO(b"valid")])
    assert http_retry.read_with_retry("https://example.test/?token=secret", opener=opener, label="census-tracts") == b"valid"
    assert opener.call_count == 2
    assert sleep.call_count == 1
    events = [json.loads(line) for line in evidence.read_text().splitlines()]
    assert [event["outcome"] for event in events] == ["retry", "success"]
    assert "secret" not in evidence.read_text()
    assert "sensitive" not in evidence.read_text()
    assert "https" not in evidence.read_text()


@pytest.mark.parametrize("failure", [error(400), error(401), error(404), error(501), error(429, "120"),
                                     URLError(ssl.SSLCertVerificationError("bad certificate"))])
def test_permanent_or_over_budget_failures_do_not_retry(monkeypatch, failure):
    sleep = Mock()
    monkeypatch.setattr(http_retry.time, "sleep", sleep)
    opener = Mock(side_effect=failure)
    with pytest.raises(type(failure)):
        http_retry.read_with_retry("https://example.test", opener=opener, label="census-tracts")
    assert opener.call_count == 1
    sleep.assert_not_called()


def test_http_date_retry_after_and_invalid_hint():
    now = datetime(2026, 11, 20, tzinfo=UTC)
    assert http_retry.retry_delay(error(503, format_datetime(now + timedelta(seconds=12))), 1, now=now) == 12
    assert http_retry.retry_delay(error(503, "invalid"), 2, now=now) == 2
    assert http_retry.retry_delay(error(503, "0"), 1, now=now) == 1


def test_exhausted_batch_stops_before_later_batches(monkeypatch):
    opener = Mock(side_effect=error(503))
    monkeypatch.setattr(load_tract_census, "urlopen", opener)
    monkeypatch.setattr(http_retry.time, "sleep", Mock())
    with pytest.raises(HTTPError):
        load_tract_census.fetch_all_tract_metrics([f"535{i:04d}.00" for i in range(45)])
    assert opener.call_count == 3


def test_invalid_response_schema_is_not_retried(monkeypatch):
    opener = Mock(return_value=io.BytesIO(b"REF_AREA,CHARACTERISTIC,OBS_VALUE\n"))
    monkeypatch.setattr(load_tract_census, "urlopen", opener)
    with pytest.raises(ValueError, match="omitted FLAG"):
        load_tract_census.fetch_batch(["2021S05075350001_00"])
    assert opener.call_count == 1


def test_municipal_fetch_uses_same_transient_retry_policy(monkeypatch):
    opener = Mock(side_effect=[error(503), io.BytesIO(b"csv")])
    monkeypatch.setattr(load_census, "urlopen", opener)
    monkeypatch.setattr(http_retry.time, "sleep", Mock())
    assert load_census.fetch_profile_csv("https://example.test") == "csv"
    assert opener.call_count == 2
