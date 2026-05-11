"use client";

import { MapPin, X } from "lucide-react";

import { formatMetric, getMetricLabel, isCmhcMetric } from "@/lib/api";
import type { CmhcMetricValues, Geography, GeographyLevel, MetricKey } from "@/types";

import { DataQualityBadge } from "./DataQualityBadge";

type Props = {
  geography: Geography | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  cmhcMetrics?: CmhcMetricValues | null;
  cmhcYear?: number;
  dataQualityLabel?: string;
  metricStatus?: "official" | "estimated";
  onClear: () => void;
};

const emptyCopy: Record<GeographyLevel, string> = {
  municipality: "Select a municipality on the map or with search",
  census_tract: "Select a census tract on the map or with search"
};

const censusCopy: Record<GeographyLevel, string> = {
  municipality:
    "The map shows GTA municipalities with 2021 Census Profile affordability metrics when loaded. Select a geography to inspect local values.",
  census_tract:
    "The map shows GTA census tracts with official 2021 Census Profile affordability metrics. Select a tract to inspect local values."
};

const cmhcCopy: Record<GeographyLevel, string> = {
  municipality:
    "The map shows GTA municipalities with CMHC Rental Market Survey data. Select a geography to inspect local values.",
  census_tract:
    "The map shows GTA census tracts with CMHC Rental Market Survey data (inherited from parent municipality). Select a tract to inspect local values."
};

export function DetailPanel({ geography, metric, geographyLevel, cmhcMetrics, cmhcYear, dataQualityLabel, metricStatus, onClear }: Props) {
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
              ? `${geography.type === "census_tract" ? "Census tract" : "Municipality"} · ${geography.geoid}`
              : emptyCopy[geographyLevel]}
          </p>
          <div className="mt-2">
            <DataQualityBadge geographyLevel={geographyLevel} dataQualityLabel={dataQualityLabel} metricStatus={metricStatus} />
          </div>
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
            <MetricLine label={getMetricLabel(metric)} value={formatMetric(metric, ({ ...metrics, ...cmhcMetrics } as Record<string, number | null | undefined>)[metric])} />
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

          {cmhcMetrics && (
            <div className="mt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
                CMHC Rental Market {cmhcYear ? `(${cmhcYear})` : ""}
              </h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <MetricLine label="Vacancy" value={formatMetric("vacancy_rate", cmhcMetrics.vacancy_rate)} />
                <MetricLine label="Availability" value={formatMetric("availability_rate", cmhcMetrics.availability_rate)} />
                <MetricLine label="Avg rent" value={formatMetric("average_rent_total", cmhcMetrics.average_rent_total)} />
                <MetricLine label="Turnover" value={formatMetric("turnover_rate", cmhcMetrics.turnover_rate)} />
                <MetricLine label="Bachelor" value={formatMetric("average_rent_bachelor", cmhcMetrics.average_rent_bachelor)} />
                <MetricLine label="1BR" value={formatMetric("average_rent_1br", cmhcMetrics.average_rent_1br)} />
                <MetricLine label="2BR" value={formatMetric("average_rent_2br", cmhcMetrics.average_rent_2br)} />
                <MetricLine label="3BR+" value={formatMetric("average_rent_3br_plus", cmhcMetrics.average_rent_3br_plus)} />
                <MetricLine label="Universe" value={formatMetric("rental_universe", cmhcMetrics.rental_universe)} />
                {cmhcMetrics.housing_starts_total !== null && (
                  <>
                    <MetricLine label="Starts" value={formatMetric("housing_starts_total", cmhcMetrics.housing_starts_total)} />
                    <MetricLine label="Completions" value={formatMetric("housing_completions", cmhcMetrics.housing_completions)} />
                    <MetricLine label="Under construction" value={formatMetric("units_under_construction", cmhcMetrics.units_under_construction)} />
                  </>
                )}
              </div>
            </div>
          )}

          <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
            {geography.geometry_source}
          </div>
        </>
      ) : (
        <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
          {isCmhcMetric(metric) ? cmhcCopy[geographyLevel] : censusCopy[geographyLevel]}
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
