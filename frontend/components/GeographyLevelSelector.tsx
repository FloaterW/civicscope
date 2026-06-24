"use client";

import { Layers } from "lucide-react";

import type { GeographyLevel } from "@/types";

type Props = {
  value: GeographyLevel;
  onChange: (level: GeographyLevel) => void;
};

const options: Array<{ value: GeographyLevel; label: string }> = [
  { value: "municipality", label: "Municipalities" },
  { value: "census_tract", label: "Census tracts" }
];

export function GeographyLevelSelector({ value, onChange }: Props) {
  return (
    <div
      className="flex items-center gap-1 rounded-md border border-civic-line bg-civic-panel p-1 shadow-panel"
      aria-label="Geography level"
    >
      <Layers className="ml-2 h-4 w-4 text-civic-muted" aria-hidden="true" />
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`h-8 rounded px-3 text-sm font-medium transition ${
              isActive
                ? "bg-civic-teal text-white dark:text-slate-900"
                : "text-civic-muted hover:bg-civic-subtle hover:text-civic-ink"
            }`}
            aria-pressed={isActive}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
