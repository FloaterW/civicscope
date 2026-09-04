import { describe, expect, it } from "vitest";

import {
  buildDashboardUrl,
  DEFAULT_DASHBOARD_LEVEL,
  DEFAULT_DASHBOARD_METRIC,
  parseDashboardUrl
} from "@/lib/dashboard-url";

describe("dashboard URL state", () => {
  it("uses safe defaults and ignores malformed owned parameters", () => {
    expect(parseDashboardUrl("?level=ward&metric=unknown&year=tomorrow&geoid=oops")).toEqual({
      level: DEFAULT_DASHBOARD_LEVEL,
      metric: DEFAULT_DASHBOARD_METRIC,
      year: undefined,
      geoid: undefined,
      adjustedForTransit: false
    });
  });

  it("restores a valid CMHC tract view and year", () => {
    expect(
      parseDashboardUrl(
        "?level=census_tract&metric=housing_starts_total&year=2023&geoid=5350001.00"
      )
    ).toEqual({
      level: "census_tract",
      metric: "housing_starts_total",
      year: 2023,
      geoid: "5350001.00",
      adjustedForTransit: false
    });
  });

  it("normalizes transit views to tracts and drops an incompatible municipality id", () => {
    expect(parseDashboardUrl("?level=municipality&metric=transit_score&geoid=3520005")).toEqual({
      level: "census_tract",
      metric: "transit_score",
      year: undefined,
      geoid: undefined,
      adjustedForTransit: true
    });
  });

  it("omits irrelevant Census years while preserving valid Census selection state", () => {
    expect(
      parseDashboardUrl(
        "?level=census_tract&metric=population&year=2025&geoid=5350001.00"
      )
    ).toMatchObject({
      level: "census_tract",
      metric: "population",
      year: undefined,
      geoid: "5350001.00"
    });
  });

  it("preserves unrelated parameters and hashes while canonicalizing owned state", () => {
    const path = buildDashboardUrl(
      "https://example.test/?campaign=civic&year=2022#comparison",
      {
        level: "census_tract",
        metric: "population",
        year: 2025,
        geoid: "5350001.00"
      }
    );
    const url = new URL(path, "https://example.test");

    expect(url.searchParams.get("campaign")).toBe("civic");
    expect(url.searchParams.get("level")).toBe("census_tract");
    expect(url.searchParams.get("metric")).toBe("population");
    expect(url.searchParams.get("geoid")).toBe("5350001.00");
    expect(url.searchParams.has("year")).toBe(false);
    expect(url.hash).toBe("#comparison");
  });
});
