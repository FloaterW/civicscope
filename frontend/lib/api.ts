import type {
  CompareResponse,
  GeographiesResponse,
  GeographyLevel,
  MapData,
  MetricKey,
  Summary
} from "@/types";
import {
  isTransitFeatureCollection,
  type TransitFeatureCollection
} from "@/lib/transit-map";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const DEFAULT_API_TIMEOUT_MS = 60_000;

export function normalizeApiTimeout(value: number): number {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : DEFAULT_API_TIMEOUT_MS;
}

export const API_TIMEOUT_MS = normalizeApiTimeout(
  Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS ?? DEFAULT_API_TIMEOUT_MS)
);

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
  { key: "transit_score", label: "Transit access score", shortLabel: "Transit", group: "Transit Access" },
  { key: "transit_route_count", label: "Transit routes nearby", shortLabel: "Routes", group: "Transit Access" },
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

export function mapDataCacheKey(
  geographyLevel: GeographyLevel,
  metric: MetricKey,
  year?: number
): string {
  const family = isCmhcMetric(metric) ? `cmhc:${year ?? "latest"}` : "census";
  return `${geographyLevel}:${family}`;
}

let transitRoutesPromise: Promise<TransitFeatureCollection> | null = null;

export function getTransitRoutes(): Promise<TransitFeatureCollection> {
  if (!transitRoutesPromise) {
    transitRoutesPromise = fetchJson<unknown>("/api/transit-routes")
      .then((payload) => {
        if (!isTransitFeatureCollection(payload)) {
          throw new Error("Transit route data is empty or malformed.");
        }
        return payload;
      })
      .catch((error) => {
        transitRoutesPromise = null;
        throw error;
      });
  }
  return transitRoutesPromise;
}

export async function fetchJson<T>(
  path: string,
  signal?: AbortSignal,
  timeoutMs: number = API_TIMEOUT_MS
): Promise<T> {
  const effectiveTimeoutMs = normalizeApiTimeout(timeoutMs);
  const requestController = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => requestController.abort(signal?.reason);
  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }
  const timeout = globalThis.setTimeout(() => {
    timedOut = true;
    requestController.abort();
  }, effectiveTimeoutMs);
  let response: Response | undefined;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      signal: requestController.signal
    });
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
    return (await response.json()) as T;
  } catch (error) {
    if (requestController.signal.aborted) {
      if (timedOut) {
        throw new Error(
          `The CivicScope API did not respond within ${Math.max(1, Math.ceil(effectiveTimeoutMs / 1000))} seconds. Try again.`
        );
      }
      throw error;
    }
    if (!response) {
      throw new Error(`Unable to reach CivicScope API at ${API_BASE}. Is the backend running?`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }
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
  if (metric === "affordability_index" || metric === "transit_score") {
    return value.toFixed(1);
  }
  if (metric === "transit_route_count") {
    return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 0 }).format(value);
  }
  return `${value.toFixed(1)}%`;
}

export function getMetricLabel(metric: MetricKey): string {
  return metricOptions.find((option) => option.key === metric)?.label ?? metric;
}
