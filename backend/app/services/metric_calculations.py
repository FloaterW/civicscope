from __future__ import annotations

from typing import Any

CMHC_METRICS = {
    "vacancy_rate",
    "average_rent_total",
    "average_rent_bachelor",
    "average_rent_1br",
    "average_rent_2br",
    "average_rent_3br_plus",
    "turnover_rate",
    "availability_rate",
    "rental_universe",
    "housing_starts_total",
    "housing_starts_single",
    "housing_starts_semi",
    "housing_starts_row",
    "housing_starts_apartment",
    "housing_completions",
    "units_under_construction",
}

VALID_METRICS = {
    "median_income",
    "median_rent",
    "rent_burden_pct",
    "population",
    "population_growth_pct",
    "affordability_index",
    "rent_to_income_ratio",
} | CMHC_METRICS

METRIC_ALIASES = {
    "income": "median_income",
    "rent": "median_rent",
    "rent_burden": "rent_burden_pct",
    "growth": "population_growth_pct",
    "population_growth": "population_growth_pct",
    "affordability": "affordability_index",
    "ratio": "rent_to_income_ratio",
    # CMHC aliases
    "vacancy": "vacancy_rate",
    "starts": "housing_starts_total",
    "completions": "housing_completions",
    "rent_cmhc": "average_rent_total",
    "turnover": "turnover_rate",
    "availability": "availability_rate",
    "universe": "rental_universe",
}


def normalize_metric_name(metric: str) -> str:
    key = metric.strip().lower()
    return METRIC_ALIASES.get(key, key)


def is_cmhc_metric(metric: str) -> bool:
    return normalize_metric_name(metric) in CMHC_METRICS


def calculate_rent_to_income_ratio(
    median_rent: float | None,
    median_income: float | None,
) -> float | None:
    if median_rent is None or median_income is None or median_income <= 0:
        return None
    # Annualized rent divided by annual household income. 0.30 is the common burden threshold.
    return round((median_rent * 12) / median_income, 4)


def calculate_affordability_index(
    median_rent: float | None,
    median_income: float | None,
) -> float | None:
    ratio = calculate_rent_to_income_ratio(median_rent, median_income)
    if ratio is None or ratio <= 0:
        return None
    # Score is 100 at the 30 percent rent-to-income threshold; higher means more affordable.
    return round(100 * (0.30 / ratio), 1)


def estimate_rent_burden_pct(
    median_rent: float | None,
    median_income: float | None,
) -> float | None:
    ratio = calculate_rent_to_income_ratio(median_rent, median_income)
    if ratio is None:
        return None
    estimate = 18 + ((ratio - 0.20) * 150)
    return round(max(12, min(65, estimate)), 1)


def calculate_population_growth_pct(
    population: int | None,
    previous_population: int | None,
) -> float | None:
    if population is None or previous_population is None or previous_population <= 0:
        return None
    return round(((population - previous_population) / previous_population) * 100, 1)


def metric_value(metric: str, row: Any) -> float | int | None:
    metric_key = normalize_metric_name(metric)
    if metric_key == "rent_to_income_ratio":
        return calculate_rent_to_income_ratio(row.median_rent, row.median_income)
    if metric_key == "population_growth_pct":
        return calculate_population_growth_pct(row.population, row.previous_population)
    return getattr(row, metric_key, None)
