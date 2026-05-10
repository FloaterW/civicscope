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

export const metricOptions: Array<{ key: MetricKey; label: string; shortLabel: string }> = [
  { key: "rent_burden_pct", label: "Rent burden", shortLabel: "Burden" },
  { key: "affordability_index", label: "Affordability index", shortLabel: "Index" },
  { key: "median_income", label: "Median income", shortLabel: "Income" },
  { key: "median_rent", label: "Median rent", shortLabel: "Rent" },
  { key: "population", label: "Population", shortLabel: "Pop." },
  { key: "population_growth_pct", label: "Population growth", shortLabel: "Growth" }
];

export async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    signal
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function levelQuery(geographyLevel: GeographyLevel) {
  return `type=${encodeURIComponent(geographyLevel)}`;
}

export function getMapData(metric: MetricKey, geographyLevel: GeographyLevel, signal?: AbortSignal) {
  return fetchJson<MapData>(
    `/api/map-data?metric=${metric}&detail=display&${levelQuery(geographyLevel)}`,
    signal
  );
}

export function getSummary(geoid: string | undefined, geographyLevel: GeographyLevel, signal?: AbortSignal) {
  const params = new URLSearchParams({ type: geographyLevel });
  if (geoid) {
    params.set("ids", geoid);
  }
  return fetchJson<Summary>(`/api/summary?${params.toString()}`, signal);
}

export function getComparison(ids: string[], geographyLevel: GeographyLevel, signal?: AbortSignal) {
  const params = new URLSearchParams({ type: geographyLevel });
  if (ids.length) {
    params.set("ids", ids.join(","));
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
    return "No data";
  }
  if (metric === "median_income" || metric === "median_rent") {
    return new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: "CAD",
      maximumFractionDigits: 0
    }).format(value);
  }
  if (metric === "population") {
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
