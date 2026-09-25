"use client";

import { useEffect, useId, useState } from "react";
import { fetchJson } from "@/lib/api";
import type { ResaleViewState } from "@/lib/dashboard-url";
import { TRREB_MODE } from "@/lib/trreb-mode";

type Resale = {
  geoid: string; source_area: string; period: string; period_type: "month" | "year";
  median_price: number | null; sales: number | null; property_days: number | null;
  source_url: string; source_page: number; geography_note: string; vintage_note: string;
  warnings: Array<{ area: string; field: string }>;
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const RESALE_ENDPOINT = TRREB_MODE === "archive" ? "/api/trreb-archive/resale" : TRREB_MODE === "public" ? "/api/trreb/resale" : "/api/trreb-preview";
const format = (value: number | null, currency = false) => value == null ? "Not reported" :
  new Intl.NumberFormat("en-CA", currency ? { style: "currency", currency: "CAD", maximumFractionDigits: 0 } : {}).format(value);

export function TrrebResaleSection({ geoid, view, onViewChange }: { geoid: string; view: ResaleViewState; onViewChange: (view: ResaleViewState) => void }) {
  const id = useId();
  const { expanded, year, month } = view;
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Resale; error?: boolean } | null>(null);
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
  return <details open={expanded} data-topic="resale" className="border-t border-civic-line pt-3">
    <summary onClick={event => {
      // A native toggle event is deferred and can be lost to an immediate
      // navigation. Commit state and the share URL in the activation itself.
      // Summary's native Enter/Space activation also dispatches this click.
      event.preventDefault();
      onViewChange({ ...view, expanded: !expanded });
    }} className="cursor-pointer text-sm font-semibold text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal">
      Resale market — TRREB <span className="ml-2 text-xs font-normal text-civic-muted">{TRREB_MODE !== "preview" ? "Archive · 2020–2025" : "Local preview"}</span>
    </summary>
    {expanded && <div className="mt-3 space-y-3">
      <p className="text-xs leading-5 text-civic-muted">MLS® resale transactions · All home types. Separate from Census and CMHC rental statistics.</p>
      <p className="text-xs leading-5 text-civic-muted">TRREB reporting area; equivalence to the selected Census boundary is not certified. No census-tract allocation.</p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor={`${id}-year`} className="text-xs text-civic-muted">Report year</label>
          <select id={`${id}-year`} value={year} onChange={event => onViewChange({ ...view, year: Number(event.target.value) })} className="mt-1 w-full rounded-md border border-civic-line bg-civic-surface p-2 text-sm text-civic-ink">
            {[2025,2024,2023,2022,2021,2020].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-period`} className="text-xs text-civic-muted">Reporting period</label>
          <select id={`${id}-period`} value={month ?? ""} onChange={event => onViewChange({ ...view, month: event.target.value ? Number(event.target.value) : undefined })} className="mt-1 w-full rounded-md border border-civic-line bg-civic-surface p-2 text-sm text-civic-ink">
            <option value="">Full year</option>
            {MONTHS.map((name,index) => <option key={name} value={index+1}>{name}</option>)}
          </select>
        </div>
      </div>
      {!current ? <p role="status" className="text-sm text-civic-muted">Loading resale statistics…</p> : current.error ?
        <div role="status" className="text-sm text-civic-muted">Resale statistics are unavailable. <button className="underline" onClick={() => setRetry(value => value+1)}>Retry resale statistics</button></div> : data && <>
          <p className="text-xs font-medium text-civic-ink">{data.source_area} · {month ? `${MONTHS[Number(month)-1]} ${year}` : `January–December ${year}`}</p>
          <dl className="grid auto-rows-fr grid-cols-2 gap-2 text-sm">
            {[["Median sale price",format(data.median_price,true)],["Sales",format(data.sales)],["Property days on market",format(data.property_days)]].map(([label,value]) =>
              <div key={label} className={`rounded-md border border-civic-line p-3 ${label === "Median sale price" ? "col-span-2" : ""}`}><dt className="text-xs text-civic-muted">{label}</dt><dd className="mt-2 font-semibold text-civic-ink">{value}</dd></div>)}
          </dl>
          <p className="text-xs leading-5 text-civic-muted">Days on market includes qualifying re-listings of the same property. Annual medians come directly from year-end tables, not averages of monthly medians.</p>
          {data.warnings.length > 0 && <p role="note" className="text-xs leading-5 text-amber-700 dark:text-amber-400">This report’s regional totals do not fully reconcile with its municipal rows. Published values are preserved; totals have not been redistributed.</p>}
          <details className="text-xs text-civic-muted"><summary className="cursor-pointer">Source and interpretation</summary>
            <p className="mt-2 leading-5">{data.geography_note} {data.vintage_note}</p>
          </details>
          <p className="text-xs leading-5 text-civic-muted">Source: Toronto Regional Real Estate Board, <a className="underline" href={data.source_url} target="_blank" rel="noreferrer">Market Watch, page {data.source_page}<span className="sr-only"> (opens in a new tab)</span></a>. {TRREB_MODE !== "preview" ? "Archived 2020–2025 reports; not current market quotes." : "Local preview; public display disabled."} TRREB statistics are not included in CSV downloads.</p>
        </>}
    </div>}
  </details>;
}
