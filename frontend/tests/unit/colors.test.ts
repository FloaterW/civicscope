import { describe, expect, it } from "vitest";

import {
  buildChoroplethScale,
  choroplethColorExpression,
  FLAT_COLOR,
  NULL_COLOR,
  POSITIVE_RAMP,
  RISK_RAMP,
  SEQUENTIAL_RAMP,
  rampColorForValue,
  rampForMetric
} from "@/lib/colors";
import type { MapData } from "@/types";

function mapData(values: Array<number | null>, metric = "population"): MapData {
  return {
    type: "FeatureCollection",
    metadata: { metric },
    features: values.map((value, index) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [index, index] },
      properties: { value }
    }))
  } as unknown as MapData;
}

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

describe("choropleth classes", () => {
  it("reports an empty dataset and paints it with the no-data color", () => {
    const data = mapData([null, null]);
    const scale = buildChoroplethScale(data);

    expect(scale).toMatchObject({
      classes: [],
      min: null,
      max: null,
      availableCount: 0,
      noDataCount: 2
    });
    expect(choroplethColorExpression(data)).toEqual(["literal", NULL_COLOR]);
  });

  it("uses one flat class when every available value is equal", () => {
    const data = mapData([7, 7, null]);
    const scale = buildChoroplethScale(data);

    expect(scale.flat).toBe(true);
    expect(scale.classes).toEqual([{ lower: 7, upper: null, color: FLAT_COLOR }]);
    expect(scale.noDataCount).toBe(1);
    expect(choroplethColorExpression(data)).toEqual([
      "case",
      ["==", ["get", "value"], null],
      NULL_COLOR,
      FLAT_COLOR
    ]);
  });

  it("deduplicates tied quantile boundaries and uses the same boundaries in the step expression", () => {
    const data = mapData([1, 1, 1, 2, 2, 5, 5, 10, null]);
    const scale = buildChoroplethScale(data);
    const expression = choroplethColorExpression(data);

    expect(scale.classes.map((entry) => entry.lower)).toEqual([1, 2, 5]);
    expect(scale.availableCount).toBe(8);
    expect(scale.noDataCount).toBe(1);
    expect(expression[0]).toBe("case");
    expect(JSON.stringify(expression)).toContain('"step"');
    for (const colorClass of scale.classes) {
      expect(JSON.stringify(expression)).toContain(String(colorClass.lower));
      expect(JSON.stringify(expression)).toContain(colorClass.color);
    }
  });

  it("keeps values outside the trusted API domain from distorting quantile boundaries", () => {
    const data = mapData([10, 20, 30, 40, 50, 29_580, null], "population_growth_pct");
    data.metadata.domain = { min: 10, max: 50 };

    const scale = buildChoroplethScale(data);
    const expression = choroplethColorExpression(data);

    expect(scale.min).toBe(10);
    expect(scale.max).toBe(50);
    expect(scale.availableCount).toBe(6);
    expect(scale.noDataCount).toBe(1);
    expect(scale.classes.every((entry) => entry.lower <= 50)).toBe(true);
    expect(JSON.stringify(expression)).not.toContain("29580");
  });

  it("keeps a distinct positive class when sparse counts tie at zero", () => {
    const data = mapData([0, 0, 0, 0, 0, 0, 0, 0, 0, 10], "housing_starts_total");
    data.metadata.domain = { min: 0, max: 10 };

    const scale = buildChoroplethScale(data);
    const expression = choroplethColorExpression(data);

    expect(scale.flat).toBe(false);
    expect(scale.classes.map((entry) => entry.lower)).toEqual([0, 10]);
    expect(new Set(scale.classes.map((entry) => entry.color)).size).toBe(2);
    expect(JSON.stringify(expression)).toContain('10');
  });
});
