"""Tests for the real CMHC census-tract SCSS loader.

These run against a committed fixture of REAL CMHC rows
(tests/fixtures/cmhc_ct_starts_sample.csv) — never synthetic data dressed up as
real. Network is not touched here.
"""
from pathlib import Path

from etl.load_cmhc_tracts import (
    CMA_PREFIX,
    METRICS,
    parse_ct_table,
    parse_published_total,
    resolve_cma_slice,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cmhc_ct_starts_sample.csv"


def test_parses_real_ct_rows_including_comma_formatted_values():
    parsed = parse_ct_table(FIXTURE.read_text(encoding="latin1"))
    # 0017.01 is published as "2,304" (comma thousands separator).
    assert parsed["0017.01"] == 2304
    assert parsed["0005.00"] == 410
    assert parsed["0007.02"] == 298


def test_zero_is_kept_as_a_real_value_not_dropped():
    parsed = parse_ct_table(FIXTURE.read_text(encoding="latin1"))
    # A tract with no construction is a real 0, distinct from "not covered".
    assert parsed["0001.00"] == 0
    assert parsed["0002.00"] == 0


def test_only_census_tract_rows_are_parsed():
    parsed = parse_ct_table(FIXTURE.read_text(encoding="latin1"))
    # Title / header / notes lines must not leak in as data keys.
    for key in parsed:
        assert key[0].isdigit() and "." in key


def test_published_total_sums_named_rows():
    # A minimal published-table CSV (CMHC province/centres format).
    csv_text = (
        " \x97 Starts by Dwelling Type by Provinces\r\n"
        "2023 Intended Markets - All\r\n"
        ",Single,Semi-Detached,Row,Apartment,All,\r\n"
        'Ontario,"4,721",328,"4,860","37,519","47,428",\r\n'
        ',"4,721",328,"4,860","37,519","47,428",\r\n'
        "Source,CMHC Starts and Completions Survey\r\n"
    )
    assert parse_published_total(csv_text) == 47428


def test_published_total_returns_none_for_unparseable_stub():
    # An HTML/error stub (no header row) must yield None — NOT 0 — so the
    # validation gate can refuse it instead of silently passing.
    assert parse_published_total("<!DOCTYPE html><html>error</html>") is None
    assert parse_published_total("") is None


def test_published_total_distinguishes_genuine_zero_from_parse_failure():
    # A real table whose named rows sum to 0 returns 0 (validatable), not None.
    csv_text = (
        ",Single,Semi-Detached,Row,Apartment,All,\r\n"
        "Ontario,0,0,0,0,0,\r\n"
        "Source,CMHC\r\n"
    )
    assert parse_published_total(csv_text) == 0


def test_resolve_exact_match_is_official():
    # CMHC publishes our exact 2021 tract -> real official value.
    cmhc = {"0001.00": 410, "0002.00": 0}
    out = resolve_cma_slice(cmhc, ["5320001.00"], "532", renter={})
    assert out["5320001.00"] == (410, "official")


def test_resolve_zero_parent_yields_official_zero_for_every_child():
    # Parent tract recorded 0 -> every 2021 child is a genuine, official 0.
    cmhc = {"0002.00": 0}  # our 0002.01/.02/.03 are not in CMHC (post-split)
    children = ["5320002.01", "5320002.02", "5320002.03"]
    out = resolve_cma_slice(cmhc, children, "532", renter={})
    for c in children:
        assert out[c] == (0, "official")


def test_resolve_nonzero_parent_allocates_by_renter_share_conserving_total():
    # Parent recorded 18; split between two children by renter share (455 vs 450),
    # labelled estimated_parent, and the children MUST sum back to 18 exactly.
    cmhc = {"0003.00": 18}
    children = ["5320003.01", "5320003.02"]
    renter = {"5320003.01": 455, "5320003.02": 450}
    out = resolve_cma_slice(cmhc, children, "532", renter)
    assert {s for (s) in (out[c][1] for c in children)} == {"estimated_parent"}
    assert sum(out[c][0] for c in children) == 18  # conserved
    # Larger renter share gets at least as much.
    assert out["5320003.01"][0] >= out["5320003.02"][0]


def test_resolve_nonzero_parent_equal_split_when_no_renter_data():
    cmhc = {"0008.00": 7}
    children = [f"5320008.0{i}" for i in (1, 2, 3)]
    out = resolve_cma_slice(cmhc, children, "532", renter={})
    assert sum(out[c][0] for c in children) == 7  # conserved even with equal split
    assert {out[c][1] for c in children} == {"estimated_parent"}


def test_resolve_omits_tracts_with_no_cmhc_match():
    # No exact and no parent -> omitted (API keeps municipal estimate).
    cmhc = {"0001.00": 5}
    out = resolve_cma_slice(cmhc, ["5320999.00"], "532", renter={})
    assert "5320999.00" not in out


def test_metric_and_cma_config_is_complete():
    # Both shipped metrics have a CT table code and a validation-total code.
    assert set(METRICS) == {"housing_starts_total", "housing_completions"}
    for ct_code, total_code in METRICS.values():
        assert ct_code.endswith(".11")  # census-tract breakdown suffix
        assert total_code.endswith(".3")  # province/centres total
    # All three GTA CMAs with their CTUID prefixes.
    assert CMA_PREFIX == {"2270": "535", "2240": "532", "2320": "537"}
