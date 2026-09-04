"use client";

import { Layers } from "lucide-react";

import type { GeographyLevel } from "@/types";

type Props = {
  value: GeographyLevel;
  onChange: (level: GeographyLevel) => void;
  disabled?: boolean;
  municipalityDisabled?: boolean;
};

const options: Array<{ value: GeographyLevel; label: string }> = [
  { value: "municipality", label: "Municipalities" },
  { value: "census_tract", label: "Census tracts" }
];

export function GeographyLevelSelector({
  value,
  onChange,
  disabled = false,
  municipalityDisabled = false
}: Props) {
  return (
    <div className="flex flex-col gap-1">
      <div
        className="flex min-h-11 items-center gap-1 rounded-md border border-civic-line bg-civic-panel p-1 shadow-panel"
        role="group"
        aria-label="Geography level"
      >
        <Layers className="ml-2 h-4 w-4 text-civic-muted" aria-hidden="true" />
        {options.map((option) => {
          const isActive = option.value === value;
          const isTransitDisabled = option.value === "municipality" && municipalityDisabled;
          const isDisabled = disabled || isTransitDisabled;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              disabled={isDisabled}
              aria-describedby={isTransitDisabled ? "transit-geography-note" : undefined}
              title={isTransitDisabled ? "Transit metrics are available by census tract" : undefined}
              className={`h-9 rounded px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel disabled:cursor-not-allowed disabled:opacity-50 ${
                isActive
                  ? "bg-civic-teal text-white dark:text-slate-900"
                  : "text-civic-muted hover:bg-civic-subtle hover:text-civic-ink disabled:hover:bg-transparent disabled:hover:text-civic-muted"
              }`}
              aria-pressed={isActive}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {municipalityDisabled && (
        <span id="transit-geography-note" className="px-1 text-[11px] text-civic-muted">
          Transit metrics use census tracts.
        </span>
      )}
    </div>
  );
}
