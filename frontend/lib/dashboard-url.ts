import { isCmhcMetric, metricOptions } from "@/lib/api";
import { isTransitMetric } from "@/lib/transit";
import type { GeographyLevel, MetricKey } from "@/types";

export const DEFAULT_DASHBOARD_LEVEL: GeographyLevel = "municipality";
export const DEFAULT_DASHBOARD_METRIC: MetricKey = "rent_burden_pct";

export type DashboardUrlState = {
  level: GeographyLevel;
  metric: MetricKey;
  year?: number;
  geoid?: string;
  adjustedForTransit: boolean;
};

const geographyLevels = new Set<GeographyLevel>(["municipality", "census_tract"]);
const metricKeys = new Set<MetricKey>(metricOptions.map((option) => option.key));

function isGeographyLevel(value: string | null): value is GeographyLevel {
  return value !== null && geographyLevels.has(value as GeographyLevel);
}

function isMetricKey(value: string | null): value is MetricKey {
  return value !== null && metricKeys.has(value as MetricKey);
}

function parseYear(value: string | null): number | undefined {
  if (!value || !/^\d{4}$/.test(value)) {
    return undefined;
  }
  const year = Number(value);
  return year >= 1900 && year <= 2100 ? year : undefined;
}

function isGeoidForLevel(value: string, level: GeographyLevel): boolean {
  return level === "municipality" ? /^\d{7}$/.test(value) : /^\d{7}\.\d{2}$/.test(value);
}

/** Parse and validate CivicScope-owned query parameters. */
export function parseDashboardUrl(search: string): DashboardUrlState {
  const params = new URLSearchParams(search);
  const metric = isMetricKey(params.get("metric"))
    ? (params.get("metric") as MetricKey)
    : DEFAULT_DASHBOARD_METRIC;
  const requestedLevel = isGeographyLevel(params.get("level"))
    ? (params.get("level") as GeographyLevel)
    : DEFAULT_DASHBOARD_LEVEL;
  const adjustedForTransit = isTransitMetric(metric) && requestedLevel !== "census_tract";
  const level: GeographyLevel = adjustedForTransit ? "census_tract" : requestedLevel;
  const requestedGeoid = params.get("geoid")?.trim();

  return {
    level,
    metric,
    year: isCmhcMetric(metric) ? parseYear(params.get("year")) : undefined,
    geoid:
      requestedGeoid && isGeoidForLevel(requestedGeoid, level) ? requestedGeoid : undefined,
    adjustedForTransit
  };
}

/** Build a same-page URL while retaining query parameters and the hash owned by other features. */
export function buildDashboardUrl(
  currentHref: string,
  state: Omit<DashboardUrlState, "adjustedForTransit">
): string {
  const url = new URL(currentHref);
  url.searchParams.set("level", state.level);
  url.searchParams.set("metric", state.metric);

  if (isCmhcMetric(state.metric) && state.year !== undefined) {
    url.searchParams.set("year", String(state.year));
  } else {
    url.searchParams.delete("year");
  }

  if (state.geoid) {
    url.searchParams.set("geoid", state.geoid);
  } else {
    url.searchParams.delete("geoid");
  }

  return `${url.pathname}${url.search}${url.hash}`;
}
