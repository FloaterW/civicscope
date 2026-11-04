import type { ReactNode } from "react";
import { MetricTooltip } from "./MetricTooltip";

/** Shared geometry and typography for Census, CMHC and resale statistics. */
export function StatisticCard({ label, value, metricKey, selected = false, sourceLabel, definition = false, className = "" }: {
  label: string;
  value: ReactNode;
  metricKey?: string;
  selected?: boolean;
  sourceLabel?: string;
  definition?: boolean;
  className?: string;
}) {
  const Label = definition ? "dt" : "div";
  const Value = definition ? "dd" : "div";
  return (
    <div data-metric={metricKey} data-selected-metric={selected || undefined} className={`flex min-h-24 min-w-0 flex-col rounded-md border px-3 py-3 ${selected ? "border-civic-teal bg-[var(--civic-accent-subtle)]" : "border-civic-line bg-civic-panel"} ${className}`}>
      {/* Reserve two label lines so independent statistic grids share geometry.
          Longer labels can still grow naturally at narrow widths or text zoom. */}
      <Label className="flex min-h-8 items-center gap-1 text-xs text-civic-muted">
        {label}
        {metricKey && <MetricTooltip metricKey={metricKey} />}
        {selected && <span className="sr-only">Selected map metric</span>}
      </Label>
      <Value className="mt-auto">
        <span className="block pt-2 text-lg font-semibold tabular-nums text-civic-ink">{value}</span>
        <span aria-hidden={sourceLabel ? undefined : true} className="block min-h-4 text-[11px] leading-4 text-civic-muted">{sourceLabel}</span>
      </Value>
    </div>
  );
}
