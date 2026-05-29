"""Field-level provenance logic for census metrics.

These tests pin down how the API distinguishes official Statistics Canada
values from estimated fallbacks, suppressed/missing values, and low-confidence
derived values (e.g. population growth off a tiny base).
"""
from types import SimpleNamespace

from app.services.metric_calculations import (
    build_metric_quality,
    estimate_rent_burden_pct,
    is_low_denominator_growth,
    resolve_rent_burden,
)
from app.services.summary import build_summary


def _row(**overrides):
    base = {
        "median_income": 60000.0,
        "median_rent": 1500.0,
        "population": 3000,
        "previous_population": 2800,
        "renter_households": 800,
        "rent_burden_pct": 35.0,
        "affordability_index": 90.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --- resolve_rent_burden ---------------------------------------------------

def test_resolve_rent_burden_official_when_value_present():
    assert resolve_rent_burden(1500.0, 60000.0, 35.0) == (35.0, "official")


def test_resolve_rent_burden_estimated_when_official_missing_but_inputs_present():
    value, status = resolve_rent_burden(1500.0, 60000.0, None)
    assert status == "estimated"
    assert value == estimate_rent_burden_pct(1500.0, 60000.0)
    assert value is not None


def test_resolve_rent_burden_unavailable_when_cannot_estimate():
    assert resolve_rent_burden(None, 60000.0, None) == (None, "unavailable")
    assert resolve_rent_burden(1500.0, None, None) == (None, "unavailable")


# --- is_low_denominator_growth ---------------------------------------------

def test_low_denominator_growth_flags_small_base():
    assert is_low_denominator_growth(50) is True
    assert is_low_denominator_growth(5) is True


def test_low_denominator_growth_ignores_normal_and_missing_base():
    assert is_low_denominator_growth(100) is False
    assert is_low_denominator_growth(2800) is False
    assert is_low_denominator_growth(0) is False
    assert is_low_denominator_growth(None) is False


# --- build_metric_quality --------------------------------------------------

def test_metric_quality_all_official_for_complete_row():
    quality = build_metric_quality(_row())
    assert quality["median_income"] == "official"
    assert quality["median_rent"] == "official"
    assert quality["population"] == "official"
    assert quality["rent_burden_pct"] == "official"
    assert quality["population_growth_pct"] == "official"


def test_metric_quality_marks_missing_value_unavailable():
    quality = build_metric_quality(_row(median_rent=None))
    assert quality["median_rent"] == "unavailable"


def test_metric_quality_marks_estimated_rent_burden():
    quality = build_metric_quality(_row(rent_burden_pct=None))
    assert quality["rent_burden_pct"] == "estimated"


def test_metric_quality_marks_unavailable_rent_burden_when_not_estimable():
    quality = build_metric_quality(_row(rent_burden_pct=None, median_rent=None))
    assert quality["rent_burden_pct"] == "unavailable"


def test_metric_quality_flags_low_denominator_growth():
    quality = build_metric_quality(_row(population=1484, previous_population=5))
    assert quality["population_growth_pct"] == "low_confidence"


def test_metric_quality_growth_unavailable_when_no_previous_population():
    quality = build_metric_quality(_row(previous_population=None))
    assert quality["population_growth_pct"] == "unavailable"


# --- summary stays consistent with the map (effective rent burden) ----------

def _summary_record(geoid, **overrides):
    metric = _row(**overrides)
    geography = SimpleNamespace(geoid=geoid, name=geoid, type="census_tract", county="Toronto")
    return (geography, metric)


def test_summary_rent_burden_includes_estimated_tracts_like_the_map():
    # Tract A: official rent burden. Tract B: official suppressed (null) but
    # estimable from rent + income. The map colours both (B via a labelled
    # estimate), so the summary's weighted average must include B too — not
    # silently drop it, which would make the summary disagree with the map.
    records = [
        _summary_record("A", rent_burden_pct=30.0, renter_households=100,
                        median_rent=1500.0, median_income=60000.0),
        _summary_record("B", rent_burden_pct=None, renter_households=100,
                        median_rent=2000.0, median_income=50000.0),
    ]
    estimated_b, status = resolve_rent_burden(2000.0, 50000.0, None)
    assert status == "estimated"
    expected = round((30.0 * 100 + estimated_b * 100) / 200, 2)

    summary = build_summary(records, 2021)
    assert summary["rent_burden_pct"] == expected
