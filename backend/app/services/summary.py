from __future__ import annotations

from typing import Any

from app.services.metric_calculations import (
    calculate_affordability_index,
    calculate_population_growth_pct,
    calculate_rent_to_income_ratio,
    resolve_rent_burden,
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


def build_summary(
    records: list[tuple[Any, Any]],
    year: int,
    cmhc_records: list[Any] | None = None,
) -> dict[str, Any]:
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
            "vacancy_rate": None,
            "average_rent_total": None,
            "housing_starts_total": None,
            "housing_completions": None,
            "unabsorbed_units": None,
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
        [metric.renter_households for metric in metrics],
    )
    # Use the effective rent burden (official, else a labeled estimate) so the
    # summary stays consistent with the map and detail panel, which also show
    # estimated values for tracts whose official rent burden was suppressed.
    rent_burden_pct = weighted_average(
        [
            resolve_rent_burden(metric.median_rent, metric.median_income, metric.rent_burden_pct)[0]
            for metric in metrics
        ],
        [metric.renter_households for metric in metrics],
    )

    # CMHC summary values
    cmhc_values: dict[str, Any] = {
        "vacancy_rate": None,
        "average_rent_total": None,
        "housing_starts_total": None,
        "housing_completions": None,
        "unabsorbed_units": None,
    }
    if cmhc_records:
        vacancy_values = [r.vacancy_rate for r in cmhc_records if r.vacancy_rate is not None]
        universe_weights = [r.rental_universe or 0 for r in cmhc_records if r.vacancy_rate is not None]
        cmhc_values["vacancy_rate"] = weighted_average(vacancy_values, universe_weights)

        rent_values = [r.average_rent_total for r in cmhc_records if r.average_rent_total is not None]
        rent_weights = [r.rental_universe or 0 for r in cmhc_records if r.average_rent_total is not None]
        cmhc_values["average_rent_total"] = weighted_average(rent_values, rent_weights)

        starts_vals = [r.housing_starts_total for r in cmhc_records if r.housing_starts_total is not None]
        cmhc_values["housing_starts_total"] = sum(starts_vals) if starts_vals else None
        completions_vals = [r.housing_completions for r in cmhc_records if r.housing_completions is not None]
        cmhc_values["housing_completions"] = sum(completions_vals) if completions_vals else None
        ua_vals = [r.unabsorbed_units for r in cmhc_records if r.unabsorbed_units is not None]
        cmhc_values["unabsorbed_units"] = sum(ua_vals) if ua_vals else None

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
        **cmhc_values,
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
            "Rent burden uses official Statistics Canada tenant shelter-cost burden values, falling back to a rent-and-income estimate where the official value is suppressed (consistent with the map).",
        ],
    }
