import { describe, expect, it } from "vitest";
import { formatMetric, getMetricLabel, isCmhcMetric, mapDataCacheKey } from "@/lib/api";

describe("formatMetric", () => {
  it("formats currency for median_income", () => {
    expect(formatMetric("median_income", 84000)).toBe("$84,000");
  });

  it("formats currency for median_rent", () => {
    expect(formatMetric("median_rent", 1500)).toBe("$1,500");
  });

  it("formats currency for CMHC average rent", () => {
    expect(formatMetric("average_rent_total", 1917)).toBe("$1,917");
  });

  it("formats percentage for rent_burden_pct", () => {
    expect(formatMetric("rent_burden_pct", 40.7)).toBe("40.7%");
  });

  it("formats affordability_index with one decimal", () => {
    expect(formatMetric("affordability_index", 160.9)).toBe("160.9");
  });

  it("formats population as integer with commas", () => {
    expect(formatMetric("population", 2794356)).toBe("2,794,356");
  });

  it("formats housing_starts_total as integer", () => {
    expect(formatMetric("housing_starts_total", 1234)).toBe("1,234");
  });

  it("formats housing_completions as integer", () => {
    expect(formatMetric("housing_completions", 567)).toBe("567");
  });

  it("formats rent_to_income_ratio as percentage", () => {
    expect(formatMetric("rent_to_income_ratio", 0.21)).toBe("21%");
  });

  it("returns 'Not available' for null", () => {
    expect(formatMetric("population", null)).toBe("Not available");
  });

  it("returns 'Not available' for undefined", () => {
    expect(formatMetric("population", undefined)).toBe("Not available");
  });

  it("returns 'Not available' for NaN", () => {
    expect(formatMetric("population", NaN)).toBe("Not available");
  });

  it("formats vacancy_rate as percentage", () => {
    expect(formatMetric("vacancy_rate", 2.8)).toBe("2.8%");
  });
});

describe("getMetricLabel", () => {
  it("returns label for known metric", () => {
    expect(getMetricLabel("rent_burden_pct")).toBe("Rent burden");
  });

  it("returns label for CMHC metric", () => {
    expect(getMetricLabel("vacancy_rate")).toBe("Vacancy rate");
  });

  it("falls back to key for unknown metric", () => {
    expect(getMetricLabel("unknown_metric" as never)).toBe("unknown_metric");
  });
});

describe("isCmhcMetric", () => {
  it("returns true for vacancy_rate", () => {
    expect(isCmhcMetric("vacancy_rate")).toBe(true);
  });

  it("returns true for average_rent_total", () => {
    expect(isCmhcMetric("average_rent_total")).toBe(true);
  });

  it("returns false for population", () => {
    expect(isCmhcMetric("population")).toBe(false);
  });

  it("returns false for median_income", () => {
    expect(isCmhcMetric("median_income")).toBe(false);
  });
});

describe("mapDataCacheKey", () => {
  it("reuses census payloads across census and transit metrics", () => {
    expect(mapDataCacheKey("census_tract", "median_income")).toBe(
      mapDataCacheKey("census_tract", "transit_score")
    );
  });

  it("reuses CMHC payloads by geography and year", () => {
    expect(mapDataCacheKey("municipality", "vacancy_rate", 2024)).toBe(
      mapDataCacheKey("municipality", "housing_starts_total", 2024)
    );
    expect(mapDataCacheKey("municipality", "vacancy_rate", 2023)).not.toBe(
      mapDataCacheKey("municipality", "vacancy_rate", 2024)
    );
  });
});
