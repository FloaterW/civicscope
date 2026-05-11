"use client";

import { Calendar } from "lucide-react";

type Props = {
  value: number;
  availableYears: number[];
  disabled: boolean;
  onChange: (year: number) => void;
};

export function YearSelector({ value, availableYears, disabled, onChange }: Props) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-civic-line bg-white p-1 shadow-panel">
      <Calendar className="ml-2 h-4 w-4 text-civic-muted" aria-hidden="true" />
      <select
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        disabled={disabled}
        className="h-8 rounded border-0 bg-white px-1 text-sm font-medium text-civic-ink outline-none disabled:cursor-not-allowed disabled:text-civic-muted disabled:opacity-50"
        aria-label="Data year"
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
