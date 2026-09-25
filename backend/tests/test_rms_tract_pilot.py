"""Synthetic parser/safety fixtures; not presented as real observations."""
import json

import pytest

from etl import pilot_cmhc_rms_tracts as pilot

from etl.pilot_cmhc_rms_tracts import count_cell, parse_universe, run_pilot

SAMPLE = (
    "Universe by Bedroom Type by Census Tract\nOctober 2025 Row / Apartment\n"
    ",Studio,1 Bedroom,2 Bedroom,3 Bedroom +,Total,\n"
    "0001.00,**,1,2,**,3,\n0002.00,0,0,0,0,0,\n,0,1,2,0,3,\n"
)


def test_preserves_flags_and_genuine_zero_without_inferring_suppressed_cells():
    result = parse_universe(SAMPLE, 2025)
    assert result["tracts"]["0001.00"]["Studio"] == {"raw": "**", "value": None, "status": "suppressed_or_unreliable"}
    assert result["tracts"]["0002.00"]["Total"]["value"] == 0
    assert result["totals_reconcile"] is True


@pytest.mark.parametrize("text", [SAMPLE.replace("2025", "2024"), SAMPLE.replace("Row / Apartment", "Apartment"), "<html>unavailable</html>", SAMPLE.replace("Total", "All"), "\nOctober 2025 Row / Apartment\n,Studio,1 Bedroom,2 Bedroom,3 Bedroom +,Total,\n"])
def test_rejects_wrong_period_universe_or_schema(text):
    with pytest.raises(ValueError):
        parse_universe(text, 2025)


def test_does_not_infer_a_missing_tract_total_from_bedrooms():
    result = parse_universe(SAMPLE.replace("0001.00,**,1,2,**,3", "0001.00,**,1,2,**,**"), 2025)
    assert result["tracts"]["0001.00"]["Total"]["value"] is None
    assert result["totals_reconcile"] is False


def test_duplicate_tract_is_rejected():
    with pytest.raises(ValueError, match="Duplicate tract"):
        parse_universe(SAMPLE.replace("0002.00", "0001.00"), 2025)


def test_unknown_flags_and_formula_like_counts_are_rejected():
    assert count_cell("343,539")["value"] == 343539
    for text in ("=1+1", "-1", "1.5", "unknown", "1,2", ",123"):
        with pytest.raises(ValueError):
            count_cell(text)


def test_output_cannot_target_application_data(tmp_path):
    with pytest.raises(ValueError, match="beneath the repository out"):
        run_pilot(2025, tmp_path / "not-allowed")


def test_duplicate_summary_is_rejected_even_if_first_total_is_suppressed():
    with pytest.raises(ValueError, match="Duplicate published summary"):
        parse_universe(SAMPLE.replace(",0,1,2,0,3,", ",0,1,2,0,**,\n,0,1,2,0,3,"), 2025)


def test_output_is_atomic_and_does_not_modify_application_data(tmp_path, monkeypatch):
    root = tmp_path / "backend"
    data = root / "app" / "data"
    data.mkdir(parents=True)
    seed = data / "demo_seed.json"
    original = json.dumps({"geographies": [{"geoid": "5350001.00", "type": "census_tract"}]})
    seed.write_text(original, encoding="utf-8")
    monkeypatch.setattr(pilot, "ROOT", root)
    monkeypatch.setattr(pilot, "CMAS", {"2270": "535", "2240": "532"})
    calls = []

    def failing_fetch(cma, year):
        calls.append(cma)
        if cma == "2240":
            raise ValueError("Rejected second response")
        return SAMPLE.encode("cp1252")

    monkeypatch.setattr(pilot, "fetch_universe", failing_fetch)
    output = tmp_path / "out" / "pilot"
    with pytest.raises(ValueError, match="Rejected second"):
        run_pilot(2025, output)
    assert calls == ["2270", "2240"]
    assert not output.exists()
    assert list(output.parent.iterdir()) == []
    assert seed.read_text(encoding="utf-8") == original

    monkeypatch.setattr(pilot, "fetch_universe", lambda cma, year: SAMPLE.encode("cp1252"))
    result = run_pilot(2025, output)
    assert result["matching_identifiers_with_total"] == 1
    assert result["boundary_compatibility"] == "not_verified"
    assert (output / "report.json").exists()
    assert seed.read_text(encoding="utf-8") == original
    with pytest.raises(ValueError, match="already exists"):
        run_pilot(2025, output)
