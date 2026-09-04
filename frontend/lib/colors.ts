// Shared civic color ramp. Used by both the choropleth map and the comparison
// chart so the two views encode value with the same colors.

// Null geographies (no value for the active metric) render in this neutral grey.
export const NULL_COLOR = "#d8dee6";
// Flat fill used when every geography shares one value (e.g. CMA-level CMHC data).
export const FLAT_COLOR = "#68b7aa";
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
