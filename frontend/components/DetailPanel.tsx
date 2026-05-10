"use client";

import { MapPin, X } from "lucide-react";

import { formatMetric, getMetricLabel } from "@/lib/api";
import type { Geography, GeographyLevel, MetricKey } from "@/types";

type Props = {
  geography: Geography | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  onClear: () => void;
};

const emptyCopy: Record<GeographyLevel, string> = {
  municipality: "Select a municipality on the map or with search",
  census_tract: "Select a census tract on the map or with search"
};

const overviewCopy: Record<GeographyLevel, string> = {
  municipality:
    "The map shows GTA municipalities with 2021 Census Profile affordability metrics when loaded. Select a geography to inspect local values.",
  census_tract:
    "The map shows official 2021 census tract boundaries with estimated tract metrics derived from parent municipalities. Select a tract to inspect local values."
};

export function DetailPanel({ geography, metric, geographyLevel, onClear }: Props) {
  const metrics = geography?.metrics;

  return (
    <section
      data-testid="detail-panel"
      className="rounded-lg border border-civic-line bg-white p-4 shadow-panel"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            Selected Geography
          </div>
          <h2 className="mt-1 text-lg font-semibold text-civic-ink">
            {geography?.name ?? "GTA overview"}
          </h2>
          <p className="text-xs text-civic-muted">
            {geography
              ? `${geography.type} ${geography.geoid}`
              : emptyCopy[geographyLevel]}
          </p>
        </div>
        {geography && (
          <button
            type="button"
            onClick={onClear}
            className="rounded-md border border-civic-line p-2 text-civic-muted hover:bg-slate-50 hover:text-civic-ink"
            aria-label="Clear selected geography"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {geography ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <MetricLine label={getMetricLabel(metric)} value={formatMetric(metric, metrics?.[metric])} />
            <MetricLine label="Income" value={formatMetric("median_income", metrics?.median_income)} />
            <MetricLine label="Rent" value={formatMetric("median_rent", metrics?.median_rent)} />
            <MetricLine label="Burden" value={formatMetric("rent_burden_pct", metrics?.rent_burden_pct)} />
            <MetricLine
              label="Growth"
              value={formatMetric("population_growth_pct", metrics?.population_growth_pct)}
            />
            <MetricLine
              label="Index"
              value={formatMetric("affordability_index", metrics?.affordability_index)}
            />
          </div>

          <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
            {geography.geometry_source}
          </div>
        </>
      ) : (
        <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
          {overviewCopy[geographyLevel]}
        </div>
      )}
    </section>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-civic-line bg-white px-3 py-2">
      <span className="block text-xs text-civic-muted">{label}</span>
      <span className="mt-1 block text-base font-semibold text-civic-ink">{value}</span>
    </div>
  );
}
