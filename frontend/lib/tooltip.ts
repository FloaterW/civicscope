import { formatMetric, getMetricLabel } from "@/lib/api";
import type { MetricFieldStatus, MetricKey, MetricQuality, MetricValues } from "@/types";

export function safeJsonParse<T>(raw: unknown, fallback: T): T {
  if (typeof raw !== "string") return (raw as T) ?? fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Build the hover-tooltip markup for a geography feature. Properties arrive
 * JSON-stringified from the vector source, so `value`/`metrics` may be strings
 *, parse them defensively. Appends a provenance note when the census metric is
 * flagged estimated / low confidence for this feature.
 *
 * Pure and dependency-light so it can be unit-tested without a browser/WebGL
 * (the pointer-driven popup is unreliable to drive in headless CI).
 */
export function buildTooltipHtml(
  rawProperties: Record<string, unknown>,
  metric: MetricKey
): string | null {
  const name = typeof rawProperties.name === "string" ? rawProperties.name : null;
  if (!name) {
    return null;
  }

  const rawValue = rawProperties.value;
  const parsed =
    rawValue === null || rawValue === undefined || rawValue === "" ? null : Number(rawValue);
  const value = parsed !== null && Number.isFinite(parsed) ? parsed : null;

  const metrics = safeJsonParse<MetricValues | null>(rawProperties.metrics, null);
  const fieldStatus = metrics?.data_quality?.[metric as keyof MetricQuality] as
    | MetricFieldStatus
    | undefined;
  const note =
    fieldStatus === "estimated"
      ? " (estimated)"
      : fieldStatus === "derived"
        ? " (derived)"
      : fieldStatus === "low_confidence"
        ? " (low confidence)"
        : "";

  return [
    `<div class="civic-map-popup__name">${escapeHtml(name)}</div>`,
    `<div class="civic-map-popup__metric">${escapeHtml(getMetricLabel(metric))}</div>`,
    `<div class="civic-map-popup__value">${escapeHtml(formatMetric(metric, value))}${escapeHtml(note)}</div>`
  ].join("");
}
