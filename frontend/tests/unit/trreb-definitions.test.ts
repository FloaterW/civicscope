import { describe, expect, it } from "vitest";
import { getMetricDefinition } from "@/components/MetricTooltip";

describe("TRREB metric explanations", () => {
  it.each(["trreb_median_price", "trreb_sales", "trreb_property_days"])("attributes %s to the historical TRREB reports", key => {
    expect(getMetricDefinition(key)?.source).toContain("Toronto Regional Real Estate Board");
    expect(getMetricDefinition(key)?.source).toContain("2020–2025");
  });
  it("distinguishes annual medians, resale transactions and property days", () => {
    expect(getMetricDefinition("trreb_median_price")?.definition).toContain("not averages of monthly medians");
    expect(getMetricDefinition("trreb_sales")?.definition).toContain("not the number of active listings or rental leases");
    expect(getMetricDefinition("trreb_property_days")?.definition).toContain("qualifying re-listings");
    expect(getMetricDefinition("trreb_property_days")?.definition).toContain("differs from listing days");
  });
});
