export type GeographyLevel = "municipality" | "census_tract";

export type MetricKey =
  | "median_income"
  | "median_rent"
  | "rent_burden_pct"
  | "population"
  | "population_growth_pct"
  | "affordability_index"
  | "rent_to_income_ratio";

export type GeoJsonGeometry = {
  type: string;
  coordinates: unknown;
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
};

export type Geography = {
  id: number;
  geoid: string;
  name: string;
  type: string;
  county: string | null;
  state: string;
  bbox: [number, number, number, number];
  geometry: GeoJsonGeometry;
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
  };
};

export type MapData = {
  type: "FeatureCollection";
  metadata: {
    metric: MetricKey;
    year: number;
    domain: {
      min: number | null;
      max: number | null;
    };
    geography_type: GeographyLevel;
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
  items: Array<{
    geoid: string;
    name: string;
    type: string;
    county: string | null;
    metrics: MetricValues;
  }>;
};

export type GeographiesResponse = {
  year: number;
  items: Geography[];
};
