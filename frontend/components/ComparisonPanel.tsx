"use client";

import { Download } from "lucide-react";
import { useCallback, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { formatMetric, getMetricLabel, isCmhcMetric } from "@/lib/api";
import { COMPARISON_BAR_COLOR } from "@/lib/colors";
import { rowsToCsv } from "@/lib/csv-export";
import { isTransitMetric, transitAgencyNames, transitSnapshotDate } from "@/lib/transit";
import type { CompareResponse, GeographyLevel, MetricKey, TransitSnapshot } from "@/types";

type Props = {
  comparison: CompareResponse | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  loading: boolean;
  displayYear?: number;
  isUserSelection?: boolean;
  transitSnapshot?: TransitSnapshot;
};

const defaultComparisonNouns: Record<GeographyLevel, string> = {
  municipality: "the default GTA municipalities",
  census_tract: "the most populous census tracts"
};

export function ComparisonPanel({ comparison, metric, geographyLevel, loading, displayYear, isUserSelection = false, transitSnapshot }: Props) {
  const [chartTooltipActive, setChartTooltipActive] = useState(false);
  const isCmhc = isCmhcMetric(metric);
  const isTransit = isTransitMetric(metric);
  const showsRentRatio = !isCmhc && !isTransit;
  const snapshotDate = transitSnapshotDate(transitSnapshot);
  const transitPeriodLabel =
    snapshotDate === "Unknown"
      ? "Transit snapshot date unavailable"
      : `Transit snapshot ${snapshotDate}`;
  const comparisonRows =
    comparison?.items
      .map((item) => {
        const allMetrics = { ...item.metrics, ...item.cmhc_metrics } as Record<string, unknown>;
        const raw = allMetrics[metric];
        const rawValue = typeof raw === "number" ? raw : null;
        const lowConfidence =
          metric === "population_growth_pct" &&
          item.metrics.data_quality?.population_growth_pct === "low_confidence";
        return {
          geoid: item.geoid,
          name: chartLabel(item.name, item.type, item.geoid),
          fullName: item.name,
          value: lowConfidence ? null : rawValue,
          rawValue,
          lowConfidence,
        };
      }) ?? [];
  const chartData = comparisonRows.filter(
    (item): item is typeof item & { value: number; rawValue: number } => item.value !== null
  );
  const hasChartData = chartData.length > 0;
  const hasRows = comparisonRows.length > 0;
  const missingCount = comparisonRows.filter((item) => item.rawValue === null).length;
  const lowConfidenceCount = comparisonRows.filter((item) => item.lowConfidence).length;
  const cohortDescription = isUserSelection
    ? `selected ${geographyLevel === "municipality" ? "municipalities" : "census tracts"}`
    : defaultComparisonNouns[geographyLevel];
  const comparisonYear = displayYear ?? comparison?.year ?? 2021;

  const handleExportCsv = useCallback(() => {
    if (!comparison) return;
    const metricLabel = getMetricLabel(metric);
    const transitHeaders = isTransit
      ? ["Transit coverage", "Included agencies", "Missing agencies", "Snapshot date"]
      : [];
    const rows = [[
      "Area",
      "Geoid",
      metricLabel,
      "Status",
      ...transitHeaders,
      ...(showsRentRatio ? ["Rent-to-income ratio"] : [])
    ]];
    for (const item of comparison.items) {
      const allMetrics = { ...item.metrics, ...item.cmhc_metrics } as Record<string, unknown>;
      const val = allMetrics[metric];
      const lowConfidence =
        metric === "population_growth_pct" &&
        item.metrics.data_quality?.population_growth_pct === "low_confidence";
      const row = [
        item.name,
        item.geoid,
        val != null ? String(val) : "",
        val == null ? "unavailable" : lowConfidence ? "low_confidence" : "available",
        ...(isTransit
          ? [
              transitSnapshot?.coverage_status ?? "unknown",
              transitAgencyNames(transitSnapshot?.included_agencies),
              transitAgencyNames(transitSnapshot?.missing_agencies),
              transitSnapshotDate(transitSnapshot)
            ]
          : []),
        ...(showsRentRatio ? [item.metrics.rent_to_income_ratio != null ? String(item.metrics.rent_to_income_ratio) : ""] : [])
      ];
      rows.push(row);
    }
    const csv = rowsToCsv(rows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `civicscope-${metric}-${geographyLevel}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(() => URL.revokeObjectURL(url), 100);
  }, [comparison, metric, geographyLevel, isTransit, showsRentRatio, transitSnapshot]);

  return (
    <div data-testid="comparison-panel" className="p-4">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-civic-ink">Comparison</h2>
          <p className="text-xs text-civic-muted">
            {getMetricLabel(metric)} across {cohortDescription}
          </p>
          {missingCount > 0 && (
            <p className="mt-1 text-xs text-civic-muted">
              {missingCount} {missingCount === 1 ? "area is" : "areas are"} listed as Not available.
            </p>
          )}
          {lowConfidenceCount > 0 && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
              {lowConfidenceCount} low-confidence growth {lowConfidenceCount === 1 ? "value is" : "values are"} shown in the table but excluded from the chart scale.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasRows && (
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 rounded-md border border-civic-line px-2.5 py-1.5 text-xs font-medium text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel"
              aria-label="Export comparison data as CSV"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Export CSV
            </button>
          )}
          <span className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
            {isTransit ? transitPeriodLabel : comparisonYear}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div
          className="relative h-72 overflow-hidden rounded-md border border-civic-line bg-civic-subtle p-3"
          role={hasChartData ? "img" : undefined}
          aria-label={
            hasChartData
              ? `${getMetricLabel(metric)} bar chart for ${cohortDescription}. ${
                  isTransit
                    ? snapshotDate === "Unknown"
                      ? "Transit snapshot date unavailable."
                      : `Transit snapshot packaged ${snapshotDate}.`
                    : `Data year ${comparisonYear}.`
                } Exact values are available in the adjacent table.`
              : undefined
          }
        >
          {loading && !hasChartData ? (
            <div className="flex h-full flex-col items-center justify-center gap-2">
              <div className="skeleton h-4 w-48" />
              <div className="flex w-full items-end justify-center gap-3 pt-4">
                {[0.6, 0.85, 0.45, 0.7, 0.55].map((h, i) => (
                  <div key={i} className="skeleton w-10" style={{ height: `${h * 140}px` }} />
                ))}
              </div>
            </div>
          ) : !hasChartData ? (
            <div className="grid h-full place-items-center text-sm text-civic-muted">
              {lowConfidenceCount > 0
                ? "Chart omitted because the available growth values are low confidence. Exact values remain in the table."
                : "No comparison data available."}
            </div>
          ) : (
            <ResponsiveContainer
              width="100%"
              height="100%"
              onResize={() => setChartTooltipActive(false)}
            >
              <BarChart
                data={chartData}
                margin={{ top: 8, right: 8, bottom: 8, left: 12 }}
                onMouseMove={() => setChartTooltipActive(true)}
                onMouseLeave={() => setChartTooltipActive(false)}
              >
                <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "var(--chart-label)" }} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 12, fill: "var(--chart-label)" }}
                  tickFormatter={(value: number) => formatAxisMetric(metric, value)}
                  tickLine={false}
                  width={62}
                />
                <Tooltip
                  active={chartTooltipActive}
                  content={(tooltipProps) => (
                    <ComparisonChartTooltip
                      active={tooltipProps.active}
                      payload={tooltipProps.payload}
                      metric={metric}
                    />
                  )}
                  isAnimationActive={false}
                  position={{ x: 8, y: 8 }}
                  wrapperStyle={{
                    maxWidth: "calc(100% - 16px)",
                    pointerEvents: "none"
                  }}
                />
                <Bar
                  dataKey="value"
                  fill={COMPARISON_BAR_COLOR}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={64}
                >
                  <LabelList
                    dataKey="value"
                    position="top"
                    formatter={(v: number) => formatMetric(metric, v)}
                    style={{ fontSize: 11, fill: "var(--chart-label)" }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="overflow-x-auto rounded-md border border-civic-line">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">
              {isTransit
                ? `${getMetricLabel(metric)} values for ${cohortDescription} from the transit snapshot${
                    snapshotDate === "Unknown"
                      ? " (date unavailable)"
                      : ` packaged ${snapshotDate}`
                  }`
                : `${getMetricLabel(metric)} values for ${cohortDescription} in ${comparisonYear}`}
              {missingCount > 0
                ? `. ${missingCount} ${missingCount === 1 ? "area has" : "areas have"} no available value.`
                : "."}
              {lowConfidenceCount > 0
                ? ` ${lowConfidenceCount} low-confidence growth ${lowConfidenceCount === 1 ? "value is" : "values are"} excluded from the chart scale.`
                : ""}
            </caption>
            <thead className="bg-civic-subtle text-left text-xs uppercase tracking-wide text-civic-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-semibold">Area</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-semibold">{getMetricLabel(metric)}</th>
                {showsRentRatio && <th scope="col" className="px-3 py-2 text-right font-semibold">Ratio</th>}
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((item) => {
                const source = comparison?.items.find((i) => i.geoid === item.geoid);
                return (
                  <tr key={item.geoid} className="border-t border-civic-line">
                    <td className="px-3 py-2 font-medium text-civic-ink">{source?.name}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-civic-ink">
                      {formatMetric(metric, item.rawValue)}
                      {item.lowConfidence && (
                        <span className="ml-2 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                          Low confidence — very small 2016 base
                        </span>
                      )}
                    </td>
                    {showsRentRatio && (
                      <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-civic-muted">
                        {formatMetric("rent_to_income_ratio", source?.metrics.rent_to_income_ratio)}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const COMPACT_NUMBER_FORMATTER = new Intl.NumberFormat("en-CA", {
  notation: "compact",
  maximumFractionDigits: 1
});

function formatAxisMetric(metric: MetricKey, value: number): string {
  const formatted = formatMetric(metric, value);
  if (formatted.endsWith("%")) return formatted;
  if (Math.abs(value) < 1_000) return formatted;
  const compact = COMPACT_NUMBER_FORMATTER.format(value);
  return formatted.startsWith("$") ? `$${compact}` : compact;
}

function ComparisonChartTooltip({
  active,
  payload,
  metric
}: {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: { fullName?: string; rawValue?: number };
  }>;
  metric: MetricKey;
}) {
  const datum = payload?.[0]?.payload;
  if (!active || !datum || typeof datum.rawValue !== "number") return null;

  return (
    <div
      className="w-max whitespace-normal rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs text-civic-ink shadow-panel"
      style={{ maxWidth: "min(16rem, calc(100vw - 4rem))" }}
    >
      <p className="break-words font-semibold leading-5">{datum.fullName}</p>
      <p className="mt-0.5 leading-5 text-civic-muted">
        {getMetricLabel(metric)}: <span className="tabular-nums text-civic-ink">{formatMetric(metric, datum.rawValue)}</span>
      </p>
    </div>
  );
}

function chartLabel(name: string, type: string, geoid: string) {
  if (type === "census_tract") {
    const tractName = name.match(/census tract (.+)$/i)?.[1] ?? geoid;
    return `CT ${tractName}`;
  }
  return name.replace(" County", "");
}
