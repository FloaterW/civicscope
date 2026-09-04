import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";

import {
  transitAgencyNames,
  transitCoverageLabel,
  transitSnapshotDate
} from "@/lib/transit";
import type { TransitSnapshot } from "@/types";

export function TransitCoverageNotice({ snapshot }: { snapshot?: TransitSnapshot }) {
  const status = snapshot?.coverage_status ?? "unknown";
  const Icon =
    status === "complete" ? CheckCircle2 : status === "partial" ? AlertTriangle : CircleHelp;
  const tone =
    status === "complete"
      ? "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
      : status === "partial"
        ? "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
        : "border-slate-300 bg-slate-50 text-slate-950 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200";

  return (
    <div
      data-testid="transit-coverage-notice"
      role="status"
      className={`mt-2 max-w-3xl rounded-md border px-3 py-2 text-xs leading-5 ${tone}`}
    >
      <p className="flex items-center gap-1.5 font-semibold">
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        {transitCoverageLabel(snapshot)}
      </p>
      <p>Included agencies: {transitAgencyNames(snapshot?.included_agencies)}.</p>
      {snapshot?.missing_agencies.length ? (
        <p>Not included: {transitAgencyNames(snapshot.missing_agencies)}.</p>
      ) : null}
      <p>Snapshot date: {transitSnapshotDate(snapshot)}.</p>
    </div>
  );
}
