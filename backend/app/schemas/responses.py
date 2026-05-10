from typing import Any

from pydantic import BaseModel, ConfigDict


class MetricResponse(BaseModel):
    year: int
    median_income: float | None
    median_rent: float | None
    population: int | None
    previous_population: int | None
    population_growth_pct: float | None
    renter_households: int | None
    rent_burden_pct: float | None
    rent_to_income_ratio: float | None
    affordability_index: float | None

    model_config = ConfigDict(from_attributes=True)


class GeographyResponse(BaseModel):
    id: int
    geoid: str
    name: str
    type: str
    county: str | None
    state: str
    bbox: list[float]
    geometry: dict[str, Any]
    geometry_source: str
    metrics: MetricResponse | None = None

    model_config = ConfigDict(from_attributes=True)
