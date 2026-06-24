"use client";

import { BadgeCheck } from "lucide-react";

import type { GeographyLevel } from "@/types";

type Props = {
  geographyLevel: GeographyLevel;
  dataQualityLabel?: string;
  metricStatus?: "official" | "estimated" | "mixed" | "zone";
};

const qualityCopy: Record<
  GeographyLevel,
  { label: string; tone: string; icon: typeof BadgeCheck }
> = {
  municipality: {
    label: "Official municipal metrics",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    icon: BadgeCheck
  },
  census_tract: {
    label: "Official tract metrics",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    icon: BadgeCheck
  }
};

const estimatedTone = "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300";
const zoneTone = "border-teal-200 bg-teal-50 text-teal-900 dark:border-teal-800 dark:bg-teal-950 dark:text-teal-300";

export function DataQualityBadge({ geographyLevel, dataQualityLabel, metricStatus }: Props) {
  const quality = qualityCopy[geographyLevel];
  const Icon = quality.icon;
  const label = dataQualityLabel ?? quality.label;
  const tone =
    metricStatus === "zone" ? zoneTone :
    metricStatus === "estimated" || metricStatus === "mixed" ? estimatedTone : quality.tone;

  return (
    <div
      data-testid="data-quality-badge"
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${tone}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </div>
  );
}
