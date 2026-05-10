"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { formatMetric, getMetricLabel } from "@/lib/api";
import type { CompareResponse, MetricKey } from "@/types";

type Props = {
  comparison: CompareResponse | null;
  metric: MetricKey;
  loading: boolean;
};

export function ComparisonPanel({ comparison, metric, loading }: Props) {
  const chartData =
    comparison?.items.map((item) => ({
      geoid: item.geoid,
      name: item.name.replace(" County", ""),
      value: item.metrics[metric] ?? 0,
      rawValue: item.metrics[metric]
    })) ?? [];
  const hasChartData = chartData.length > 0;

  return (
    <div data-testid="comparison-panel" className="p-4">
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-civic-ink">Comparison</h2>
          <p className="text-xs text-civic-muted">
            {getMetricLabel(metric)} across selected municipalities
          </p>
        </div>
        <span className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
          {comparison?.year ?? "2022"}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="h-72 rounded-md border border-civic-line bg-slate-50 p-3">
          {loading && !hasChartData ? (
            <div className="grid h-full place-items-center text-sm text-civic-muted">
              Loading comparison...
            </div>
          ) : !hasChartData ? (
            <div className="grid h-full place-items-center text-sm text-civic-muted">
              No comparison data available.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                <CartesianGrid stroke="#d8dee6" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} tickLine={false} />
                <YAxis tick={{ fontSize: 12 }} tickLine={false} width={54} />
                <Tooltip
                  formatter={(value, _name, item) => [
                    formatMetric(metric, item.payload.rawValue),
                    getMetricLabel(metric)
                  ]}
                  labelStyle={{ color: "#18212f" }}
                />
                <Bar dataKey="value" fill="#117c78" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="overflow-hidden rounded-md border border-civic-line">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-slate-100 text-left text-xs uppercase tracking-wide text-civic-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Area</th>
                <th className="px-3 py-2 font-semibold">{getMetricLabel(metric)}</th>
                <th className="px-3 py-2 font-semibold">Ratio</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((item, index) => {
                const source = comparison?.items[index];
                return (
                  <tr key={item.geoid} className="border-t border-civic-line">
                    <td className="px-3 py-2 font-medium text-civic-ink">{source?.name}</td>
                    <td className="px-3 py-2 text-civic-ink">
                      {formatMetric(metric, source?.metrics[metric])}
                    </td>
                    <td className="px-3 py-2 text-civic-muted">
                      {formatMetric("rent_to_income_ratio", source?.metrics.rent_to_income_ratio)}
                    </td>
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
