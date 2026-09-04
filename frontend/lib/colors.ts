import type { MapData } from "@/types";

// Civic map color ramps. Comparison bars deliberately use one neutral teal so
// a small comparison cohort cannot be mistaken for the map's full-data scale.

// Null geographies (no value for the active metric) render in this neutral grey.
export const NULL_COLOR = "#d8dee6";
// Flat fill used when every geography shares one value (e.g. CMA-level CMHC data).
export const FLAT_COLOR = "#68b7aa";
export const COMPARISON_BAR_COLOR = "var(--civic-teal)";
// Metric-aware ramps prevent positive values (for example affordability or
// transit access) from receiving the same warning color used for high burden.
export const RISK_RAMP = ["#f1f7f0", "#68b7aa", "#a64822"];
export const POSITIVE_RAMP = ["#f7ede8", "#68b7aa", "#28745f"];
export const SEQUENTIAL_RAMP = ["#eef2f7", "#6b9bbf", "#285b9f"];

const POSITIVE_METRICS = new Set([
  "affordability_index",
  "median_income",
  "transit_score",
  "transit_route_count"
]);
const RISK_METRICS = new Set([
  "rent_burden_pct",
  "rent_to_income_ratio",
  "median_rent",
  "average_rent_total",
  "average_rent_bachelor",
  "average_rent_1br",
  "average_rent_2br",
  "average_rent_3br_plus"
]);

export function rampForMetric(metric?: string): string[] {
  if (metric && POSITIVE_METRICS.has(metric)) return POSITIVE_RAMP;
  if (metric && RISK_METRICS.has(metric)) return RISK_RAMP;
  return SEQUENTIAL_RAMP;
}

export function mixHex(a: string, b: string, t: number): string {
  const parse = (hex: string): [number, number, number] => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16)
  ];
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const channel = (x: number, y: number) => Math.round(x + (y - x) * t);
  const toHex = (n: number) => n.toString(16).padStart(2, "0");
  return `#${toHex(channel(ar, br))}${toHex(channel(ag, bg))}${toHex(channel(ab, bb))}`;
}

/** Sample the 3-color ramp at fraction t in [0, 1]. */
export function rampColorAt(t: number, metric?: string): string {
  const ramp = rampForMetric(metric);
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (ramp.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(ramp.length - 1, lower + 1);
  const frac = scaled - lower;
  return mixHex(ramp[lower], ramp[upper], frac);
}

/** Color for a value given the domain [min, max]. Falls back to the flat color
 * when the domain has no spread (a single value across all areas). */
export function rampColorForValue(
  value: number,
  min: number,
  max: number,
  metric?: string
): string {
  if (!Number.isFinite(value)) return NULL_COLOR;
  if (max <= min) return FLAT_COLOR;
  return rampColorAt((value - min) / (max - min), metric);
}

export type ChoroplethClass = {
  lower: number;
  upper: number | null;
  color: string;
};

export type ChoroplethScale = {
  classes: ChoroplethClass[];
  min: number | null;
  max: number | null;
  flat: boolean;
  availableCount: number;
  noDataCount: number;
};

/**
 * Build up to five true quantile classes from the active map dataset.
 * Boundaries are observed values rather than interpolated estimates, which
 * keeps count and currency legend labels aligned with the values users see.
 */
export function buildChoroplethScale(data: MapData): ChoroplethScale {
  const availableValues = data.features
    .map((feature) => feature.properties.value)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const domainMin = data.metadata.domain?.min;
  const domainMax = data.metadata.domain?.max;
  const trustedDomain =
    typeof domainMin === "number" &&
    Number.isFinite(domainMin) &&
    typeof domainMax === "number" &&
    Number.isFinite(domainMax) &&
    domainMin <= domainMax
      ? { min: domainMin, max: domainMax }
      : null;
  // The API deliberately excludes low-confidence values from metadata.domain.
  // Keep those values visible on the map, but do not let them distort the
  // quantile boundaries used for every other geography.
  const values = availableValues
    .filter(
      (value) => !trustedDomain || (value >= trustedDomain.min && value <= trustedDomain.max)
    )
    .sort((a, b) => a - b);
  const noDataCount = data.features.length - availableValues.length;

  if (values.length === 0) {
    return {
      classes: [],
      min: null,
      max: null,
      flat: false,
      availableCount: availableValues.length,
      noDataCount
    };
  }

  const min = values[0];
  const max = values[values.length - 1];
  if (min === max) {
    return {
      classes: [{ lower: min, upper: null, color: FLAT_COLOR }],
      min,
      max,
      flat: true,
      availableCount: availableValues.length,
      noDataCount
    };
  }

  const candidates: number[] = [];
  for (let classIndex = 1; classIndex < 5; classIndex += 1) {
    const observedIndex = Math.min(
      values.length - 1,
      Math.floor((classIndex * values.length) / 5)
    );
    const boundary = values[observedIndex];
    if (
      boundary > min &&
      candidates[candidates.length - 1] !== boundary
    ) {
      candidates.push(boundary);
    }
  }

  // Highly sparse count data can place every quantile boundary on zero even
  // when a small number of positive values exists. Preserve a distinct class
  // for those positive geographies instead of painting the whole map alike.
  if (candidates.length === 0) {
    candidates.push(max);
  }

  const boundaries = [min, ...candidates];
  const classes = boundaries.map((lower, index) => ({
    lower,
    upper: boundaries[index + 1] ?? null,
    color: rampColorAt(
      boundaries.length === 1 ? 0.5 : index / (boundaries.length - 1),
      data.metadata.metric
    )
  }));

  return {
    classes,
    min,
    max,
    flat: false,
    availableCount: availableValues.length,
    noDataCount
  };
}

/** MapLibre expression that exactly matches buildChoroplethScale's classes. */
export function choroplethColorExpression(data: MapData): unknown[] {
  const scale = buildChoroplethScale(data);

  if (scale.classes.length === 0) {
    return ["literal", NULL_COLOR];
  }

  if (scale.flat) {
    return ["case", ["==", ["get", "value"], null], NULL_COLOR, FLAT_COLOR];
  }

  const [firstClass, ...remainingClasses] = scale.classes;
  const stepStops = remainingClasses.flatMap((colorClass) => [
    colorClass.lower,
    colorClass.color
  ]);

  return [
    "case",
    ["==", ["get", "value"], null],
    NULL_COLOR,
    [
      "step",
      ["to-number", ["get", "value"], firstClass.lower],
      firstClass.color,
      ...stepStops
    ]
  ];
}
