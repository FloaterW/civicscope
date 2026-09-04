"use client";

import { Calendar } from "lucide-react";

type Props = {
  value: number;
  availableYears: number[];
  disabled: boolean;
  label?: string;
  onChange: (year: number) => void;
};

export function YearSelector({
  value,
  availableYears,
  disabled,
  label = "CMHC data year",
  onChange
}: Props) {
  return (
    <div className="flex min-h-11 items-center gap-2 rounded-md border border-civic-line bg-civic-panel p-1 shadow-panel transition focus-within:border-civic-teal">
      <Calendar className="ml-2 h-4 w-4 text-civic-muted" aria-hidden="true" />
      <select
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        disabled={disabled}
        className="h-9 rounded border-0 bg-civic-panel px-1 text-sm font-medium text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel disabled:cursor-not-allowed disabled:text-civic-muted disabled:opacity-50"
        aria-label={label}
      >
        {availableYears.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </div>
  );
}
