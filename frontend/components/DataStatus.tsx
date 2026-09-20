"use client";
import { useEffect, useState } from "react";
import { fetchJson } from "@/lib/api";

type Source = { source: string; observation_year: number | null; last_checked_at: string | null; check_status: string; packaged_at: string | null; coverage: string | null };
export function DataStatus() {
  const [sources, setSources] = useState<Source[] | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchJson<{ sources: Source[] }>("/api/data-status", controller.signal)
      .then((data) => { if (!controller.signal.aborted) setSources(data.sources); })
      .catch(() => { /* Status failures must not interrupt exploration. */ });
    return () => controller.abort();
  }, []);
  return <details>
    <summary className="cursor-pointer text-civic-teal">Data dates and update status</summary>
    {sources ? <ul className="mt-2 space-y-1">
      {sources.map((source) => <li key={source.source}>
        <span className="font-semibold">{source.source === "cmhc" ? "CMHC" : source.source === "census" ? "Census" : "Transit"}</span>
        {source.observation_year ? ` · latest observation year ${source.observation_year}` : " · scheduled-route snapshot"}
        {source.last_checked_at ? ` · source checked ${new Date(source.last_checked_at).toLocaleDateString("en-CA", { timeZone: "UTC" })}${source.check_status === "overdue" ? " (check overdue)" : ""}` : " · source check date not recorded"}
        {source.coverage ? ` · ${source.coverage} coverage` : ""}
        {source.packaged_at ? ` · packaged ${new Date(source.packaged_at).toLocaleDateString("en-CA", { timeZone: "UTC" })}` : ""}
      </li>)}
    </ul> : <p>Update status is currently unavailable.</p>}
    <p>Source checks refer to verified packaged files; they do not change the year the figures describe. CMHC checks cover municipality and tract files, not the separately maintained survey-zone snapshot.</p>
  </details>;
}
