export type GeographyLevel = "municipality" | "census_tract";

export type MetricKey =
  | "median_income"
  | "median_rent"
  | "rent_burden_pct"
  | "population"
  | "population_growth_pct"
  | "affordability_index"
  | "rent_to_income_ratio"
  | "vacancy_rate"
  | "average_rent_total"
  | "average_rent_bachelor"
  | "average_rent_1br"
  | "average_rent_2br"
  | "average_rent_3br_plus"
  | "turnover_rate"
  | "availability_rate"
  | "rental_universe"
  | "housing_starts_total"
  | "housing_starts_single"
  | "housing_starts_semi"
  | "housing_starts_row"
  | "housing_starts_apartment"
  | "housing_completions"
  | "units_under_construction"
  | "unabsorbed_units";

export type GeoJsonGeometry = {
  type: string;
  coordinates: unknown;
};

/** Per-field provenance for a census metric value. */
export type MetricFieldStatus = "official" | "estimated" | "unavailable" | "low_confidence";

export type MetricQuality = {
  median_income?: MetricFieldStatus;
  median_rent?: MetricFieldStatus;
  population?: MetricFieldStatus;
  previous_population?: MetricFieldStatus;
  renter_households?: MetricFieldStatus;
  rent_burden_pct?: MetricFieldStatus;
  population_growth_pct?: MetricFieldStatus;
  affordability_index?: MetricFieldStatus;
};

export type MetricValues = {
  year: number;
  median_income: number | null;
  median_rent: number | null;
  population: number | null;
  previous_population: number | null;
  population_growth_pct: number | null;
  renter_households: number | null;
  rent_burden_pct: number | null;
  rent_to_income_ratio: number | null;
  affordability_index: number | null;
  dwellings_total: number | null;
  dwellings_single_detached: number | null;
  dwellings_semi_detached: number | null;
  dwellings_row_house: number | null;
  dwellings_apt_duplex: number | null;
  dwellings_apt_low_rise: number | null;
  dwellings_apt_high_rise: number | null;
  owner_households: number | null;
  /** Field-level provenance flags (official / estimated / unavailable / low_confidence). */
  data_quality?: MetricQuality;
};

export type CmhcMetricValues = {
  year: number;
  vacancy_rate: number | null;
  average_rent_total: number | null;
  average_rent_bachelor: number | null;
  average_rent_1br: number | null;
  average_rent_2br: number | null;
  average_rent_3br_plus: number | null;
  turnover_rate: number | null;
  availability_rate: number | null;
  rental_universe: number | null;
  housing_starts_total: number | null;
  housing_starts_single: number | null;
  housing_starts_semi: number | null;
  housing_starts_row: number | null;
  housing_starts_apartment: number | null;
  housing_completions: number | null;
  units_under_construction: number | null;
  unabsorbed_units: number | null;
  rms_surveyed: boolean;
  allocated?: boolean;
};

export type Geography = {
  id: number;
  geoid: string;
  name: string;
  type: string;
  county: string | null;
  state: string;
  bbox: [number, number, number, number];
  geometry?: GeoJsonGeometry;
  geometry_source: string;
  metrics?: MetricValues;
};

export type MapFeature = {
  type: "Feature";
  geometry: GeoJsonGeometry;
  properties: Geography & {
    metric: MetricKey;
    value: number | null;
    metrics: MetricValues;
    cmhc_metrics?: CmhcMetricValues | null;
    cmhc_year?: number;
  };
};

export type MapData = {
  type: "FeatureCollection";
  metadata: {
    metric: MetricKey;
    year: number;
    cmhc_year?: number;
    domain: {
      min: number | null;
      max: number | null;
    };
    geography_type: GeographyLevel;
    available_years?: number[];
    data_quality: {
      metric_status: "official" | "estimated" | "mixed";
      label: string;
      description: string;
    };
    source: string;
  };
  features: MapFeature[];
};

export type Summary = {
  year: number;
  region_count: number;
  population: number;
  previous_population: number;
  population_growth_pct: number | null;
  median_income: number | null;
  median_rent: number | null;
  rent_to_income_ratio: number | null;
  rent_burden_pct: number | null;
  affordability_index: number | null;
  renter_households: number;
  vacancy_rate?: number | null;
  average_rent_total?: number | null;
  housing_starts_total?: number | null;
  housing_completions?: number | null;
  unabsorbed_units?: number | null;
  selected_geographies: Array<{
    geoid: string;
    name: string;
    type: string;
    county: string | null;
  }>;
  notes: string[];
};

export type CompareResponse = {
  year: number;
  cmhc_year?: number;
  items: Array<{
    geoid: string;
    name: string;
    type: string;
    county: string | null;
    metrics: MetricValues;
    cmhc_metrics?: CmhcMetricValues | null;
  }>;
};

export type GeographiesResponse = {
  year: number;
  items: Geography[];
};
