"use client";

import { Download } from "lucide-react";
import { useCallback, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { formatMetric, getMetricLabel, isCmhcMetric } from "@/lib/api";
import { rowsToCsv } from "@/lib/csv-export";
import { rampColorForValue } from "@/lib/colors";
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
  const comparisonRows =
    comparison?.items
      .map((item) => {
        const allMetrics = { ...item.metrics, ...item.cmhc_metrics } as Record<string, unknown>;
        const raw = allMetrics[metric];
        const rawValue = typeof raw === "number" ? raw : null;
        return {
          geoid: item.geoid,
          name: chartLabel(item.name, item.type, item.geoid),
          fullName: item.name,
          value: rawValue,
          rawValue,
        };
      }) ?? [];
  const chartData = comparisonRows.filter(
    (item): item is typeof item & { value: number; rawValue: number } => item.value !== null
  );
  const hasChartData = chartData.length > 0;
  const hasRows = comparisonRows.length > 0;
  const missingCount = comparisonRows.length - chartData.length;
  const values = chartData.map((d) => d.value as number);
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 0;

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
      ...(isCmhc ? [] : ["Rent-to-income ratio"])
    ]];
    for (const item of comparison.items) {
      const allMetrics = { ...item.metrics, ...item.cmhc_metrics } as Record<string, unknown>;
      const val = allMetrics[metric];
      const row = [
        item.name,
        item.geoid,
        val != null ? String(val) : "",
        val != null ? "available" : "unavailable",
        ...(isTransit
          ? [
              transitSnapshot?.coverage_status ?? "unknown",
              transitAgencyNames(transitSnapshot?.included_agencies),
              transitAgencyNames(transitSnapshot?.missing_agencies),
              transitSnapshotDate(transitSnapshot)
            ]
          : []),
        ...(isCmhc ? [] : [item.metrics.rent_to_income_ratio != null ? String(item.metrics.rent_to_income_ratio) : ""])
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
  }, [comparison, metric, geographyLevel, isCmhc, isTransit, transitSnapshot]);

  return (
    <div data-testid="comparison-panel" className="p-4">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-civic-ink">Comparison</h2>
          <p className="text-xs text-civic-muted">
            {getMetricLabel(metric)} across {isUserSelection ? `selected ${geographyLevel === "municipality" ? "municipalities" : "census tracts"}` : defaultComparisonNouns[geographyLevel]}
          </p>
          {missingCount > 0 && (
            <p className="mt-1 text-xs text-civic-muted">
              {missingCount} {missingCount === 1 ? "area is" : "areas are"} listed as Not available.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasRows && (
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 rounded-md border border-civic-line px-2.5 py-1.5 text-xs font-medium text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink"
              aria-label="Export comparison data as CSV"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Export CSV
            </button>
          )}
          <span className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
            {displayYear ?? comparison?.year ?? "2021"}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="h-72 rounded-md border border-civic-line bg-civic-subtle p-3">
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
              No comparison data available.
            </div>
          ) : (
            <ResponsiveContainer
              width="100%"
              height="100%"
              onResize={() => setChartTooltipActive(false)}
            >
              <BarChart
                data={chartData}
                margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
                onMouseMove={() => setChartTooltipActive(true)}
                onMouseLeave={() => setChartTooltipActive(false)}
              >
                <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "var(--chart-label)" }} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: "var(--chart-label)" }} tickLine={false} width={54} />
                <Tooltip
                  active={chartTooltipActive}
                  formatter={(value, _name, item) => [
                    formatMetric(metric, item.payload.rawValue),
                    getMetricLabel(metric)
                  ]}
                  contentStyle={{
                    background: "var(--civic-panel)",
                    border: "1px solid var(--civic-line)",
                    borderRadius: "6px",
                    color: "var(--civic-ink)"
                  }}
                  labelStyle={{ color: "var(--civic-ink)" }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={64}>
                  {chartData.map((item) => (
                    <Cell
                      key={item.geoid}
                      fill={rampColorForValue(item.value as number, minValue, maxValue, metric)}
                    />
                  ))}
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

        <div className="overflow-hidden rounded-md border border-civic-line">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-civic-subtle text-left text-xs uppercase tracking-wide text-civic-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Area</th>
                <th className="px-3 py-2 font-semibold">{getMetricLabel(metric)}</th>
                {!isCmhc && <th className="px-3 py-2 font-semibold">Ratio</th>}
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((item) => {
                const source = comparison?.items.find((i) => i.geoid === item.geoid);
                return (
                  <tr key={item.geoid} className="border-t border-civic-line">
                    <td className="px-3 py-2 font-medium text-civic-ink">{source?.name}</td>
                    <td className="px-3 py-2 text-civic-ink">
                      {formatMetric(metric, item.rawValue)}
                    </td>
                    {!isCmhc && (
                      <td className="px-3 py-2 text-civic-muted">
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

function chartLabel(name: string, type: string, geoid: string) {
  if (type === "census_tract") {
    const tractName = name.match(/census tract (.+)$/i)?.[1] ?? geoid;
    return `CT ${tractName}`;
  }
  return name.replace(" County", "");
}
