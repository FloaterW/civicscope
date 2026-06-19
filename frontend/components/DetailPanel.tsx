"use client";

import { MapPin, X } from "lucide-react";

import { formatMetric, isCmhcMetric } from "@/lib/api";
import type {
  CmhcMetricValues,
  Geography,
  GeographyLevel,
  MetricFieldStatus,
  MetricKey,
  MetricValues
} from "@/types";

import { DataQualityBadge } from "./DataQualityBadge";

type Props = {
  geography: Geography | null;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  cmhcMetrics?: CmhcMetricValues | null;
  cmhcYear?: number;
  dataQualityLabel?: string;
  metricStatus?: "official" | "estimated" | "mixed";
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
  const quality = metrics?.data_quality;
  const hasAnyRentalData = cmhcMetrics ? rentalMarketMetrics.some((m) => cmhcMetrics[m.key] != null) : false;
  const hasAnySupplyData =
    cmhcMetrics?.housing_starts_total != null ||
    cmhcMetrics?.housing_completions != null ||
    cmhcMetrics?.units_under_construction != null ||
    cmhcMetrics?.unabsorbed_units != null;

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
              ? `${geography.type === "census_tract" ? "Census tract" : "Municipality"} - ${geography.geoid}`
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
            <SectionHeader title="Household & Housing Profile" period="2021 Census" />
            <div className="grid grid-cols-3 gap-2 text-sm">
              <MetricLine label="Median household income" value={formatMetric("median_income", metrics?.median_income)} status={quality?.median_income} />
              <MetricLine label="Median rent" value={formatMetric("median_rent", metrics?.median_rent)} status={quality?.median_rent} />
              <MetricLine label="Rent burden" value={formatMetric("rent_burden_pct", metrics?.rent_burden_pct)} status={quality?.rent_burden_pct} />
              <MetricLine label="Pop. growth" value={formatMetric("population_growth_pct", metrics?.population_growth_pct)} status={quality?.population_growth_pct} />
              <MetricLine label="Population" value={formatMetric("population", metrics?.population)} status={quality?.population} />
              <MetricLine label="Affordability index" value={formatMetric("affordability_index", metrics?.affordability_index)} status={quality?.affordability_index} />
            </div>
            {quality?.rent_burden_pct === "estimated" && (
              <p className="mt-2 text-xs leading-5 text-amber-700">
                Rent burden estimated from median rent and income (Statistics Canada value suppressed for this tract).
              </p>
            )}
            {quality?.population_growth_pct === "low_confidence" && (
              <p className="mt-2 text-xs leading-5 text-amber-700">
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
                <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
                  {cmhcMetrics.rms_surveyed
                    ? "Rental market data suppressed for confidentiality in this survey zone."
                    : "Not covered by the CMHC Rental Market Survey."}
                </div>
              )}

              {hasAnySupplyData && (
                <div className="mt-4">
                  <SectionHeader
                    title="Housing Construction"
                    period={cmhcYear ? `${cmhcYear} YTD` : undefined}
                  />
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <MetricLine
                      label="Starts"
                      value={formatMetric("housing_starts_total", cmhcMetrics.housing_starts_total)}
                      status={cmhcSourceStatus(cmhcMetrics.starts_source, geographyLevel)}
                      cmhcOfficial={isCmhcOfficial(cmhcMetrics.starts_source, geographyLevel)}
                    />
                    <MetricLine
                      label="Completions"
                      value={formatMetric("housing_completions", cmhcMetrics.housing_completions)}
                      status={cmhcSourceStatus(cmhcMetrics.completions_source, geographyLevel)}
                      cmhcOfficial={isCmhcOfficial(cmhcMetrics.completions_source, geographyLevel)}
                    />
                    <MetricLine label="Under const." value={formatMetric("units_under_construction", cmhcMetrics.units_under_construction)} status={geographyLevel === "census_tract" ? "estimated" : undefined} />
                    <MetricLine label="Unabsorbed" value={formatMetric("unabsorbed_units", cmhcMetrics.unabsorbed_units)} status={geographyLevel === "census_tract" ? "estimated" : undefined} />
                  </div>
                  {geographyLevel === "census_tract" && (
                    <p className="mt-2 text-xs leading-5 text-civic-muted">
                      Starts & completions marked “CMHC tract data” are real published census-tract
                      values; “est.” values are allocated from the parent municipality where CMHC has
                      no tract figure.
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="mt-4 rounded-md border border-dashed border-civic-line bg-slate-50 p-3 text-xs leading-5 text-civic-muted">
              {geographyLevel === "census_tract"
                ? "CMHC does not publish census tract-level data. Estimated values allocated from parent municipality."
                : "No CMHC survey coverage for this municipality."}
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
        note={cmhcMetrics.allocated ? "municipal rates" : undefined}
      />
      {marketFields.length > 0 ? (
        <div className="grid grid-cols-2 gap-2 text-sm">
          {marketFields.map((m) => (
            <MetricLine key={m.key} label={m.label} value={formatMetric(m.metricKey, cmhcMetrics[m.key] as number)} />
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
  cmhcOfficial
}: {
  label: string;
  value: string;
  /** Census field-level provenance. "official" intentionally renders NO badge
   * (the default, clean state). */
  status?: MetricFieldStatus;
  /** Set only for CMHC SCSS count metrics whose value is a real published
   * census-tract figure — renders the distinct "CMHC tract data" badge. */
  cmhcOfficial?: boolean;
}) {
  return (
    <div className="rounded-md border border-civic-line bg-white px-3 py-2">
      <span className="block text-xs text-civic-muted">{label}</span>
      <span className="mt-1 block text-base font-semibold text-civic-ink">
        {value}
        {status === "estimated" && (
          <span
            data-testid="estimated-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600"
            title="Estimated fallback; Statistics Canada value suppressed."
          >
            est.
          </span>
        )}
        {status === "low_confidence" && (
          <span
            data-testid="low-confidence-flag"
            className="ml-1 align-middle text-xs font-medium text-amber-600"
            title="Derived off a very small base population; low confidence."
          >
            ⚠
          </span>
        )}
        {cmhcOfficial && (
          <span
            data-testid="official-flag"
            className="ml-1 align-middle text-xs font-medium text-emerald-600"
            title="Real CMHC census-tract value (Starts & Completions Survey)."
          >
            CMHC tract data
          </span>
        )}
      </span>
    </div>
  );
}

/** Whether a CMHC count metric's value is a real published census-tract figure
 * (so the "CMHC tract data" badge should show). Only in census-tract mode. */
function isCmhcOfficial(
  source: "official" | "estimated" | undefined,
  geographyLevel: GeographyLevel
): boolean {
  return geographyLevel === "census_tract" && source === "official";
}

/** Whether a CMHC count metric is an allocation estimate (show "est."). */
function cmhcSourceStatus(
  source: "official" | "estimated" | undefined,
  geographyLevel: GeographyLevel
): MetricFieldStatus | undefined {
  if (geographyLevel !== "census_tract") return undefined;
  if (source === "estimated") return "estimated";
  return undefined;
}
