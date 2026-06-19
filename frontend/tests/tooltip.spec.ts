import { expect, test } from "@playwright/test";

import { buildTooltipHtml, escapeHtml } from "../lib/tooltip";

// Pure unit tests for the map hover-tooltip markup. The pointer-driven popup is
// covered manually / in headed runs (MapLibre WebGL hit-testing is unreliable in
// headless CI), but the part with real logic — the markup builder — is fully
// deterministic and tested here, so CI guards the tooltip's content and format.

test.describe("buildTooltipHtml", () => {
  test("renders the geography name, metric label, and formatted value", () => {
    const html = buildTooltipHtml(
      { name: "Toronto", value: 40, metrics: JSON.stringify({}) },
      "rent_burden_pct"
    );
    expect(html).toContain("Toronto");
    expect(html).toContain("Rent burden");
    expect(html).toContain("40.0%");
  });

  test("returns null when the feature has no name", () => {
    expect(buildTooltipHtml({ value: 40 }, "rent_burden_pct")).toBeNull();
  });

  test("parses JSON-stringified properties from the vector source", () => {
    // Properties arrive stringified from MapLibre's vector tiles.
    const html = buildTooltipHtml(
      { name: "Markham", value: "1850", metrics: JSON.stringify({ data_quality: {} }) },
      "median_rent"
    );
    expect(html).toContain("Markham");
    expect(html).toContain("Median rent");
    expect(html).toContain("$1,850");
  });

  test('appends "(estimated)" when the field is flagged estimated', () => {
    const html = buildTooltipHtml(
      {
        name: "Whitby census tract 0105.17",
        value: 12,
        metrics: JSON.stringify({ data_quality: { rent_burden_pct: "estimated" } })
      },
      "rent_burden_pct"
    );
    expect(html).toContain("(estimated)");
  });

  test('appends "(low confidence)" for low_confidence growth', () => {
    const html = buildTooltipHtml(
      {
        name: "Whitby census tract 0105.22",
        value: 29580,
        metrics: JSON.stringify({ data_quality: { population_growth_pct: "low_confidence" } })
      },
      "population_growth_pct"
    );
    expect(html).toContain("(low confidence)");
  });

  test("renders Not available for a null value without crashing", () => {
    const html = buildTooltipHtml(
      { name: "Some tract", value: null, metrics: JSON.stringify({}) },
      "median_rent"
    );
    expect(html).toContain("Not available");
  });

  test("escapeHtml neutralizes angle brackets and quotes", () => {
    expect(escapeHtml('<script>"x"')).toBe("&lt;script&gt;&quot;x&quot;");
  });

  test("escapes HTML in a feature name to prevent injection", () => {
    const html = buildTooltipHtml(
      { name: "<img src=x onerror=alert(1)>", value: 1, metrics: JSON.stringify({}) },
      "rent_burden_pct"
    );
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});
