import type {
  CompareResponse,
  GeographiesResponse,
  GeographyLevel,
  MapData,
  MetricKey,
  Summary
} from "@/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export const metricOptions: Array<{ key: MetricKey; label: string; shortLabel: string; group: string }> = [
  { key: "rent_burden_pct", label: "Rent burden", shortLabel: "Burden", group: "Census Profile" },
  { key: "affordability_index", label: "Affordability index", shortLabel: "Index", group: "Census Profile" },
  { key: "median_income", label: "Median income", shortLabel: "Income", group: "Census Profile" },
  { key: "median_rent", label: "Median rent", shortLabel: "Rent", group: "Census Profile" },
  { key: "population", label: "Population", shortLabel: "Pop.", group: "Census Profile" },
  { key: "population_growth_pct", label: "Population growth", shortLabel: "Growth", group: "Census Profile" },
  { key: "vacancy_rate", label: "Vacancy rate", shortLabel: "Vacancy", group: "CMHC Rental Market" },
  { key: "average_rent_total", label: "Average rent (CMHC)", shortLabel: "CMHC Rent", group: "CMHC Rental Market" },
  { key: "housing_starts_total", label: "Housing starts", shortLabel: "Starts", group: "CMHC Rental Market" },
  { key: "housing_completions", label: "Completions", shortLabel: "Compl.", group: "CMHC Rental Market" },
  { key: "turnover_rate", label: "Turnover rate", shortLabel: "Turnover", group: "CMHC Rental Market" },
  { key: "availability_rate", label: "Availability rate", shortLabel: "Avail.", group: "CMHC Rental Market" },
];

export const CMHC_METRIC_KEYS: Set<MetricKey> = new Set([
  "vacancy_rate", "average_rent_total", "average_rent_bachelor", "average_rent_1br",
  "average_rent_2br", "average_rent_3br_plus", "turnover_rate", "availability_rate",
  "rental_universe", "housing_starts_total", "housing_starts_single", "housing_starts_semi",
  "housing_starts_row", "housing_starts_apartment", "housing_completions", "units_under_construction",
  "unabsorbed_units",
]);

export function isCmhcMetric(metric: MetricKey): boolean {
  return CMHC_METRIC_KEYS.has(metric);
}

export async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new Error(`Unable to reach CivicScope API at ${API_BASE}. Is the backend running?`);
  }
  if (!response.ok) {
    let message: string;
    try {
      const body = await response.json();
      message = body?.detail ?? body?.message ?? JSON.stringify(body);
    } catch {
      message = await response.text();
    }
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function levelQuery(geographyLevel: GeographyLevel) {
  return `type=${encodeURIComponent(geographyLevel)}`;
}

export function getMapData(metric: MetricKey, geographyLevel: GeographyLevel, signal?: AbortSignal, year?: number) {
  const params = new URLSearchParams({
    metric,
    detail: "display",
    type: geographyLevel,
  });
  if (year !== undefined) {
    params.set("year", String(year));
  }
  return fetchJson<MapData>(`/api/map-data?${params.toString()}`, signal);
}

export function getSummary(geoid: string | undefined, geographyLevel: GeographyLevel, signal?: AbortSignal, year?: number) {
  const params = new URLSearchParams({ type: geographyLevel });
  if (geoid) {
    params.set("ids", geoid);
  }
  if (year !== undefined) {
    params.set("year", String(year));
  }
  return fetchJson<Summary>(`/api/summary?${params.toString()}`, signal);
}

export function getComparison(ids: string[], geographyLevel: GeographyLevel, signal?: AbortSignal, year?: number) {
  const params = new URLSearchParams({ type: geographyLevel });
  if (ids.length) {
    params.set("ids", ids.join(","));
  }
  if (year !== undefined) {
    params.set("year", String(year));
  }
  return fetchJson<CompareResponse>(`/api/compare?${params.toString()}`, signal);
}

export function searchGeographies(search: string, geographyLevel: GeographyLevel, signal?: AbortSignal) {
  const params = new URLSearchParams({ type: geographyLevel });
  if (search.trim()) {
    params.set("search", search.trim());
  }
  return fetchJson<GeographiesResponse>(`/api/geographies?${params.toString()}`, signal);
}

export function formatMetric(metric: MetricKey, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  if (metric === "median_income" || metric === "median_rent" || metric.startsWith("average_rent")) {
    return new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: "CAD",
      maximumFractionDigits: 0
    }).format(value);
  }
  if (
    metric === "population" ||
    metric === "rental_universe" ||
    metric.startsWith("housing_starts") ||
    metric === "housing_completions" ||
    metric === "units_under_construction" ||
    metric === "unabsorbed_units"
  ) {
    return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 0 }).format(value);
  }
  if (metric === "rent_to_income_ratio") {
    return `${Math.round(value * 100)}%`;
  }
  if (metric === "affordability_index") {
    return value.toFixed(1);
  }
  return `${value.toFixed(1)}%`;
}

export function getMetricLabel(metric: MetricKey): string {
  return metricOptions.find((option) => option.key === metric)?.label ?? metric;
}
