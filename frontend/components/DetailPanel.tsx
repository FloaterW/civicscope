"use client";

import { Download, MapPin, MousePointerClick, X } from "lucide-react";
import { useCallback } from "react";

import { formatMetric, isCmhcMetric } from "@/lib/api";
import { buildGeographyExportRows, rowsToCsv } from "@/lib/csv-export";
import {
  transitAgencyNames,
  transitCoverageLabel,
  transitSnapshotDate
} from "@/lib/transit";
import type {
  CmhcCountSource,
  CmhcMetricValues,
  Geography,
  GeographyLevel,
  MetricFieldStatus,
  MetricKey,
  MetricValues,
  TransitSnapshot
} from "@/types";

import { DataQualityBadge } from "./DataQualityBadge";
import { MetricTooltip } from "./MetricTooltip";

type Props = {
  geography: Geography | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  cmhcMetrics?: CmhcMetricValues | null;
  cmhcYear?: number;
  dataQualityLabel?: string;
  metricStatus?: "official" | "derived" | "estimated" | "mixed" | "zone";
  transitSnapshot?: TransitSnapshot;
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
    "The map shows CMHC survey-zone values, published tract construction counts, and clearly labeled fallbacks. Select a tract to inspect the source of each value."
};

const transitCopy: Record<GeographyLevel, string> = {
  municipality:
    "Transit scores are available at the census tract level. Switch to tract view to see transit accessibility.",
  census_tract:
    "The map shows GTA census tracts scored by transit accessibility using the disclosed packaged GTFS snapshot."
};

const TRANSIT_METRIC_KEYS = new Set(["transit_score", "transit_route_count"]);

export function DetailPanel({ geography, metric, geographyLevel, cmhcMetrics, cmhcYear, dataQualityLabel, metricStatus, transitSnapshot, onClear }: Props) {
  const metrics = geography?.metrics;
  const quality = metrics?.data_quality;
  const hasAnyRentalData = cmhcMetrics ? rentalMarketMetrics.some((m) => cmhcMetrics[m.key] != null) : false;

  const handleExportCsv = useCallback(() => {
    if (!geography || !metrics) return;
    const csv = rowsToCsv(
      buildGeographyExportRows(geographyLevel, metrics, cmhcMetrics, cmhcYear, transitSnapshot)
    );
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `civicscope-${geography.geoid}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 100);
  }, [geography, geographyLevel, metrics, cmhcMetrics, cmhcYear, transitSnapshot]);
  const hasAnySupplyData =
    cmhcMetrics?.housing_starts_total != null ||
    cmhcMetrics?.housing_completions != null ||
    cmhcMetrics?.units_under_construction != null ||
    cmhcMetrics?.unabsorbed_units != null;

  return (
    <section
      data-testid="detail-panel"
      className="rounded-lg border border-civic-line bg-civic-panel p-4 shadow-panel"
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
              ? `${geography.type === "census_tract" ? "Census tract" : "Municipality"} - ${geography.geoid}`
              : emptyCopy[geographyLevel]}
          </p>
          <div className="mt-2">
            <DataQualityBadge geographyLevel={geographyLevel} dataQualityLabel={dataQualityLabel} metricStatus={metricStatus} />
          </div>
        </div>
        {geography && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 rounded-md border border-civic-line px-2.5 py-1.5 text-xs font-medium text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink"
              aria-label="Export geography data as CSV"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              CSV
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded-md border border-civic-line p-2 text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink"
              aria-label="Clear selected geography"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {geography ? (
        <div className="animate-fade-in">
          {/* Census Profile */}
          <div className="mt-4" data-section="census">
            <SectionHeader title="Household & Housing Profile" period="2021 Census" />
            <div className="grid grid-cols-3 gap-2 text-sm">
              <MetricLine label="Median household income" value={formatMetric("median_income", metrics?.median_income)} status={quality?.median_income} metricKey="median_income" />
              <MetricLine label="Median rent" value={formatMetric("median_rent", metrics?.median_rent)} status={quality?.median_rent} metricKey="median_rent" />
              <MetricLine label="Rent burden" value={formatMetric("rent_burden_pct", metrics?.rent_burden_pct)} status={quality?.rent_burden_pct} metricKey="rent_burden_pct" />
              <MetricLine label="Pop. growth" value={formatMetric("population_growth_pct", metrics?.population_growth_pct)} status={quality?.population_growth_pct} metricKey="population_growth_pct" />
              <MetricLine label="Population" value={formatMetric("population", metrics?.population)} status={quality?.population} metricKey="population" />
              <MetricLine label="Affordability index" value={formatMetric("affordability_index", metrics?.affordability_index)} status={quality?.affordability_index} metricKey="affordability_index" />
            </div>
            {quality?.rent_burden_pct === "estimated" && (
              <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-400">
                Rent burden estimated from median rent and income (Statistics Canada value suppressed for this tract).
              </p>
            )}
            {quality?.population_growth_pct === "low_confidence" && (
              <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-400">
                Population growth computed off a very small 2016 base; treat the percentage with caution.
              </p>
            )}
          </div>

          {/* Dwelling Type & Tenure */}
          {metrics?.dwellings_total != null && (
            <HousingStockSection metrics={metrics} />
          )}

          {/* CMHC Rental Market */}
          {cmhcMetrics && (hasAnyRentalData || hasAnySupplyData) ? (
            <>
              {hasAnyRentalData ? (
                <CmhcRentalSection cmhcMetrics={cmhcMetrics} cmhcYear={cmhcYear} geographyLevel={geographyLevel} />
              ) : (
                <div className="mt-4 rounded-md border border-dashed border-civic-line bg-civic-subtle p-3 text-xs leading-5 text-civic-muted">
                  {cmhcMetrics.rms_surveyed
                    ? "Rental market data suppressed for confidentiality in this survey zone."
                    : "Not covered by the CMHC Rental Market Survey."}
                </div>
              )}

              {hasAnySupplyData && (
                <div className="mt-4">
                  <SectionHeader
                    title="Housing Construction"
                    period={cmhcYear ? `Calendar year ${cmhcYear}` : undefined}
                  />
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <MetricLine
                      label="Starts"
                      value={formatMetric("housing_starts_total", cmhcMetrics.housing_starts_total)}
                      cmhcSource={cmhcSourceFor(cmhcMetrics.starts_source, geographyLevel)}
                      metricKey="housing_starts_total"
                    />
                    <MetricLine
                      label="Completions"
                      value={formatMetric("housing_completions", cmhcMetrics.housing_completions)}
                      cmhcSource={cmhcSourceFor(cmhcMetrics.completions_source, geographyLevel)}
                      metricKey="housing_completions"
                    />
                    <MetricLine label="Under const." value={formatMetric("units_under_construction", cmhcMetrics.units_under_construction)} status={geographyLevel === "census_tract" ? "estimated" : undefined} />
                    <MetricLine label="Unabsorbed" value={formatMetric("unabsorbed_units", cmhcMetrics.unabsorbed_units)} status={geographyLevel === "census_tract" ? "estimated" : undefined} />
                  </div>
                  {geographyLevel === "census_tract" && (
                    <p className="mt-2 text-xs leading-5 text-civic-muted">
                      &quot;CMHC tract data&quot; = real published census-tract values. &quot;est. (CMHC parent
                      tract)&quot; = allocated from CMHC&apos;s real parent tract (a 2016 tract that split in
                      2021). &quot;est.&quot; = allocated from the parent municipality where CMHC has no tract
                      figure.
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="mt-4 rounded-md border border-dashed border-civic-line bg-civic-subtle p-3 text-xs leading-5 text-civic-muted">
              {geographyLevel === "census_tract"
                ? "No CMHC value is available for this tract and year."
                : "No CMHC survey coverage for this municipality."}
            </div>
          )}

          {/* Transit Accessibility */}
          {geographyLevel === "census_tract" && metrics && (
            <div className="mt-4">
              <SectionHeader title="Transit Accessibility" note="GTFS" />
              <div className="grid grid-cols-2 gap-2 text-sm">
                <MetricLine
                  label="Access score"
                  value={formatMetric("transit_score", metrics.transit_score)}
                  status={quality?.transit_score}
                  metricKey="transit_score"
                />
                <MetricLine
                  label="Routes nearby"
                  value={formatMetric("transit_route_count", metrics.transit_route_count)}
                  status={quality?.transit_route_count}
                  metricKey="transit_route_count"
                />
              </div>
              <p className="mt-2 text-xs leading-5 text-civic-muted">
                Unique transit routes within 800m of tract boundary. Score normalized 0-100 across GTA tracts.
              </p>
              <p data-testid="transit-detail-coverage" className="mt-2 text-xs leading-5 text-civic-ink">
                {transitCoverageLabel(transitSnapshot)}. Included: {transitAgencyNames(transitSnapshot?.included_agencies)}.
                {transitSnapshot?.missing_agencies.length
                  ? ` Not included: ${transitAgencyNames(transitSnapshot.missing_agencies)}.`
                  : ""} Snapshot date: {transitSnapshotDate(transitSnapshot)}.
              </p>
            </div>
          )}

          <div className="mt-4 rounded-md border border-dashed border-civic-line bg-civic-subtle p-3 text-xs leading-5 text-civic-muted">
            {geography.geometry_source}
          </div>
        </div>
      ) : (
        <div className="mt-6 flex flex-col items-center gap-3 py-4 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-civic-surface text-civic-muted">
            <MousePointerClick className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-medium text-civic-ink">{emptyCopy[geographyLevel]}</p>
            <p className="mt-1 max-w-xs text-xs leading-5 text-civic-muted">
              {TRANSIT_METRIC_KEYS.has(metric) ? transitCopy[geographyLevel] : isCmhcMetric(metric) ? cmhcCopy[geographyLevel] : censusCopy[geographyLevel]}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function SectionHeader({ title, period, note }: { title: string; period?: string; note?: string }) {
  return (
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
      {title}
      {period && <span className="ml-1 font-normal normal-case text-civic-muted">- {period}</span>}
      {note && <span className="ml-1 font-normal normal-case text-civic-muted">- {note}</span>}
    </h3>
  );
}

const rentalMarketMetrics: Array<{ key: keyof CmhcMetricValues; metricKey: MetricKey; label: string }> = [
  { key: "vacancy_rate", metricKey: "vacancy_rate", label: "Vacancy rate" },
  { key: "availability_rate", metricKey: "availability_rate", label: "Availability rate" },
  { key: "average_rent_total", metricKey: "average_rent_total", label: "Average rent" },
  { key: "turnover_rate", metricKey: "turnover_rate", label: "Turnover rate" },
];

const rentByUnitMetrics: Array<{ key: keyof CmhcMetricValues; metricKey: MetricKey; label: string }> = [
  { key: "average_rent_bachelor", metricKey: "average_rent_bachelor", label: "Bachelor" },
  { key: "average_rent_1br", metricKey: "average_rent_1br", label: "1-bedroom" },
  { key: "average_rent_2br", metricKey: "average_rent_2br", label: "2-bedroom" },
  { key: "average_rent_3br_plus", metricKey: "average_rent_3br_plus", label: "3-bedroom+" },
];

function CmhcRentalSection({ cmhcMetrics, cmhcYear, geographyLevel }: { cmhcMetrics: CmhcMetricValues; cmhcYear?: number; geographyLevel: GeographyLevel }) {
  const marketFields = rentalMarketMetrics.filter((m) => cmhcMetrics[m.key] != null);
  const unitFields = rentByUnitMetrics.filter((m) => cmhcMetrics[m.key] != null);
  const hasUniverse = cmhcMetrics.rental_universe != null;

  return (
    <div className="mt-4">
      <SectionHeader
        title="Rental Market"
        period={cmhcYear ? `Oct ${cmhcYear} RMS` : undefined}
        note={
          geographyLevel === "census_tract"
            ? cmhcMetrics.survey_zone
              ? "survey-zone vacancy and average rent; other fields use parent municipality"
              : "parent-municipality values"
            : cmhcMetrics.survey_zone
              ? "shared survey-zone values"
              : undefined
        }
      />
      {marketFields.length > 0 ? (
        <div className="grid grid-cols-2 gap-2 text-sm">
          {marketFields.map((m) => (
            <MetricLine key={m.key} label={m.label} value={formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} metricKey={m.metricKey} />
          ))}
          {hasUniverse && (
            <MetricLine
              label={cmhcMetrics.allocated ? "Rental universe (est.)" : "Rental universe"}
              value={formatMetric("rental_universe", cmhcMetrics.rental_universe)}
            />
          )}
        </div>
      ) : (
        <p className="text-xs text-civic-muted">Not surveyed by CMHC Rental Market Survey.</p>
      )}
      {unitFields.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          {unitFields.map((m) => (
            <MetricLine key={m.key} label={m.label} value={formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} />
          ))}
        </div>
      )}
      {geographyLevel === "municipality" && cmhcMetrics.survey_zone && marketFields.length > 0 && (
        <p data-testid="survey-zone-note" className="mt-2 text-xs leading-5 text-civic-muted">
          CMHC surveys this municipality as part of the <strong>{cmhcMetrics.survey_zone}</strong>{" "}
          rental market zone, so these rental values are shared across those municipalities
          (CMHC&apos;s survey granularity, not duplicated data).
        </p>
      )}
      {geographyLevel === "census_tract" && cmhcMetrics.survey_zone && marketFields.length > 0 && (
        <p data-testid="survey-zone-note" className="mt-2 text-xs leading-5 text-civic-muted">
          CMHC survey zone: <strong>{cmhcMetrics.survey_zone}</strong>.
          Vacancy rate and average rent reflect this zone&apos;s surveyed values; bedroom rents,
          availability, turnover, and counts use the labeled parent-municipality fallback.
        </p>
      )}
    </div>
  );
}

function pct(part: number | null | undefined, total: number | null | undefined): string {
  if (part == null || total == null || total === 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
}

function HousingStockSection({ metrics }: { metrics: MetricValues }) {
  const total = metrics.dwellings_total;
  if (total == null) return null;

  const groundOriented =
    (metrics.dwellings_single_detached ?? 0) +
    (metrics.dwellings_semi_detached ?? 0) +
    (metrics.dwellings_row_house ?? 0);
  const apartment =
    (metrics.dwellings_apt_high_rise ?? 0) +
    (metrics.dwellings_apt_low_rise ?? 0) +
    (metrics.dwellings_apt_duplex ?? 0);

  const occupied = (metrics.owner_households ?? 0) + (metrics.renter_households ?? 0);
  const ownerPct = pct(metrics.owner_households, occupied || null);
  const renterPct = pct(metrics.renter_households, occupied || null);

  return (
    <div className="mt-4">
      <SectionHeader title="Housing Stock" period="2021 Census" />
      <div className="grid grid-cols-3 gap-2 text-sm">
        <MetricLine label="Total dwellings" value={total.toLocaleString("en-CA")} />
        <MetricLine label="Owner" value={ownerPct} />
        <MetricLine label="Renter" value={renterPct} />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
        <MetricLine label="Single-detached" value={pct(metrics.dwellings_single_detached, total)} />
        <MetricLine label="Semi-detached" value={pct(metrics.dwellings_semi_detached, total)} />
        <MetricLine label="Row house" value={pct(metrics.dwellings_row_house, total)} />
        <MetricLine label="Apt. 5+ storeys" value={pct(metrics.dwellings_apt_high_rise, total)} />
        <MetricLine label="Apt. <5 storeys" value={pct(metrics.dwellings_apt_low_rise, total)} />
        <MetricLine label="Apt. in duplex" value={pct(metrics.dwellings_apt_duplex, total)} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <MetricLine label="Ground-oriented" value={`${pct(groundOriented, total)} (${groundOriented.toLocaleString("en-CA")})`} />
        <MetricLine label="Apartment" value={`${pct(apartment, total)} (${apartment.toLocaleString("en-CA")})`} />
      </div>
    </div>
  );
}

function MetricLine({
  label,
  value,
  status,
  cmhcSource,
  metricKey
}: {
  label: string;
  value: string;
  status?: MetricFieldStatus;
  cmhcSource?: CmhcCountSource;
  metricKey?: string;
}) {
  return (
    <div className="rounded-md border border-civic-line bg-civic-panel px-3 py-2">
      <span className="flex items-center gap-1 text-xs text-civic-muted">
        {label}
        {metricKey && <MetricTooltip metricKey={metricKey} />}
      </span>
      <span className="mt-1 block text-base font-semibold text-civic-ink">
        {value}
        {status === "estimated" && (
          <span
            data-testid="estimated-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600 dark:text-amber-400"
            title="Estimated fallback; Statistics Canada value suppressed."
          >
            est.
          </span>
        )}
        {status === "derived" && (
          <span
            data-testid="derived-flag"
            className="ml-1 align-middle text-xs font-medium text-indigo-600 dark:text-indigo-400"
            title="Calculated from published source values; not separately published by the source agency."
          >
            derived
          </span>
        )}
        {status === "low_confidence" && (
          <span
            data-testid="low-confidence-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600 dark:text-amber-400"
            title="Derived off a very small base population; low confidence."
          >
            &#x26A0;
          </span>
        )}
        {cmhcSource === "official" && (
          <span
            data-testid="official-flag"
            className="ml-1 align-middle text-xs font-medium text-emerald-600 dark:text-emerald-400"
            title="Real CMHC census-tract value (Starts & Completions Survey)."
          >
            CMHC tract data
          </span>
        )}
        {cmhcSource === "estimated_parent" && (
          <span
            data-testid="parent-est-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600 dark:text-amber-400"
            title="Allocated from CMHC's real parent tract (a 2016 tract that split in 2021); a closer estimate than the municipal allocation, but still an estimate."
          >
            est. (CMHC parent tract)
          </span>
        )}
        {cmhcSource === "estimated" && (
          <span
            data-testid="cmhc-estimated-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600 dark:text-amber-400"
            title="Estimated by allocating the parent municipality's total by renter-household share."
          >
            est.
          </span>
        )}
      </span>
    </div>
  );
}

function cmhcSourceFor(
  source: CmhcCountSource | undefined,
  geographyLevel: GeographyLevel
): CmhcCountSource | undefined {
  return geographyLevel === "census_tract" ? source : undefined;
}
