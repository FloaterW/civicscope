from __future__ import annotations

from collections import defaultdict
from math import floor
from typing import Any, Mapping, Sequence

from app.services.metric_calculations import metric_value


CMHC_COUNT_METRICS = frozenset(
    {
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
)

CMHC_REAL_TRACT_METRICS = frozenset(
    {"housing_starts_total", "housing_completions"}
)


def allocate_integer_total(
    total: int,
    weights: Mapping[str, int | float | None],
) -> dict[str, int]:
    """Allocate an integer total without losing units to independent rounding.

    Largest-remainder allocation is deterministic: equal fractional remainders
    are resolved by geography identifier. When every supplied weight is zero,
    the total is split equally so the parent total is still conserved.
    """
    if total < 0:
        raise ValueError("Allocation total cannot be negative.")
    if not weights:
        return {}

    normalized = {key: max(float(value or 0), 0.0) for key, value in weights.items()}
    if sum(normalized.values()) == 0:
        normalized = {key: 1.0 for key in normalized}

    denominator = sum(normalized.values())
    raw = {key: total * weight / denominator for key, weight in normalized.items()}
    allocated = {key: floor(value) for key, value in raw.items()}
    remainder = total - sum(allocated.values())
    recipients = sorted(
        raw,
        key=lambda key: (-(raw[key] - allocated[key]), key),
    )
    for key in recipients[:remainder]:
        allocated[key] += 1
    return allocated


def build_tract_count_allocations(
    records: Sequence[tuple[Any, Any]],
    municipality_name_to_geoid: Mapping[str, str],
    cmhc_by_geoid: Mapping[str, Any],
    real_tract_cmhc: Mapping[str, Any],
) -> dict[str, dict[str, int | None]]:
    """Resolve every tract CMHC count once for consistent API serialization.

    Published tract starts/completions are fixed first. Any remaining municipal
    total is allocated among uncovered tracts by renter-household share. Other
    count metrics allocate the complete municipal total across all child tracts.
    """
    by_municipality: dict[str, list[tuple[Any, Any]]] = defaultdict(list)
    allocations: dict[str, dict[str, int | None]] = {
        geography.geoid: {} for geography, _ in records
    }
    for geography, metric in records:
        if geography.county:
            by_municipality[geography.county].append((geography, metric))

    for municipality_name, tract_records in by_municipality.items():
        parent_geoid = municipality_name_to_geoid.get(municipality_name)
        parent = cmhc_by_geoid.get(parent_geoid) if parent_geoid else None
        if parent is None:
            continue

        for metric_key in CMHC_COUNT_METRICS:
            parent_value = metric_value(metric_key, parent)
            fixed: dict[str, int] = {}
            if metric_key in CMHC_REAL_TRACT_METRICS:
                for geography, _ in tract_records:
                    real_row = real_tract_cmhc.get(geography.geoid)
                    real_value = (
                        getattr(real_row, metric_key, None) if real_row is not None else None
                    )
                    if real_value is not None:
                        fixed[geography.geoid] = int(real_value)

            for geoid, value in fixed.items():
                allocations[geoid][metric_key] = value

            uncovered = [
                (geography, metric)
                for geography, metric in tract_records
                if geography.geoid not in fixed
            ]
            if parent_value is None:
                for geography, _ in uncovered:
                    allocations[geography.geoid][metric_key] = None
                continue

            # If independently published tract data exceeds a municipal series,
            # preserve the published values and allocate no additional estimate.
            remaining = max(int(parent_value) - sum(fixed.values()), 0)
            weights = {
                geography.geoid: getattr(metric, "renter_households", None)
                for geography, metric in uncovered
            }
            estimated = allocate_integer_total(remaining, weights)
            for geography, _ in uncovered:
                allocations[geography.geoid][metric_key] = estimated.get(
                    geography.geoid, 0
                )

    return allocations
