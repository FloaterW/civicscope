"use client";

import { Calendar } from "lucide-react";
import { SelectControl } from "./SelectControl";

type Props = {
  id?: string;
  value: number;
  availableYears: number[];
  disabled: boolean;
  label?: string;
  onChange: (year: number) => void;
};

export function YearSelector({
  id,
  value,
  availableYears,
  disabled,
  label = "CMHC data year",
  onChange
}: Props) {
  return (
    <SelectControl id={id} label={label} value={value} onChange={value => onChange(Number(value))} disabled={disabled}
      icon={<Calendar className="ml-2 h-4 w-4 shrink-0 text-civic-muted" aria-hidden="true" />}>
        {availableYears.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
    </SelectControl>
  );
}
