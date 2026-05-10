from __future__ import annotations

from typing import Any

from app.services.metric_calculations import (
    calculate_affordability_index,
    calculate_population_growth_pct,
    calculate_rent_to_income_ratio,
)


def weighted_average(values: list[float | None], weights: list[int | None]) -> float | None:
    weighted_total = 0.0
    weight_total = 0
    for value, weight in zip(values, weights, strict=False):
        if value is None or not weight or weight <= 0:
            continue
        weighted_total += value * weight
        weight_total += weight
    if weight_total == 0:
        return None
    return round(weighted_total / weight_total, 2)


def build_summary(records: list[tuple[Any, Any]], year: int) -> dict[str, Any]:
    if not records:
        return {
            "year": year,
            "region_count": 0,
            "population": 0,
            "previous_population": 0,
            "population_growth_pct": None,
            "median_income": None,
            "median_rent": None,
            "rent_to_income_ratio": None,
            "rent_burden_pct": None,
            "affordability_index": None,
            "selected_geographies": [],
            "notes": ["No matching geographies were found."],
        }

    geographies = [geography for geography, _ in records]
    metrics = [metric for _, metric in records]
    population = sum(metric.population or 0 for metric in metrics)
    previous_population = sum(metric.previous_population or 0 for metric in metrics)
    renter_households = sum(metric.renter_households or 0 for metric in metrics)

    median_income = weighted_average(
        [metric.median_income for metric in metrics],
        [metric.population for metric in metrics],
    )
    median_rent = weighted_average(
        [metric.median_rent for metric in metrics],
        [metric.renter_households or metric.population for metric in metrics],
    )
    rent_burden_pct = weighted_average(
        [metric.rent_burden_pct for metric in metrics],
        [metric.renter_households for metric in metrics],
    )

    return {
        "year": year,
        "region_count": len(records),
        "population": population,
        "previous_population": previous_population,
        "population_growth_pct": calculate_population_growth_pct(population, previous_population),
        "median_income": median_income,
        "median_rent": median_rent,
        "rent_to_income_ratio": calculate_rent_to_income_ratio(median_rent, median_income),
        "rent_burden_pct": rent_burden_pct,
        "affordability_index": calculate_affordability_index(median_rent, median_income),
        "renter_households": renter_households,
        "selected_geographies": [
            {
                "geoid": geography.geoid,
                "name": geography.name,
                "type": geography.type,
                "county": geography.county,
            }
            for geography in geographies
        ],
        "notes": [
            "Summary uses weighted averages of local median values; use official regional aggregates for publication-grade reporting.",
            "Rent burden uses Statistics Canada tenant shelter-cost burden values when official profile metrics are loaded.",
        ],
    }
