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
    dwellings_total: int | None = None
    dwellings_single_detached: int | None = None
    dwellings_semi_detached: int | None = None
    dwellings_row_house: int | None = None
    dwellings_apt_duplex: int | None = None
    dwellings_apt_low_rise: int | None = None
    dwellings_apt_high_rise: int | None = None
    owner_households: int | None = None
    data_quality: dict[str, str] | None = None

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


class GeographySummaryResponse(BaseModel):
    id: int
    geoid: str
    name: str
    type: str
    county: str | None
    state: str
    bbox: list[float]
    geometry_source: str
    metrics: MetricResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class GeographiesListResponse(BaseModel):
    year: int
    items: list[GeographySummaryResponse]
