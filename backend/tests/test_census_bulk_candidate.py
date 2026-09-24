import pytest

from etl.census_bulk_candidate import BULK_CHARACTERISTICS, parse_bulk_rows
from etl.load_census import OFFICIAL_CHARACTERISTIC_IDS


def fixture_rows():
    rows = [["CENSUS_YEAR", "DGUID", "CHARACTERISTIC_ID", "CHARACTERISTIC_NAME", "C1_COUNT_TOTAL", "SYMBOL", "C2_COUNT_MEN+", "SYMBOL"]]
    for field, (code, label) in BULK_CHARACTERISTICS.items():
        value = {"owner_households": "602925", "tenure_renter_households": "557970", "renter_households": "557975"}.get(field, "0")
        rows.append(["2021", "2021A00053520005", code, label, value, "", "", "..."])
    return rows


def test_bulk_ids_are_distinct_and_only_total_symbol_controls_value():
    assert set(BULK_CHARACTERISTICS) == set(OFFICIAL_CHARACTERISTIC_IDS)
    assert BULK_CHARACTERISTICS["median_income"][0] != OFFICIAL_CHARACTERISTIC_IDS["median_income"]
    result = parse_bulk_rows(iter(fixture_rows()), {"2021A00053520005": "3520005"})[0]
    assert result.owner_households == 602925
    assert result.tenure_renter_households == 557970
    assert result.renter_households == 557975
    assert result.rent_burden_pct == 0  # later gender SYMBOL must not hide a valid total


@pytest.mark.parametrize("symbol", ["x", "...", "F", "E", "unknown"])
def test_bulk_suppressed_values_remain_null(symbol):
    rows = fixture_rows()
    next(row for row in rows[1:] if row[2] == "1492")[5] = symbol
    result = parse_bulk_rows(iter(rows), {"2021A00053520005": "3520005"})[0]
    assert result.rent_burden_pct is None


def test_bulk_missing_observations_do_not_publish_as_suppressed():
    rows = fixture_rows()[:-1]
    with pytest.raises(ValueError, match="omitted"):
        parse_bulk_rows(iter(rows), {"2021A00053520005": "3520005"})


def test_bulk_rejects_wrong_label_and_duplicate_observations():
    rows = fixture_rows()
    rows[-1][3] = "Not condominium"
    with pytest.raises(ValueError, match="label changed"):
        parse_bulk_rows(iter(rows), {"2021A00053520005": "3520005"})
    rows = fixture_rows()
    rows.append(rows[-1].copy())
    with pytest.raises(ValueError, match="Duplicate"):
        parse_bulk_rows(iter(rows), {"2021A00053520005": "3520005"})
