"use client";

import { Building2, Gauge, Home, KeyRound, Percent, TrendingUp, Users, WalletCards } from "lucide-react";
import { useMemo } from "react";

import { formatMetric } from "@/lib/api";
import type { GeographyLevel, Summary } from "@/types";

type Props = {
  summary: Summary | null;
  geographyLevel: GeographyLevel;
  loading: boolean;
};

const summaryNouns: Record<GeographyLevel, string> = {
  municipality: "GTA municipalities",
  census_tract: "GTA census tracts"
};

export function SummaryCards({ summary, geographyLevel, loading }: Props) {
  const regionCount = new Intl.NumberFormat("en-CA").format(summary?.region_count ?? 0);
  const cards = useMemo(() => [
    {
      label: "Median income",
      value: formatMetric("median_income", summary?.median_income),
      icon: WalletCards
    },
    {
      label: "Median rent",
      value: formatMetric("median_rent", summary?.median_rent),
      icon: Home
    },
    {
      label: "Rent-to-income",
      value: formatMetric("rent_to_income_ratio", summary?.rent_to_income_ratio),
      icon: TrendingUp
    },
    {
      label: "Population",
      value: formatMetric("population", summary?.population),
      icon: Users
    },
    {
      label: "Rent burden",
      value: formatMetric("rent_burden_pct", summary?.rent_burden_pct),
      icon: Percent
    },
    {
      label: "Affordability",
      value: formatMetric("affordability_index", summary?.affordability_index),
      icon: Gauge
    },
    ...(summary?.vacancy_rate !== undefined && summary?.vacancy_rate !== null
      ? [{ label: "Vacancy rate", value: formatMetric("vacancy_rate", summary.vacancy_rate), icon: KeyRound }]
      : []),
    ...(summary?.average_rent_total !== undefined && summary?.average_rent_total !== null
      ? [{ label: "Avg CMHC rent", value: formatMetric("average_rent_total", summary.average_rent_total), icon: Home }]
      : []),
    ...(summary?.housing_starts_total !== undefined && summary?.housing_starts_total !== null
      ? [{ label: "Housing starts", value: formatMetric("housing_starts_total", summary.housing_starts_total), icon: Building2 }]
      : []),
    ...(summary?.housing_completions !== undefined && summary?.housing_completions !== null
      ? [{ label: "Completions", value: formatMetric("housing_completions", summary.housing_completions), icon: Building2 }]
      : [])
  ], [summary]);

  return (
    <section
      data-testid="summary-panel"
      className="rounded-lg border border-civic-line bg-white p-4 shadow-panel"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-civic-ink">Summary</h2>
          <p className="text-xs text-civic-muted">
            {summary?.region_count === 1
              ? summary.selected_geographies[0]?.name
              : `${regionCount} ${summaryNouns[geographyLevel]}`}
          </p>
        </div>
        <span className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
          {summary?.year ?? "2021"}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-2">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="min-h-[78px] rounded-md border border-civic-line bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-xs font-medium text-civic-muted">
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {card.label}
              </div>
              <div className="mt-2 min-h-7 text-xl font-semibold text-civic-ink">
                {loading ? "..." : card.value}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
