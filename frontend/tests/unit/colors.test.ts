import { describe, expect, it } from "vitest";

import {
  POSITIVE_RAMP,
  RISK_RAMP,
  SEQUENTIAL_RAMP,
  rampColorForValue,
  rampForMetric
} from "@/lib/colors";

describe("metric-aware color ramps", () => {
  it("uses a positive ramp for affordability and transit access", () => {
    expect(rampForMetric("affordability_index")).toBe(POSITIVE_RAMP);
    expect(rampForMetric("transit_score")).toBe(POSITIVE_RAMP);
    expect(rampColorForValue(100, 0, 100, "affordability_index")).toBe(
      POSITIVE_RAMP[2]
    );
  });

  it("uses a risk ramp for burden and rent", () => {
    expect(rampForMetric("rent_burden_pct")).toBe(RISK_RAMP);
    expect(rampForMetric("median_rent")).toBe(RISK_RAMP);
  });

  it("uses a neutral sequential ramp for population and supply counts", () => {
    expect(rampForMetric("population")).toBe(SEQUENTIAL_RAMP);
    expect(rampForMetric("housing_starts_total")).toBe(SEQUENTIAL_RAMP);
  });
});
