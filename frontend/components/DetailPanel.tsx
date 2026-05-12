"use client";

import { MapPin, X } from "lucide-react";

import { formatMetric, isCmhcMetric } from "@/lib/api";
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
          {/* Census Profile */}
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
              Census Profile (2021)
            </h3>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <MetricLine label="Income" value={formatMetric("median_income", metrics?.median_income)} />
              <MetricLine label="Rent" value={formatMetric("median_rent", metrics?.median_rent)} />
              <MetricLine label="Burden" value={formatMetric("rent_burden_pct", metrics?.rent_burden_pct)} />
              <MetricLine label="Growth" value={formatMetric("population_growth_pct", metrics?.population_growth_pct)} />
              <MetricLine label="Population" value={formatMetric("population", metrics?.population)} />
              <MetricLine label="Index" value={formatMetric("affordability_index", metrics?.affordability_index)} />
            </div>
          </div>

          {/* CMHC Rental Market */}
          {cmhcMetrics ? (
            <>
              <CmhcRentalSection cmhcMetrics={cmhcMetrics} cmhcYear={cmhcYear} geographyLevel={geographyLevel} />

              {/* CMHC Housing Supply — only for municipalities with count data */}
              {cmhcMetrics.housing_starts_total !== null && (
                <div className="mt-4">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
                    CMHC Housing Supply {cmhcYear ? `(${cmhcYear})` : ""}
                  </h3>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <MetricLine label="Starts" value={formatMetric("housing_starts_total", cmhcMetrics.housing_starts_total)} />
                    <MetricLine label="Completions" value={formatMetric("housing_completions", cmhcMetrics.housing_completions)} />
                    <MetricLine label="Under const." value={formatMetric("units_under_construction", cmhcMetrics.units_under_construction)} />
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
              No CMHC data available for this geography.
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

const rentalMetrics: Array<{ key: keyof CmhcMetricValues; metricKey: MetricKey; label: string }> = [
  { key: "vacancy_rate", metricKey: "vacancy_rate", label: "Vacancy" },
  { key: "availability_rate", metricKey: "availability_rate", label: "Availability" },
  { key: "average_rent_total", metricKey: "average_rent_total", label: "Avg rent" },
  { key: "turnover_rate", metricKey: "turnover_rate", label: "Turnover" },
  { key: "average_rent_bachelor", metricKey: "average_rent_bachelor", label: "Bachelor" },
  { key: "average_rent_1br", metricKey: "average_rent_1br", label: "1BR" },
  { key: "average_rent_2br", metricKey: "average_rent_2br", label: "2BR" },
  { key: "average_rent_3br_plus", metricKey: "average_rent_3br_plus", label: "3BR+" },
  { key: "rental_universe", metricKey: "rental_universe", label: "Universe" },
];

function CmhcRentalSection({ cmhcMetrics, cmhcYear, geographyLevel }: { cmhcMetrics: CmhcMetricValues; cmhcYear?: number; geographyLevel: GeographyLevel }) {
  const available = rentalMetrics.filter((m) => cmhcMetrics[m.key] !== null && cmhcMetrics[m.key] !== undefined);

  return (
    <div className="mt-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
        CMHC Rental Market {cmhcYear ? `(${cmhcYear})` : ""}
        {geographyLevel === "census_tract" && (
          <span className="ml-1 font-normal normal-case text-civic-muted">· municipal rates</span>
        )}
      </h3>
      {available.length > 0 ? (
        <div className="grid grid-cols-2 gap-2 text-sm">
          {available.map((m) => (
            <MetricLine key={m.key} label={m.label} value={formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-civic-muted">No rental market data for this year.</p>
      )}
    </div>
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
