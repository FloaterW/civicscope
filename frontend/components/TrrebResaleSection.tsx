"use client";

import { CalendarRange } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { fetchJson } from "@/lib/api";
import type { ResaleViewState } from "@/lib/dashboard-url";
import { TRREB_MODE } from "@/lib/trreb-mode";
import { SelectControl } from "./SelectControl";
import { StatisticCard } from "./StatisticCard";
import { YearSelector } from "./YearSelector";

type Resale = {
  geoid: string; source_area: string; period: string; period_type: "month" | "year";
  median_price: number | null; sales: number | null; property_days: number | null;
  source_url: string; source_page: number; geography_note: string; vintage_note: string;
  warnings: Array<{ area: string; field: string }>;
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const YEARS = [2025, 2024, 2023, 2022, 2021, 2020];
const RESALE_ENDPOINT = TRREB_MODE === "archive" ? "/api/trreb-archive/resale" : TRREB_MODE === "public" ? "/api/trreb/resale" : "/api/trreb-preview";
const format = (value: number | null, currency = false) => value == null ? "Not reported" :
  new Intl.NumberFormat("en-CA", currency ? { style: "currency", currency: "CAD", maximumFractionDigits: 0 } : {}).format(value);

export function TrrebResaleSection({ geoid, view, onViewChange }: { geoid: string; view: ResaleViewState; onViewChange: (view: ResaleViewState) => void }) {
  const id = useId();
  const { expanded, year, month } = view;
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Resale; error?: boolean } | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [loadedHeight, setLoadedHeight] = useState(0);
  const key = `${geoid}:${year}:${month}:${retry}`;
  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController();
    fetchJson<Resale>(`${RESALE_ENDPOINT}/${encodeURIComponent(geoid)}?year=${year}${month ? `&month=${month}` : ""}`, controller.signal, 15000, TRREB_MODE === "archive" ? "same-origin" : "api")
      .then(data => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(() => { if (!controller.signal.aborted) setResult({ key, error: true }); });
    return () => controller.abort();
  }, [expanded, geoid, year, month, key]);
  const current = result?.key === key ? result : null;
  const data = current?.data;
  // Keep the last loaded footprint during requests/errors, including expanded
  // source notes. This prevents the scroll container clamping its scrollTop.
  // Measure the inner content, not the reserved outer box, to avoid a sizing loop.
  useLayoutEffect(() => {
    const content = contentRef.current;
    if (!data || !expanded || !content) return;
    const observer = new ResizeObserver(() => setLoadedHeight(content.getBoundingClientRect().height));
    observer.observe(content);
    return () => observer.disconnect();
  }, [data, expanded]);
  const periodLabel = month ? `${MONTHS[month - 1]} ${year}` : `January–December ${year}`;
  return <details open={expanded} data-topic="resale" className="border-t border-civic-line pt-3">
    <summary onClick={event => {
      // A native toggle event is deferred and can be lost to an immediate
      // navigation. Commit state and the share URL in the activation itself.
      // Summary's native Enter/Space activation also dispatches this click.
      event.preventDefault();
      onViewChange({ ...view, expanded: !expanded });
    }} className="cursor-pointer rounded-xs text-sm font-semibold text-civic-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-civic-teal">
      Resale market — TRREB <span className="ml-2 text-xs font-normal text-civic-muted">{TRREB_MODE !== "preview" ? "Archive · 2020–2025" : "Local preview"}</span>
    </summary>
    {expanded && <div className="mt-3 space-y-3">
      <p className="text-xs leading-5 text-civic-muted">All home types · MLS® resales in TRREB reporting areas, not Census boundaries. Separate from CMHC rents.</p>
      <div className="grid grid-cols-1 gap-2 min-[400px]:grid-cols-2">
        <div className="min-w-0">
          <label htmlFor={`${id}-year`} className="mb-1 block text-xs text-civic-muted">Report year</label>
          <YearSelector id={`${id}-year`} label="Report year" value={year} availableYears={YEARS} disabled={false} onChange={year => onViewChange({ ...view, year })} />
        </div>
        <div className="min-w-0">
          <label htmlFor={`${id}-period`} className="mb-1 block text-xs text-civic-muted">Reporting period</label>
          <SelectControl id={`${id}-period`} label="Reporting period" value={month ?? ""} onChange={value => onViewChange({ ...view, month: value ? Number(value) : undefined })}
            icon={<CalendarRange className="ml-2 h-4 w-4 shrink-0 text-civic-muted" aria-hidden="true" />}>
            <option value="">Full year</option>
            {MONTHS.map((name,index) => <option key={name} value={index+1}>{name}</option>)}
          </SelectControl>
        </div>
      </div>
      <div data-testid="resale-results" style={!data && loadedHeight ? { minHeight: loadedHeight } : undefined}>
        <div ref={contentRef} className="space-y-3">
          <p role="status" className="min-h-5 text-xs font-medium text-civic-ink">
            {!current ? `Loading resale statistics… ${periodLabel}` : current.error ? "Resale statistics are unavailable." : `${data?.source_area} · ${periodLabel}`}
          </p>
          <dl aria-busy={!current} className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
            <StatisticCard definition label="Median sale price" metricKey="trreb_median_price" className="col-span-2" value={data ? format(data.median_price, true) : "—"} />
            <StatisticCard definition label="Sales" metricKey="trreb_sales" value={data ? format(data.sales) : "—"} />
            <StatisticCard definition label="Days on market" metricKey="trreb_property_days" sourceLabel="Property-based" value={data ? format(data.property_days) : "—"} />
          </dl>
          {current?.error && <button type="button" className="inline-flex min-h-11 items-center rounded-md border border-civic-line bg-civic-panel px-3 text-sm font-medium text-civic-ink hover:bg-civic-subtle focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-civic-teal" onClick={() => setRetry(value => value + 1)}>Retry resale statistics</button>}
          {data && data.warnings.length > 0 && <p role="note" className="text-xs leading-5 text-amber-700 dark:text-amber-400">This report’s regional totals do not fully reconcile with its municipal rows. Published values are preserved; totals have not been redistributed.</p>}
          <p className="text-xs leading-5 text-civic-muted">Source: Toronto Regional Real Estate Board. {data ? <a className="rounded-xs underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-civic-teal" href={data.source_url} target="_blank" rel="noreferrer">Market Watch, page {data.source_page}<span className="sr-only"> (opens in a new tab)</span></a> : "Report link available when loaded."}</p>
          <details className="text-xs text-civic-muted"><summary className="cursor-pointer rounded-xs font-medium focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-civic-teal">Source and interpretation</summary>
            <div className="mt-2 space-y-2 leading-5">
              {data && <p>{data.geography_note} {data.vintage_note}</p>}
              <p>{TRREB_MODE !== "preview" ? "Archived 2020–2025 reports; not current market quotes." : "Local preview; public display disabled."} TRREB statistics are not included in CSV downloads.</p>
            </div>
          </details>
        </div>
      </div>
    </div>}
  </details>;
}
