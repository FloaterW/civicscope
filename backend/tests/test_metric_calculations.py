from app.services.metric_calculations import (
    calculate_affordability_index,
    calculate_population_growth_pct,
    calculate_rent_to_income_ratio,
    estimate_rent_burden_pct,
)


def test_rent_to_income_ratio_annualizes_rent():
    assert calculate_rent_to_income_ratio(1500, 60000) == 0.3


def test_affordability_index_is_100_at_burden_threshold():
    assert calculate_affordability_index(1500, 60000) == 100.0


def test_estimated_rent_burden_is_bounded():
    assert estimate_rent_burden_pct(4000, 30000) == 65
    assert estimate_rent_burden_pct(500, 120000) == 12


def test_population_growth_pct():
    assert calculate_population_growth_pct(1100, 1000) == 10.0
