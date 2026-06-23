"use client";

import { SlidersHorizontal } from "lucide-react";

import { metricOptions } from "@/lib/api";
import type { MetricKey } from "@/types";

type Props = {
  value: MetricKey;
  onChange: (metric: MetricKey) => void;
};

const groups = Array.from(
  new Map(metricOptions.map((option) => [option.group, option.group])).values()
);

export function MetricSelector({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-civic-line bg-civic-panel p-1 shadow-panel">
      <SlidersHorizontal className="ml-2 h-4 w-4 text-civic-muted" aria-hidden="true" />
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as MetricKey)}
        className="h-8 rounded border-0 bg-civic-panel px-1 text-sm font-medium text-civic-ink outline-none"
        aria-label="Map metric"
      >
        {groups.map((group) => (
          <optgroup key={group} label={group}>
            {metricOptions
              .filter((option) => option.group === group)
              .map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
