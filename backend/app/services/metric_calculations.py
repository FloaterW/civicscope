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
    "unabsorbed_units",
}

TRANSIT_METRICS = {
    "transit_route_count",
    "transit_score",
}

VALID_METRICS = {
    "median_income",
    "median_rent",
    "rent_burden_pct",
    "population",
    "population_growth_pct",
    "affordability_index",
    "rent_to_income_ratio",
} | CMHC_METRICS | TRANSIT_METRICS

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
    # Transit aliases
    "transit": "transit_score",
    "routes": "transit_route_count",
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


# Census tracts can have a tiny 2016 base population (e.g. a tract that was
# largely undeveloped), which turns ordinary growth into an absurd percentage.
# Growth computed off a base below this threshold is flagged low-confidence so
# the UI never presents it as a stable trend.
LOW_POPULATION_DENOMINATOR = 100


def is_low_denominator_growth(previous_population: int | None) -> bool:
    return previous_population is not None and 0 < previous_population < LOW_POPULATION_DENOMINATOR


def resolve_rent_burden(
    median_rent: float | None,
    median_income: float | None,
    official_value: float | None,
) -> tuple[float | None, str]:
    """Return the effective rent-burden value and its provenance.

    Official Statistics Canada values are used verbatim.  When the official
    value is suppressed/missing we fall back to an estimate derived from rent
    and income, clearly labeled ``estimated``.  When even that is impossible
    the value is ``unavailable`` (rendered as "Not available").
    """
    if official_value is not None:
        return official_value, "official"
    estimate = estimate_rent_burden_pct(median_rent, median_income)
    if estimate is not None:
        return estimate, "estimated"
    return None, "unavailable"


def build_metric_quality(row: Any) -> dict[str, str]:
    """Per-field provenance for a census metric row.

    Statuses: ``official`` (published), ``derived`` (calculated from published
    inputs), ``estimated`` (fallback formula), ``unavailable``
    (suppressed/missing), and ``low_confidence`` (derived off a tiny denominator).
    """
    _, rent_burden_status = resolve_rent_burden(
        row.median_rent, row.median_income, row.rent_burden_pct
    )
    growth = calculate_population_growth_pct(row.population, row.previous_population)
    if growth is None:
        growth_status = "unavailable"
    elif is_low_denominator_growth(row.previous_population):
        growth_status = "low_confidence"
    else:
        growth_status = "derived"

    def present(value: Any) -> str:
        return "official" if value is not None else "unavailable"

    return {
        "median_income": present(row.median_income),
        "median_rent": present(row.median_rent),
        "population": present(row.population),
        "previous_population": present(row.previous_population),
        "renter_households": present(row.renter_households),
        "rent_burden_pct": rent_burden_status,
        "population_growth_pct": growth_status,
        "affordability_index": (
            "derived" if row.affordability_index is not None else "unavailable"
        ),
        "transit_score": (
            "derived" if getattr(row, "transit_score", None) is not None else "unavailable"
        ),
        "transit_route_count": (
            "derived"
            if getattr(row, "transit_route_count", None) is not None
            else "unavailable"
        ),
    }


def metric_value(metric: str, row: Any) -> float | int | None:
    metric_key = normalize_metric_name(metric)
    if metric_key == "rent_to_income_ratio":
        return calculate_rent_to_income_ratio(row.median_rent, row.median_income)
    if metric_key == "population_growth_pct":
        return calculate_population_growth_pct(row.population, row.previous_population)
    if metric_key == "rent_burden_pct":
        # Use the effective value (official, else labeled estimate) so the map
        # and the detail panel agree on what they display.
        value, _ = resolve_rent_burden(row.median_rent, row.median_income, row.rent_burden_pct)
        return value
    return getattr(row, metric_key, None)
