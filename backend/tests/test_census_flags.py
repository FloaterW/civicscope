import io

import pytest

from etl.census_flags import observation_value
from etl import load_census, load_tract_census


@pytest.mark.parametrize("flag", ["1", "2", "3", "4", "6", "7", "O", "x", "unexpected"])
def test_flagged_placeholder_zero_is_not_published(flag):
    assert observation_value({"OBS_VALUE": "0", "FLAG": flag}) is None


@pytest.mark.parametrize("flag", ["", "5", "r"])
def test_genuine_zero_survives(flag):
    assert observation_value({"OBS_VALUE": "0", "FLAG": flag}) == "0"


def test_owner_is_not_condominium_status():
    assert load_census.OFFICIAL_CHARACTERISTIC_IDS["owner_households"] == "1401"
    assert load_tract_census.CHARACTERISTIC_IDS["owner_households"] == "1401"
    assert "1406" not in load_census.CHARACTERISTIC_TO_FIELD
    assert "detail=full" in load_census.build_profile_url(["3520005"])


def test_csd_parser_preserves_suppression():
    rows = load_census.parse_profile_csv_text(
        "REF_AREA,CHARACTERISTIC,OBS_VALUE,FLAG\n2021A00053520005,1478,0,6\n2021A00053520005,1401,500,\n",
        require_flags=True,
    )
    assert rows[0].rent_burden_pct is None
    assert rows[0].owner_households == 500
    with pytest.raises(ValueError, match="omitted FLAG"):
        load_census.parse_profile_csv_text("REF_AREA,CHARACTERISTIC,OBS_VALUE\n", require_flags=True)


def test_tract_requests_flags_and_preserves_suppression(monkeypatch):
    def response(request, timeout):
        assert "detail=full" in request.full_url
        return io.BytesIO(b"REF_AREA,CHARACTERISTIC,OBS_VALUE,FLAG\n2021S05075320001_00,1478,0,6\n2021S05075320001_00,1401,500,\n")
    monkeypatch.setattr(load_tract_census, "urlopen", response)
    rows = load_tract_census.fetch_batch(["2021S05075320001_00"])
    assert rows[0].rent_burden_pct is None
    assert rows[0].owner_households == 500
