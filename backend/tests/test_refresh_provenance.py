import json
from datetime import UTC, datetime

import pytest

from app.services.refresh_provenance import packaged_digest, verified_sources
from etl.record_source_check import record_check
from etl.refresh_candidate import digest


@pytest.fixture
def evidence(tmp_path):
    published, candidate = tmp_path / "published", tmp_path / "candidate"
    for folder in (published, candidate):
        folder.mkdir()
        (folder / "cmhc_seed.json").write_text(json.dumps({"metadata": {"source": "cmhc", "years": [2025]}, "metrics": [{"geoid": "city", "year": 2025, "rent": 1000}]}))
        (folder / "cmhc_ct_metrics.csv").write_text("geoid,year,value\ntract,2025,0\n")
    manifest = {"sources": {"cmhc": {"last_checked_at": datetime.now(UTC).isoformat(), "artifacts": {name: {"sha256": digest(candidate / name)} for name in ("cmhc_seed.json", "cmhc_ct_metrics.csv")}}}}
    (candidate / "refresh_manifest.json").write_text(json.dumps(manifest))
    return published, candidate


def test_record_preserves_other_sources_and_does_not_write(evidence):
    published, candidate = evidence
    original = '{"sources":{"census":{"last_checked_at":null}}}'
    (published / "refresh_manifest.json").write_text(original)
    manifest = record_check("cmhc", published, candidate)
    assert "census" in manifest["sources"]
    assert (published / "refresh_manifest.json").read_text() == original
    (published / "refresh_manifest.json").write_text(json.dumps(manifest))
    assert set(verified_sources(published)) == {"cmhc"}


def test_candidate_hash_mismatch_rejected(evidence):
    published, candidate = evidence
    (candidate / "cmhc_ct_metrics.csv").write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        record_check("cmhc", published, candidate)


@pytest.mark.parametrize("replacement", ["geoid,year,value\ntract,2025,1\n", "geoid,year,value\ntract,2025,\n", "geoid,year,value\n"])
def test_changed_missing_or_suppressed_values_rejected(evidence, replacement):
    published, candidate = evidence
    (published / "cmhc_ct_metrics.csv").write_text(replacement)
    with pytest.raises(ValueError, match="changes published data"):
        record_check("cmhc", published, candidate)


@pytest.mark.parametrize("fault", ["missing", "malformed", "list", "no_hash", "changed"])
def test_unverified_packaged_data_stays_unknown(evidence, fault):
    published, candidate = evidence
    manifest = record_check("cmhc", published, candidate)
    if fault == "list":
        manifest = []
    elif fault == "no_hash":
        del manifest["sources"]["cmhc"]["artifacts"]
    elif fault == "changed":
        (published / "cmhc_ct_metrics.csv").write_text("changed")
    if fault != "missing":
        (published / "refresh_manifest.json").write_text("invalid json" if fault == "malformed" else json.dumps(manifest))
    assert verified_sources(published) == {}


def test_packaged_cmhc_evidence_matches_actual_files():
    from importlib.resources import files
    assert "cmhc" in verified_sources(files("app.data"))


def test_hash_is_portable_across_checkout_line_endings(tmp_path):
    left, right = tmp_path / "lf", tmp_path / "crlf"
    left.write_bytes(b"a,b\n1,0\n")
    right.write_bytes(b"a,b\r\n1,0\r\n")
    assert packaged_digest(left) == packaged_digest(right)


def test_equivalent_metadata_does_not_hide_changed_values(evidence):
    published, candidate = evidence
    path = published / "cmhc_seed.json"
    value = json.loads(path.read_text())
    value["metadata"]["fetched_at"] = "old"
    path.write_text(json.dumps(value))
    assert record_check("cmhc", published, candidate)
    value["metrics"][0]["rent"] = 999
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="changes published data"):
        record_check("cmhc", published, candidate)
