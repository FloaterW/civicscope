import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DataQualityBadge } from "@/components/DataQualityBadge";

describe("map data-quality badges", () => {
  it("shows unavailable values with the API label and a neutral absence icon", () => {
    const html = renderToStaticMarkup(createElement(DataQualityBadge, {
      geographyLevel: "census_tract",
      metricStatus: "unavailable",
      dataQualityLabel: "No CMHC tract values",
    }));

    expect(html).toContain("No CMHC tract values");
    expect(html).toContain("lucide-circle-minus");
    expect(html).toContain("text-civic-muted");
    expect(html).not.toMatch(/lucide-badge-check|emerald|Official tract metrics/);
  });

  it("does not describe unavailable data as official when no label is supplied", () => {
    const html = renderToStaticMarkup(createElement(DataQualityBadge, {
      geographyLevel: "municipality",
      metricStatus: "unavailable",
    }));

    expect(html).toContain("Data unavailable");
    expect(html).not.toContain("Official municipal metrics");
  });

  it.each(["estimated", "mixed"] as const)("retains the warning treatment for %s values", metricStatus => {
    const html = renderToStaticMarkup(createElement(DataQualityBadge, {
      geographyLevel: "census_tract",
      metricStatus,
      dataQualityLabel: "CMHC (estimated tract allocation)",
    }));

    expect(html).toContain("CMHC (estimated tract allocation)");
    expect(html).toContain("lucide-triangle-alert");
    expect(html).toContain("text-amber-900");
    expect(html).not.toContain("lucide-badge-check");
  });
});
