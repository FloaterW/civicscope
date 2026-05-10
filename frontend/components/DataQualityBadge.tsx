"use client";

import { BadgeCheck } from "lucide-react";

import type { GeographyLevel } from "@/types";

type Props = {
  geographyLevel: GeographyLevel;
};

const qualityCopy: Record<
  GeographyLevel,
  { label: string; tone: string; icon: typeof BadgeCheck }
> = {
  municipality: {
    label: "Official municipal metrics",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-900",
    icon: BadgeCheck
  },
  census_tract: {
    label: "Official tract metrics",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-900",
    icon: BadgeCheck
  }
};

export function DataQualityBadge({ geographyLevel }: Props) {
  const quality = qualityCopy[geographyLevel];
  const Icon = quality.icon;

  return (
    <div
      data-testid="data-quality-badge"
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${quality.tone}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {quality.label}
    </div>
  );
}
