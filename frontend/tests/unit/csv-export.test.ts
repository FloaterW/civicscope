import { describe, expect, it } from "vitest";

import { buildGeographyExportRows, CSV_HEADERS, rowsToCsv } from "@/lib/csv-export";
import type { CmhcMetricValues, MetricValues, TransitSnapshot } from "@/types";

const metrics = {
  year: 2021,
  median_income: 90000,
  median_rent: 1500,
  rent_burden_pct: 31.2,
  population_growth_pct: 4.2,
  population: 1000,
  affordability_index: 150,
  transit_score: 0,
  transit_route_count: 0,
  data_quality: {
    median_income: "official",
    median_rent: "official",
    rent_burden_pct: "estimated",
    population_growth_pct: "derived",
    population: "official",
    affordability_index: "derived",
    transit_score: "derived",
    transit_route_count: "derived"
  }
} as MetricValues;

const cmhc = {
  year: 2023,
  vacancy_rate: 2.1,
  average_rent_total: 1900,
  housing_starts_total: 12,
  housing_completions: 9,
  units_under_construction: 4,
  unabsorbed_units: 1,
  rental_universe: 200,
  rms_surveyed: true,
  allocated: true,
  starts_source: "official",
  completions_source: "estimated_parent",
  survey_zone: "Toronto (Central)",
  vacancy_rate_source: "survey_zone",
  average_rent_total_source: "survey_zone",
  other_rms_source: "inherited_municipality"
} as CmhcMetricValues;

const transitSnapshot: TransitSnapshot = {
  schema_version: 1,
  packaged_at: "2026-06-24T11:48:17-04:00",
  coverage_status: "partial",
  included_agencies: [{ id: "ttc", name: "TTC" }],
  missing_agencies: [{ id: "brampton", name: "Brampton Transit" }]
};

describe("buildGeographyExportRows", () => {
  it("exports explicit periods, methods, and statuses", () => {
    const rows = buildGeographyExportRows("census_tract", metrics, cmhc, 2023);

    expect(rows[0]).toEqual(CSV_HEADERS);
    expect(rows.find((row) => row[0] === "Rent burden")).toEqual([
      "Rent burden",
      "31.2",
      "2021 Census",
      "Statistics Canada Census Profile",
      "Estimated from median rent and household income",
      "estimated"
    ]);
    expect(rows.find((row) => row[0] === "Vacancy rate")?.slice(2)).toEqual([
      "October 2023 survey",
      "CMHC Rental Market Survey — survey zone (Toronto (Central))",
      "Published at survey-zone granularity",
      "official"
    ]);
    expect(rows.find((row) => row[0] === "Housing starts")?.slice(2)).toEqual([
      "Calendar year 2023",
      "CMHC Starts & Completions Survey — census tract",
      "Published tract value",
      "official"
    ]);
  });

  it("preserves genuine transit zeros as derived values", () => {
    const rows = buildGeographyExportRows(
      "census_tract",
      metrics,
      undefined,
      undefined,
      transitSnapshot
    );
    expect(rows.find((row) => row[0] === "Transit routes nearby")?.[1]).toBe("0");
    expect(rows.find((row) => row[0] === "Transit routes nearby")?.[5]).toBe(
      "derived (partial coverage)"
    );
    expect(rows.find((row) => row[0] === "Transit snapshot coverage")).toEqual([
      "Transit snapshot coverage",
      "partial",
      "2026-06-24",
      "Included agencies: TTC",
      "Missing agencies: Brampton Transit",
      "partial"
    ]);
  });
});

describe("rowsToCsv", () => {
  it("quotes values and neutralizes spreadsheet formulas", () => {
    const csv = rowsToCsv([
      ["Area", "Value"],
      ["=HYPERLINK(\"https://example.test\")", "+1"],
      ["ordinary", "-42"],
    ]);

    expect(csv).toContain(`"'=HYPERLINK(""https://example.test"")"`);
    expect(csv).toContain(`"'+1"`);
    expect(csv).toContain(`"'-42"`);
  });
});
