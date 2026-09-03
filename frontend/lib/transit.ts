import type { MetricFieldStatus, MetricKey, TransitSnapshot } from "@/types";

const TRANSIT_METRICS = new Set<MetricKey>(["transit_score", "transit_route_count"]);

export function isTransitMetric(metric: MetricKey): boolean {
  return TRANSIT_METRICS.has(metric);
}

export function transitCoverageLabel(snapshot?: TransitSnapshot): string {
  if (snapshot?.coverage_status === "complete") return "Complete transit snapshot";
  if (snapshot?.coverage_status === "partial") return "Partial transit snapshot";
  return "Transit coverage not verified";
}

export function transitAgencyNames(
  agencies: Array<{ name: string }> | undefined
): string {
  return agencies?.map((agency) => agency.name).join(", ") || "None identified";
}

export function transitSnapshotDate(snapshot?: TransitSnapshot): string {
  return snapshot?.packaged_at?.slice(0, 10) || "Unknown";
}

export function transitMetricStatus(
  status: MetricFieldStatus | undefined,
  snapshot?: TransitSnapshot
): string {
  const baseStatus = status ?? "unavailable";
  if (baseStatus === "unavailable") return baseStatus;
  return `${baseStatus} (${snapshot?.coverage_status ?? "unknown"} coverage)`;
}
