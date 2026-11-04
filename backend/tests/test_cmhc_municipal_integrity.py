"""Municipal CMHC aggregation contracts; all source responses are synthetic."""
from dataclasses import replace

import pytest

from etl import load_cmhc as cmhc


def monthly_year():
    return [cmhc.ScssMonthlyRow(2025, month, month) for month in range(1, 13)]


def zones_for(geoid):
    return [
        cmhc.ZoneData(name, average_rent=2000, vacancy_rate=2, rental_universe=100)
        for name, geoids in cmhc.ZONE_TO_GEOIDS.items()
        if geoid in geoids
    ]


def test_annual_completions_include_all_months_and_ignore_other_years():
    rows = monthly_year() + [cmhc.ScssMonthlyRow(2024, 1, 999)]
    assert cmhc._sum_completions_for_year(rows, 2025) == 78
    assert cmhc._sum_completions_for_year([replace(row, total=0) for row in rows], 2025) == 0


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "duplicate_replaces_missing", "suppressed", "negative", "bad_month", "fractional"])
def test_invalid_annual_completions_remain_missing_and_fail_actual_coverage_gate(invalid):
    rows = monthly_year()
    if invalid == "missing":
        rows.pop()
    elif invalid == "duplicate":
        rows.append(rows[0])
    elif invalid == "duplicate_replaces_missing":
        rows[-1] = rows[0]
    elif invalid == "suppressed":
        rows[0].total = None
    elif invalid == "negative":
        rows[0].total = -1
    elif invalid == "fractional":
        rows[0].total = 1.5
    else:
        rows[0].month = 13
    total = cmhc._sum_completions_for_year(rows, 2025)
    assert total is None
    metric = cmhc.CmhcRow("3520005", 2025, average_rent_total=2000,
                          housing_starts_total=10, housing_completions=total)
    with pytest.raises(ValueError, match="housing_completions coverage"):
        cmhc.validate_seed_coverage([metric], {"3520005"}, [2025])


@pytest.mark.parametrize("geoid", sorted(cmhc.AGGREGATED_GEOIDS))
def test_every_constituent_zone_is_required_for_multi_zone_municipalities(geoid):
    zones = zones_for(geoid)
    with pytest.raises(ValueError, match="Incomplete or duplicate RMS zones"):
        cmhc.aggregate_zones_to_municipalities(zones[:-1], 2025)
    complete = cmhc.aggregate_zones_to_municipalities(zones, 2025)
    assert complete[0].rental_universe == 100 * len(zones)


@pytest.mark.parametrize("geoid", ["3520005", "3519036", "3519038"])
def test_duplicate_zone_is_rejected_for_aggregated_single_and_shared_zones(geoid):
    zones = zones_for(geoid)
    with pytest.raises(ValueError, match="duplicates="):
        cmhc.aggregate_zones_to_municipalities(zones + [zones[0]], 2025)


def test_renamed_zone_does_not_silently_change_municipal_coverage():
    zones = zones_for("3520005")
    zones[-1].zone_name = "New source definition needs review"
    with pytest.raises(ValueError, match="Review the source geography definitions"):
        cmhc.aggregate_zones_to_municipalities(zones, 2025)


def test_present_suppressed_zone_rows_are_not_missing_geographies():
    zones = [cmhc.ZoneData(zone.zone_name) for zone in zones_for("3521010")]
    row = cmhc.aggregate_zones_to_municipalities(zones, 2025)[0]
    assert row.rental_universe is None
    assert row.average_rent_1br is None


def test_published_zero_stock_survives_aggregation_and_actual_coverage_gate():
    zones = [cmhc.ZoneData(zone.zone_name, rental_universe=0) for zone in zones_for("3521010")]
    row = cmhc.aggregate_zones_to_municipalities(zones, 2025)[0]
    assert row.rental_universe == 0
    row.housing_starts_total = row.housing_completions = 0
    assert cmhc.validate_seed_coverage([row], {"3521010"}, [2025])["partial"] is False


def test_unknown_constituent_stock_does_not_become_partial_municipal_stock():
    zones = zones_for("3521010")
    zones[0].rental_universe = None
    assert cmhc.aggregate_zones_to_municipalities(zones, 2025)[0].rental_universe is None


def test_bedroom_rents_use_bedroom_stock_instead_of_all_bedroom_stock():
    zones = zones_for("3521010")
    zones[0].average_rent_1br, zones[0].rental_universe_1br = 1000, 90
    zones[1].average_rent_1br, zones[1].rental_universe_1br = 3000, 10
    row = cmhc.aggregate_zones_to_municipalities(zones, 2025)[0]
    assert row.average_rent_1br == 1200
    assert row.average_rent_total == 2000
    assert row.rental_universe == 200


@pytest.mark.parametrize("units,rent,expected", [(None, 3000, None), (10, None, None), (-1, 3000, None), (0, None, 1000)])
def test_bedroom_aggregation_does_not_impute_missing_weights_or_suppressed_rents(units, rent, expected):
    zones = zones_for("3521010")
    zones[0].average_rent_1br, zones[0].rental_universe_1br = 1000, 90
    zones[1].average_rent_1br, zones[1].rental_universe_1br = rent, units
    assert cmhc.aggregate_zones_to_municipalities(zones, 2025)[0].average_rent_1br == expected


def test_bedroom_fetch_preserves_matching_units_through_merge_and_aggregation(monkeypatch):
    def response(_year, bedroom):
        assert bedroom in cmhc.BEDROOM_TYPES
        return ("Brampton (West),2,a,3,a,1000,a,900,a,1,a,90,\n"
                "Brampton (East),2,a,3,a,3000,a,2900,a,1,a,10,\n")
    monkeypatch.setattr(cmhc, "fetch_rms_bedroom_csv", response)
    monkeypatch.setattr(cmhc.time, "sleep", lambda _: None)
    bedroom_data = cmhc.fetch_bedroom_rents_for_year(2025)
    zones = zones_for("3521010")
    cmhc.merge_bedroom_rents(zones, bedroom_data)
    row = cmhc.aggregate_zones_to_municipalities(zones, 2025)[0]
    for field in cmhc.BEDROOM_TYPES.values():
        assert getattr(row, field) == 1200
    assert bedroom_data["Brampton (West)"]["rental_universe_1br"] == 90


def test_duplicate_bedroom_source_zones_are_not_overwritten(monkeypatch):
    row = "Brampton (West),2,a,3,a,1000,a,900,a,1,a,90,\n"
    monkeypatch.setattr(cmhc, "fetch_rms_bedroom_csv", lambda *_: row + row)
    with pytest.raises(ValueError, match="Duplicate RMS zones"):
        cmhc.fetch_bedroom_rents_for_year(2025)


@pytest.mark.parametrize("zones", [zones_for("3520005")[:1], zones_for("3520005") + zones_for("3520005")[:1]])
def test_update_seed_never_writes_partial_or_duplicate_zone_aggregate(tmp_path, monkeypatch, zones):
    output = tmp_path / "candidate.json"
    output.write_text("existing candidate", encoding="utf-8")
    monkeypatch.setattr(cmhc, "load_geoids_from_seed", lambda: ["3520005"])
    monkeypatch.setattr(cmhc, "fetch_rms_summary_csv", lambda _: "synthetic")
    monkeypatch.setattr(cmhc, "parse_rms_summary_csv", lambda _: zones)
    monkeypatch.setattr(cmhc, "fetch_bedroom_rents_for_year", lambda _: {})
    with pytest.raises(ValueError, match="Incomplete or duplicate RMS zones"):
        cmhc.update_seed([2025], output_path=output)
    assert output.read_text(encoding="utf-8") == "existing candidate"


def test_update_seed_rejects_entirely_missing_surveyed_municipality(tmp_path, monkeypatch):
    output = tmp_path / "candidate.json"
    monkeypatch.setattr(cmhc, "load_geoids_from_seed", lambda: ["3519036"])
    monkeypatch.setattr(cmhc, "fetch_rms_summary_csv", lambda _: "")
    monkeypatch.setattr(cmhc, "fetch_scss_all_municipalities", lambda _: {
        "3519036": {2025: {"housing_starts_total": 10, "housing_completions": 20}}
    })
    with pytest.raises(ValueError, match="surveyed rows missing RMS values"):
        cmhc.update_seed([2025], output_path=output)
    assert not output.exists()


def test_seed_json_has_portable_lf_bytes_before_provenance_hashing(tmp_path):
    output = tmp_path / "cmhc.json"
    cmhc.write_seed([cmhc.CmhcRow("3520005", 2025)], [2025], output_path=output)
    assert b"\r\n" not in output.read_bytes()
    assert output.read_bytes().endswith(b"\n")
