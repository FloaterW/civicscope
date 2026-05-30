"use client";

import { BadgeCheck } from "lucide-react";

import type { GeographyLevel } from "@/types";

type Props = {
  geographyLevel: GeographyLevel;
  /** When supplied (from API metadata), overrides the default label. */
  dataQualityLabel?: string;
  /** "estimated"/"mixed" use amber tones instead of green to flag non-official values. */
  metricStatus?: "official" | "estimated" | "mixed";
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

const estimatedTone = "border-amber-200 bg-amber-50 text-amber-900";

export function DataQualityBadge({ geographyLevel, dataQualityLabel, metricStatus }: Props) {
  const quality = qualityCopy[geographyLevel];
  const Icon = quality.icon;
  const label = dataQualityLabel ?? quality.label;
  const tone =
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
