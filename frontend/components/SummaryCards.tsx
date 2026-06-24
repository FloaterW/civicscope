"use client";

import { Gauge, Home, Percent, TrendingUp, Users, WalletCards } from "lucide-react";
import { useMemo } from "react";

import { formatMetric } from "@/lib/api";
import type { GeographyLevel, Summary } from "@/types";
import { MetricTooltip } from "./MetricTooltip";

type Props = {
  summary: Summary | null;
  geographyLevel: GeographyLevel;
  loading: boolean;
};

const summaryNouns: Record<GeographyLevel, string> = {
  municipality: "GTA municipalities",
  census_tract: "GTA census tracts"
};

function Skeleton({ className }: { className?: string }) {
  return <div className={`skeleton ${className ?? ""}`} />;
}

export function SummaryCards({ summary, geographyLevel, loading }: Props) {
  const regionCount = new Intl.NumberFormat("en-CA").format(summary?.region_count ?? 0);
  const heroCards = useMemo(() => [
    {
      label: "Rent burden",
      metricKey: "rent_burden_pct",
      value: formatMetric("rent_burden_pct", summary?.rent_burden_pct),
      icon: Percent
    },
    {
      label: "Affordability",
      metricKey: "affordability_index",
      value: formatMetric("affordability_index", summary?.affordability_index),
      icon: Gauge
    }
  ], [summary]);
  const subCards = useMemo(() => [
    {
      label: "Median income",
      metricKey: "median_income",
      value: formatMetric("median_income", summary?.median_income),
      icon: WalletCards
    },
    {
      label: "Median rent",
      metricKey: "median_rent",
      value: formatMetric("median_rent", summary?.median_rent),
      icon: Home
    },
    {
      label: "Rent-to-income",
      metricKey: "rent_to_income_ratio",
      value: formatMetric("rent_to_income_ratio", summary?.rent_to_income_ratio),
      icon: TrendingUp
    },
    {
      label: "Population",
      metricKey: "population",
      value: formatMetric("population", summary?.population),
      icon: Users
    }
  ], [summary]);

  return (
    <section
      data-testid="summary-panel"
      className="animate-fade-in rounded-lg border border-civic-line bg-civic-panel p-4 shadow-panel"
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
      <div className="grid grid-cols-2 gap-2">
        {[...heroCards, ...subCards].map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="rounded-md border border-civic-line border-l-[3px] border-l-civic-teal bg-civic-subtle p-3"
            >
              <div className="flex items-center gap-1.5 text-xs font-medium text-civic-muted">
                <Icon className="h-3.5 w-3.5 shrink-0 text-civic-teal" aria-hidden="true" />
                {card.label}
                <MetricTooltip metricKey={card.metricKey} />
              </div>
              <div className="mt-1 min-h-6 text-lg font-semibold text-civic-ink">
                {loading ? <Skeleton className="h-6 w-16" /> : card.value}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
