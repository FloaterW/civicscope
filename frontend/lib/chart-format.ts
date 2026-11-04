import { formatMetric } from "@/lib/api";
import type { MetricKey } from "@/types";

const COMPACT_INTEGER = new Intl.NumberFormat("en-CA", {
  notation: "compact",
  maximumFractionDigits: 0
});
const COMPACT_DECIMAL = new Intl.NumberFormat("en-CA", {
  notation: "compact",
  maximumFractionDigits: 1
});

/** Recharts labels can receive nonnumeric values. Never coerce missing data to zero. */
export function formatChartLabel(metric: MetricKey, value: unknown, compact: boolean): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const formatted = formatMetric(metric, value);
  if (!compact || Math.abs(value) < 1_000 || formatted.endsWith("%")) return formatted;
  const formatter = Math.abs(value) >= 1_000_000 ? COMPACT_DECIMAL : COMPACT_INTEGER;
  // The currency unit remains on the y-axis; repeating it on every short label
  // crowds equal-height bars at phone widths. Tooltips and the table stay exact.
  return formatter.format(value);
}
