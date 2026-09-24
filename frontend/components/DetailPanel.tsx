"use client";

import { Download, MapPin, MousePointerClick, X } from "lucide-react";
import { Children, createContext, isValidElement, useCallback, useContext, type ReactNode } from "react";

import { formatMetric, getMetricLabel, isCmhcMetric } from "@/lib/api";
import { buildGeographyExportRows, rowsToCsv } from "@/lib/csv-export";
import type { ResaleViewState } from "@/lib/dashboard-url";
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
import { TrrebResaleSection } from "./TrrebResaleSection";

type Props = {
  resaleView: ResaleViewState;
  onResaleViewChange: (view: ResaleViewState) => void;
  geography: Geography | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  cmhcMetrics?: CmhcMetricValues | null;
  cmhcLoading?: boolean;
  cmhcError?: boolean;
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
    "Explore household income, rent and affordability from the 2021 Census Profile.",
  census_tract:
    "Explore 2021 Census Profile metrics. Estimated and unavailable tract values are labeled."
};

const cmhcCopy: Record<GeographyLevel, string> = {
  municipality:
    "Explore CMHC rental-market and construction data. Each topic shows its own reference period.",
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
const SelectedMetric = createContext<MetricKey>("rent_burden_pct");

function metricTopic(metric: MetricKey): string {
  if (metric === "population" || metric === "population_growth_pct") return "population";
  if (TRANSIT_METRIC_KEYS.has(metric)) return "transit";
  if (metric.startsWith("housing_") || metric === "units_under_construction" || metric === "unabsorbed_units") return "construction";
  return isCmhcMetric(metric) ? "rental" : "census";
}

// Sort the actual DOM, not just the visual order, so keyboard navigation follows the page.
function TopicSections({ children }: { children: ReactNode }) {
  const activeTopic = metricTopic(useContext(SelectedMetric));
  const priority = (child: ReactNode) => isValidElement<{ topic: string }>(child) && child.props.topic === activeTopic ? 0 : 1;
  return <div className="mt-4 space-y-3">{Children.toArray(children).sort((a, b) => priority(a) - priority(b))}</div>;
}

function TopicSection({ topic, title, period, children }: { topic: string; title: string; period?: string; children: ReactNode }) {
  const active = metricTopic(useContext(SelectedMetric)) === topic;
  return (
    <details open={active} data-topic={topic} data-active-topic={active || undefined} className="group border-t border-civic-line pt-3">
      <summary className="cursor-pointer rounded-sm text-sm font-semibold text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal">
        {title}
        {period && <span className="ml-2 text-xs font-normal text-civic-muted"> {period}</span>}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

export function DetailPanel({ resaleView, onResaleViewChange, geography, metric, geographyLevel, cmhcMetrics, cmhcLoading = false, cmhcError = false, cmhcYear, dataQualityLabel, metricStatus, transitSnapshot, onClear }: Props) {
  const metrics = geography?.metrics;
  const quality = metrics?.data_quality;

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
  return (
    <SelectedMetric.Provider value={metric}>
    <section
      data-testid="detail-panel"
      className={`rounded-lg border border-civic-line bg-civic-panel p-4 shadow-panel ${geography ? "xl:flex xl:h-full xl:min-h-0 xl:flex-col xl:overflow-hidden" : ""}`}
    >
      <div data-testid="detail-panel-header" className="flex shrink-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-civic-teal">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {geography ? "Selected Geography" : "Explore the map"}
          </div>
          <h2 className="mt-1 text-lg font-semibold text-civic-ink">
            {geography?.name ?? "GTA overview"}
          </h2>
          {geography && <p className="text-xs text-civic-muted">
            {`${geography.type === "census_tract" ? "Census tract" : "Municipality"} - ${geography.geoid}`}
          </p>}
          {geography && <div className="mt-2">
            <DataQualityBadge geographyLevel={geographyLevel} dataQualityLabel={dataQualityLabel} metricStatus={metricStatus} />
          </div>}
        </div>
        {geography && (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-civic-line px-2.5 text-xs font-medium text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink"
              aria-label="Export geography data as CSV"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              CSV
            </button>
            <button
              type="button"
              onClick={onClear}
              className="grid h-9 w-9 place-items-center rounded-md border border-civic-line text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink"
              aria-label="Clear selected geography"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {geography ? (
        <div
          key={`${geography.geoid}:${metric}`}
          data-testid="detail-panel-scroll"
          role="region"
          aria-label="Selected geography statistics"
          tabIndex={0}
          className="rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-civic-teal xl:min-h-0 xl:flex-1 xl:overflow-y-auto xl:overscroll-contain xl:[scrollbar-gutter:stable]"
        >
        <TopicSections key={`${geography.geoid}:${metric}`}>
          {/* Census Profile */}
          <TopicSection topic="census" title="Household & housing profile" period="2021 Census">
            <div data-section="census" className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
              <MetricLine label="Median household income" value={formatMetric("median_income", metrics?.median_income)} status={quality?.median_income} metricKey="median_income" />
              <MetricLine label="Median rent" value={formatMetric("median_rent", metrics?.median_rent)} status={quality?.median_rent} metricKey="median_rent" />
              <MetricLine label="Rent burden" value={formatMetric("rent_burden_pct", metrics?.rent_burden_pct)} status={quality?.rent_burden_pct} metricKey="rent_burden_pct" />
              <MetricLine label="Affordability index" value={formatMetric("affordability_index", metrics?.affordability_index)} status={quality?.affordability_index} metricKey="affordability_index" />
            </div>
            {quality?.rent_burden_pct === "estimated" && (
              <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-400">
                Rent burden estimated from median rent and income (Statistics Canada value suppressed for this tract).
              </p>
            )}
          </TopicSection>
          <TopicSection topic="population" title="Population & growth" period="2021 Census">
            <div className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
              <MetricLine label="Population" value={formatMetric("population", metrics?.population)} status={quality?.population} metricKey="population" />
              <MetricLine label="Population growth" value={formatMetric("population_growth_pct", metrics?.population_growth_pct)} status={quality?.population_growth_pct} metricKey="population_growth_pct" />
            </div>
            <p className="mt-2 text-xs leading-5 text-civic-muted">Growth compares the 2016 and 2021 Census populations; it is not an annual growth rate.</p>
            {quality?.population_growth_pct === "low_confidence" && (
              <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-400">
                Population growth computed off a very small 2016 base; treat the percentage with caution.
              </p>
            )}
          </TopicSection>

          {/* Dwelling Type & Tenure */}
          {metrics?.dwellings_total != null && (
            <TopicSection topic="stock" title="Dwelling types & tenure" period="2021 Census"><HousingStockSection metrics={metrics} /></TopicSection>
          )}

          {/* CMHC Rental Market */}
          {process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_TRREB_PREVIEW_ENABLED === "1" && geographyLevel === "municipality" && (
            <TrrebResaleSection geoid={geography.geoid} view={resaleView} onViewChange={onResaleViewChange} />
          )}
          <TopicSection topic="rental" title="Rental market" period={cmhcYear ? `Oct ${cmhcYear} · CMHC` : "CMHC"}>
              {cmhcLoading || cmhcError ? (
                <p role="status" className="text-sm text-civic-muted">{cmhcLoading ? "Loading rental data…" : "Rental data could not be loaded. Use Retry above."}</p>
              ) : cmhcMetrics ? (
                <CmhcRentalSection cmhcMetrics={cmhcMetrics} cmhcYear={cmhcYear} geographyLevel={geographyLevel} />
              ) : metricTopic(metric) === "rental" ? (
                <MetricLine label={getMetricLabel(metric)} value="Not available" metricKey={metric} sourceLabel="No rental value for this area/year" />
              ) : (
                <div className="mt-4 rounded-md border border-dashed border-civic-line bg-civic-subtle p-3 text-xs leading-5 text-civic-muted">
                  No CMHC rental value is available for this area and year.
                </div>
              )}
          </TopicSection>
          <TopicSection topic="construction" title="Housing construction" period={cmhcYear ? String(cmhcYear) : "CMHC"}>
              {cmhcLoading || cmhcError ? (
                <p role="status" className="text-sm text-civic-muted">{cmhcLoading ? "Loading construction data…" : "Construction data could not be loaded. Use Retry above."}</p>
              ) : cmhcMetrics ? (
                <div>
                  <div className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
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
                    <MetricLine label="Under construction" value={formatMetric("units_under_construction", cmhcMetrics.units_under_construction)} cmhcSource={geographyLevel === "census_tract" && cmhcMetrics.units_under_construction != null ? "estimated" : undefined} metricKey="units_under_construction" />
                    <MetricLine label="Unabsorbed" value={formatMetric("unabsorbed_units", cmhcMetrics.unabsorbed_units)} cmhcSource={geographyLevel === "census_tract" && cmhcMetrics.unabsorbed_units != null ? "estimated" : undefined} metricKey="unabsorbed_units" />
                  </div>
                  <p className="mt-2 text-xs leading-5 text-civic-muted">Starts and completions are calendar-year totals. Under construction and unabsorbed are December snapshots.</p>
                  {geographyLevel === "census_tract" && (
                    <p className="mt-2 text-xs leading-5 text-civic-muted">
                      &quot;CMHC tract data&quot; = real published census-tract values. &quot;est. (CMHC parent
                      tract)&quot; = allocated from CMHC&apos;s real parent tract (a 2016 tract that split in
                      2021). &quot;est.&quot; = allocated from the parent municipality where CMHC has no tract
                      figure.
                    </p>
                  )}
                </div>
              ) : metricTopic(metric) === "construction" ? (
                <MetricLine label={getMetricLabel(metric)} value="Not available" metricKey={metric} sourceLabel="No construction value for this area/year" />
              ) : (
            <div className="mt-4 rounded-md border border-dashed border-civic-line bg-civic-subtle p-3 text-xs leading-5 text-civic-muted">
              {geographyLevel === "census_tract"
                ? "No CMHC value is available for this tract and year."
                : "No CMHC survey coverage for this municipality."}
            </div>
              )}
          </TopicSection>

          {/* Transit Accessibility */}
          {geographyLevel === "census_tract" && metrics && (
            <TopicSection topic="transit" title="Transit accessibility" period="GTFS snapshot">
              <div className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
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
            </TopicSection>
          )}

          <TopicSection topic="sources" title="Boundary & source details">
            <p className="text-xs leading-5 text-civic-muted">{geography.geometry_source}</p>
            <p className="mt-2 text-xs leading-5 text-civic-muted">Census and CMHC measure different periods and housing samples. Expand a topic to see its own reference period. CSV exports include the core Census, rental, construction and transit metrics, including collapsed topics; dwelling-type and tenure breakdowns are not included.</p>
          </TopicSection>
        </TopicSections>
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
    </SelectedMetric.Provider>
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
  const selectedMetric = useContext(SelectedMetric);
  const marketFields = rentalMarketMetrics.filter((m) => cmhcMetrics[m.key] != null || m.metricKey === selectedMetric);
  const unitFields = rentByUnitMetrics.filter((m) => cmhcMetrics[m.key] != null);
  const hasUniverse = cmhcMetrics.rental_universe != null;

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs leading-5 text-civic-muted">Historical survey rents, not current listing prices. CMHC covers purpose-built rentals, including existing tenants; it does not represent every home available to rent.</p>
      <p className="mb-2 text-xs leading-5 text-civic-muted">
        {cmhcYear ? `October ${cmhcYear} Rental Market Survey. ` : "Rental Market Survey. "}
        {
          geographyLevel === "census_tract"
            ? cmhcMetrics.vacancy_rate_source === "survey_zone" || cmhcMetrics.average_rent_total_source === "survey_zone"
              ? "survey-zone vacancy and average rent; other fields use parent municipality"
              : "parent-municipality values"
            : cmhcMetrics.survey_zone
              ? "shared survey-zone values"
              : undefined
        }
      </p>
      {marketFields.length > 0 || hasUniverse ? (
        <div className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
          {marketFields.map((m) => (
            <MetricLine key={m.key} label={m.label} value={cmhcMetrics[m.key] == null ? "Not published" : formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} metricKey={m.metricKey}
              sourceLabel={cmhcMetrics[m.key] == null ? "Unavailable for this area/year" : geographyLevel === "census_tract" ? ((m.key === "vacancy_rate" ? cmhcMetrics.vacancy_rate_source : m.key === "average_rent_total" ? cmhcMetrics.average_rent_total_source : cmhcMetrics.other_rms_source) === "survey_zone" ? "Survey zone" : "Parent municipality") : undefined} />
          ))}
          {hasUniverse && (
            <MetricLine
              label={cmhcMetrics.allocated ? "Rental universe (est.)" : "Rental universe"}
              value={formatMetric("rental_universe", cmhcMetrics.rental_universe)}
              metricKey="rental_universe"
            />
          )}
        </div>
      ) : (
        <p className="text-xs text-civic-muted">{cmhcMetrics.rms_surveyed ? "Rental figures are suppressed or not published for this area and year." : "Not surveyed by CMHC Rental Market Survey."}</p>
      )}
      {unitFields.length > 0 && (
        <div className="mt-2 grid auto-rows-fr grid-cols-2 gap-2 text-sm">
          {unitFields.map((m) => (
            <MetricLine key={m.key} label={m.label} value={formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} sourceLabel={geographyLevel === "census_tract" ? "Parent municipality" : undefined} />
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
          Zone values are used only when published for the selected year. Other rental
          values use the labeled parent-municipality fallback; counts may be allocated estimates.
        </p>
      )}
    </div>
  );
}

function pct(part: number | null | undefined, total: number | null | undefined): string {
  if (part == null || total == null || total === 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
}

function completeTotal(...values: Array<number | null | undefined>): number | null {
  // A suppressed component is unknown, not zero; do not manufacture a percentage.
  return values.some((value) => value == null) ? null : values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
}

function HousingStockSection({ metrics }: { metrics: MetricValues }) {
  const total = metrics.dwellings_total;
  if (total == null) return null;

  const groundOriented = completeTotal(metrics.dwellings_single_detached, metrics.dwellings_semi_detached, metrics.dwellings_row_house);
  const apartment = completeTotal(metrics.dwellings_apt_high_rise, metrics.dwellings_apt_low_rise, metrics.dwellings_apt_duplex);

  const occupied = completeTotal(metrics.owner_households, metrics.renter_households);
  const ownerPct = pct(metrics.owner_households, occupied || null);
  const renterPct = pct(metrics.renter_households, occupied || null);

  return (
    <div className="mt-4">
      <div className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
        <MetricLine label="Total dwellings" value={total.toLocaleString("en-CA")} />
        <MetricLine label="Owner" value={ownerPct} />
        <MetricLine label="Renter" value={renterPct} />
      </div>
      <div className="mt-2 grid auto-rows-fr grid-cols-2 gap-2 text-sm">
        <MetricLine label="Single-detached" value={pct(metrics.dwellings_single_detached, total)} />
        <MetricLine label="Semi-detached" value={pct(metrics.dwellings_semi_detached, total)} />
        <MetricLine label="Row house" value={pct(metrics.dwellings_row_house, total)} />
        <MetricLine label="Apt. 5+ storeys" value={pct(metrics.dwellings_apt_high_rise, total)} />
        <MetricLine label="Apt. <5 storeys" value={pct(metrics.dwellings_apt_low_rise, total)} />
        <MetricLine label="Apt. in duplex" value={pct(metrics.dwellings_apt_duplex, total)} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <MetricLine label="Ground-oriented" value={groundOriented == null ? "Not available" : `${pct(groundOriented, total)} (${groundOriented.toLocaleString("en-CA")})`} />
        <MetricLine label="Apartment" value={apartment == null ? "Not available" : `${pct(apartment, total)} (${apartment.toLocaleString("en-CA")})`} />
      </div>
    </div>
  );
}

function MetricLine({
  label,
  value,
  status,
  cmhcSource,
  sourceLabel,
  metricKey
}: {
  label: string;
  value: string;
  status?: MetricFieldStatus;
  cmhcSource?: CmhcCountSource;
  sourceLabel?: string;
  metricKey?: string;
}) {
  const selected = useContext(SelectedMetric) === metricKey;
  return (
    <div data-metric={metricKey} data-selected-metric={selected || undefined} className={`flex min-h-24 min-w-0 flex-col rounded-md border px-3 py-3 ${selected ? "border-civic-teal bg-[var(--civic-accent-subtle)]" : "border-civic-line bg-civic-panel"}`}>
      <span className="flex items-center gap-1 text-xs text-civic-muted">
        {label}
        {metricKey && <MetricTooltip metricKey={metricKey} />}
      </span>
      {selected && <span className="sr-only">Selected map metric</span>}
      <span className="mt-auto block pt-2 text-lg font-semibold tabular-nums text-civic-ink">
        {value}
        {status === "estimated" && (
          <span
            data-testid="estimated-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Estimated fallback; Statistics Canada value suppressed."
          >
            est.
          </span>
        )}
        {status === "derived" && (
          <span
            data-testid="derived-flag"
            className="ml-1 align-middle text-xs font-medium text-indigo-600 dark:text-indigo-300"
            title="Calculated from published source values; not separately published by the source agency."
          >
            derived
          </span>
        )}
        {status === "low_confidence" && (
          <span
            data-testid="low-confidence-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-700 dark:text-amber-400"
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
            className="ml-1 align-middle text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Allocated from CMHC's real parent tract (a 2016 tract that split in 2021); a closer estimate than the municipal allocation, but still an estimate."
          >
            est. (CMHC parent tract)
          </span>
        )}
        {cmhcSource === "estimated" && (
          <span
            data-testid="cmhc-estimated-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Estimated by allocating the parent municipality's total by renter-household share."
          >
            est.
          </span>
        )}
      </span>
      <span aria-hidden={sourceLabel ? undefined : true} className="block min-h-4 text-[11px] text-civic-muted">{sourceLabel}</span>
    </div>
  );
}

function cmhcSourceFor(
  source: CmhcCountSource | undefined,
  geographyLevel: GeographyLevel
): CmhcCountSource | undefined {
  return geographyLevel === "census_tract" ? source : undefined;
}
