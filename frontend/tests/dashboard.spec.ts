import { expect, test, type Page } from "@playwright/test";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

type MapFeaturePayload = {
  geometry: {
    type: string;
    coordinates: unknown;
  };
  properties: {
    geoid: string;
    name: string;
    bbox: number[];
    metrics: {
      median_income: number | null;
      median_rent: number | null;
      rent_burden_pct: number | null;
      affordability_index: number | null;
      data_quality?: Record<string, string>;
    };
  };
};

type MapPayload = {
  type: "FeatureCollection";
  metadata: {
    domain: {
      min: number | null;
      max: number | null;
    };
    geography_type: "municipality" | "census_tract";
    data_quality: {
      metric_status: "official" | "estimated" | "mixed";
      label: string;
    };
  };
  features: MapFeaturePayload[];
};

test.describe("CivicScope dashboard regressions", () => {
  test("map data API returns usable GTA municipality polygons with official metrics", async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/map-data?metric=rent_burden&detail=display`);
    expect(response.ok(), await response.text()).toBeTruthy();

    const payload = (await response.json()) as MapPayload;
    expect(payload.type).toBe("FeatureCollection");
    expect(payload.metadata.geography_type).toBe("municipality");
    expect(payload.metadata.data_quality.metric_status).toBe("official");
    expect(payload.features).toHaveLength(25);
    expect(payload.metadata.domain.min).toBeGreaterThan(20);
    expect(payload.metadata.domain.max).toBeLessThan(60);

    for (const feature of payload.features) {
      expect(["Polygon", "MultiPolygon"]).toContain(feature.geometry.type);
      expect(feature.properties.bbox).toHaveLength(4);
      expect(feature.properties.bbox.every(Number.isFinite)).toBe(true);
      expect(countCoordinatePairs(feature.geometry.coordinates)).toBeGreaterThan(8);
      expect(feature.properties.metrics.median_income).toBeGreaterThan(0);
      expect(feature.properties.metrics.median_rent).toBeGreaterThan(0);
      expect(feature.properties.metrics.rent_burden_pct).toBeGreaterThan(0);
      expect(feature.properties.metrics.affordability_index).toBeGreaterThan(0);
    }
  });

  test("geography level selector loads census tract map data and tract search", async ({ page }) => {
    await blockExternalMapAssets(page);

    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();

    const map = page.getByTestId("civic-map");
    await expect(page.getByText("Rent burden by census tract")).toBeVisible();
    await expect(page.getByTestId("summary-panel")).toContainText("1,334 GTA census tracts");
    // Rent burden is the default metric and has an estimated fallback, so the
    // badge must disclose that — not claim every value is official.
    await expect(
      page.getByTestId("data-quality-badge").filter({ hasText: "Official + estimated tract metrics" })
    ).toHaveCount(2);
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });
    await expect(map).toHaveAttribute("data-feature-count", "1334", { timeout: 30000 });
    await expect(page.getByTestId("detail-panel")).toContainText("official 2021 Census Profile");

    await page.getByTestId("geography-search").fill("5350001.00");
    const tractResult = page.getByRole("option").filter({ hasText: "5350001.00" });
    await expect(tractResult).toHaveCount(1);
    await tractResult.click();

    await expect(page.getByTestId("detail-panel")).toContainText("Toronto census tract 0001.00");
    await expect(page.getByTestId("detail-panel")).not.toContainText("No data");
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");
  });

  test("overview renders summary values, map canvas, legend, and comparison chart", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    await blockExternalMapAssets(page);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Greater Toronto Housing Affordability Monitor" })
    ).toBeVisible();

    const summary = page.getByTestId("summary-panel");
    await expect(summary).toContainText("25 GTA municipalities");
    await expect(summary).toContainText("$1,554");
    await expect(summary).toContainText("40.7%");
    await expect(summary).toContainText("6,711,985");

    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-feature-count", "25");
    // Legend is titled with the active metric and split into quantile classes.
    const legend = page.getByTestId("map-legend");
    await expect(legend).toContainText("Rent burden");
    await expect(legend.locator("[data-legend-class]").first()).toBeVisible();

    const canvas = map.locator("canvas");
    await expect(canvas).toHaveCount(1);
    const canvasBox = await canvas.boundingBox();
    expect(canvasBox).not.toBeNull();
    expect(canvasBox?.width).toBeGreaterThan(320);
    expect(canvasBox?.height).toBeGreaterThan(320);

    const comparison = page.getByTestId("comparison-panel");
    await expect(page.getByText("Loading comparison...")).toHaveCount(0);
    await expect(comparison).toContainText("Toronto");
    await expect(comparison).toContainText("Mississauga");
    await expect(comparison.locator(".recharts-bar-rectangle")).toHaveCount(5);
    await expect(page.getByTestId("dashboard-root")).not.toContainText("No data");

    expect(consoleErrors.filter((message) => !message.includes("Failed to load resource"))).toEqual([]);
  });

  test("municipality search selects Toronto without losing local metrics", async ({ page }) => {
    await blockExternalMapAssets(page);

    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    await page.getByTestId("geography-search").fill("Toronto");
    const torontoResult = page.getByRole("option").filter({ hasText: "3520005" });
    await expect(torontoResult).toHaveCount(1);
    await torontoResult.click();

    await expect(page.getByTestId("summary-panel")).toContainText("Toronto");
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
    await expect(page.getByTestId("detail-panel")).not.toContainText("No data");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
  });

  test("switching between municipalities and census tracts does not produce API errors", async ({ page }) => {
    const apiErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/api/") && response.status() >= 400) {
        apiErrors.push(`${response.status()} ${response.url()}`);
      }
    });
    await blockExternalMapAssets(page);

    await page.goto("/");
    const map = page.getByTestId("civic-map");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");
    await expect(map).toHaveAttribute("data-feature-count", "25");

    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(map).toHaveAttribute("data-feature-count", "1334", { timeout: 30000 });
    await expect(map).toHaveAttribute("data-geography-type", "census_tract");

    await page.getByRole("button", { name: "Municipalities" }).click();
    await expect(map).toHaveAttribute("data-geography-type", "municipality");
    await expect(map).toHaveAttribute("data-feature-count", "25");

    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(map).toHaveAttribute("data-geography-type", "census_tract");
    await expect(map).toHaveAttribute("data-feature-count", "1334");

    expect(apiErrors).toEqual([]);
  });

  test("switching geography level with a selection active fires no stale cross-type requests", async ({ page }) => {
    const apiErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/api/") && response.status() >= 400) {
        apiErrors.push(`${response.status()} ${response.url()}`);
      }
    });
    await blockExternalMapAssets(page);

    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    // Select a census tract, then switch back to municipalities. The stale
    // tract geoid must not be requested under type=municipality (would 404).
    await page.getByTestId("geography-search").fill("5350001.00");
    const result = page.getByRole("option").filter({ hasText: "5350001.00" });
    await expect(result).toHaveCount(1);
    await result.click();
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");

    await page.getByRole("button", { name: "Municipalities" }).click();
    await expect(map).toHaveAttribute("data-geography-type", "municipality", { timeout: 30000 });
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    expect(apiErrors).toEqual([]);
  });

  test("metric selector repaints map state and polygon clicks select a municipality", async ({ page }) => {
    await blockExternalMapAssets(page);

    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-metric", "rent_burden_pct");
    const initialDomainMax = await map.getAttribute("data-domain-max");

    await page.getByLabel("Map metric").selectOption("median_income");
    await expect(page.getByText("Median income by municipality")).toBeVisible();
    await expect(map).toHaveAttribute("data-metric", "median_income");
    await expect(map).not.toHaveAttribute("data-domain-max", initialDomainMax ?? "");
    // Legend retitles to the active metric (quantile classes shown below it).
    await expect(page.getByTestId("map-legend")).toContainText("Median income");

    await page.getByLabel("Map metric").selectOption("population_growth_pct");
    await expect(page.getByText("Population growth by municipality")).toBeVisible();
    await expect(map).toHaveAttribute("data-metric", "population_growth_pct");
    await expect(map).toHaveAttribute("data-domain-max", "44.4");
    await expect(page.getByTestId("map-legend")).toContainText("Population growth");
    await expect(page.getByText("Updating map...")).toHaveCount(0);

    const canvasBox = await map.locator("canvas").boundingBox();
    expect(canvasBox).not.toBeNull();
    await page.mouse.click(
      canvasBox!.x + canvasBox!.width * 0.47,
      canvasBox!.y + canvasBox!.height * 0.67
    );

    await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
    await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
  });

  test("grouped metric selector renders optgroup tags and CMHC metrics", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const select = page.getByLabel("Map metric");
    const optgroups = select.locator("optgroup");
    await expect(optgroups).toHaveCount(2);
    await expect(optgroups.first()).toHaveAttribute("label", "Census Profile");
    await expect(optgroups.last()).toHaveAttribute("label", "CMHC Rental Market");

    await select.selectOption("vacancy_rate");
    await expect(page.getByText("Vacancy rate by municipality")).toBeVisible();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "vacancy_rate");
  });

  test("year selector is disabled for Census metrics and enabled for CMHC metrics", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const yearSelect = page.getByLabel("Data year");
    await expect(yearSelect).toBeDisabled();

    await page.getByLabel("Map metric").selectOption("vacancy_rate");
    await expect(yearSelect).toBeEnabled();

    await page.getByLabel("Map metric").selectOption("rent_burden_pct");
    await expect(yearSelect).toBeDisabled();
  });

  test("switching between Census and CMHC metrics does not produce API errors", async ({ page }) => {
    const apiErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/api/") && response.status() >= 400) {
        apiErrors.push(`${response.status()} ${response.url()}`);
      }
    });
    await blockExternalMapAssets(page);

    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    await page.getByLabel("Map metric").selectOption("vacancy_rate");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "vacancy_rate");

    await page.getByLabel("Map metric").selectOption("median_income");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "median_income");

    await page.getByLabel("Map metric").selectOption("housing_starts_total");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "housing_starts_total");

    expect(apiErrors).toEqual([]);
  });

  test("census tract map-data exposes field-level provenance for tract metrics", async ({ request }) => {
    const response = await request.get(
      `${API_BASE}/api/map-data?metric=rent_burden&type=census_tract&detail=display`
    );
    expect(response.ok(), await response.text()).toBeTruthy();
    const payload = (await response.json()) as MapPayload;

    // The badge must not flatly claim every tract rent-burden value is official.
    expect(payload.metadata.data_quality.metric_status).toBe("mixed");
    expect(payload.metadata.data_quality.label).toContain("estimated");

    const withQuality = payload.features.filter((f) => f.properties.metrics.data_quality);
    expect(withQuality.length).toBe(payload.features.length);

    const statuses = new Set(
      payload.features.map((f) => f.properties.metrics.data_quality?.rent_burden_pct)
    );
    // Official, estimated, and unavailable rent burden all coexist among tracts.
    expect(statuses.has("official")).toBe(true);
    expect(statuses.has("estimated")).toBe(true);
    expect(statuses.has("unavailable")).toBe(true);
  });

  test("estimated tract rent burden is visibly flagged, not presented as official", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );

    // Whitby tract 0105.17 has a suppressed official rent burden but usable
    // rent + income, so it is estimated and must say so.
    await page.getByTestId("geography-search").fill("5320105.17");
    const result = page.getByRole("option").filter({ hasText: "5320105.17" });
    await expect(result).toHaveCount(1);
    await result.click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel).toContainText("Whitby census tract 0105.17");
    await expect(panel.getByTestId("estimated-flag").first()).toBeVisible();
    await expect(panel).toContainText("Rent burden estimated from median rent and income");
  });

  test("tract with a tiny previous population flags low-confidence growth", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );

    // Whitby tract 0105.22: 2016 base population of 5 produces an absurd growth %.
    await page.getByTestId("geography-search").fill("5320105.22");
    const result = page.getByRole("option").filter({ hasText: "5320105.22" });
    await expect(result).toHaveCount(1);
    await result.click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel.getByTestId("low-confidence-flag").first()).toBeVisible();
    await expect(panel).toContainText("very small 2016 base");
  });

  test("tract with a suppressed value renders Not available without crashing", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );

    // Whitby tract 0105.24 has a suppressed median rent.
    await page.getByTestId("geography-search").fill("5320105.24");
    const result = page.getByRole("option").filter({ hasText: "5320105.24" });
    await expect(result).toHaveCount(1);
    await result.click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel).toContainText("Whitby census tract 0105.24");
    await expect(panel).toContainText("Not available");
  });

  test("population growth map scale excludes tiny-base outliers in tract mode", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    await page.getByLabel("Map metric").selectOption("population_growth_pct");
    await expect(map).toHaveAttribute("data-metric", "population_growth_pct");

    // A handful of near-empty 2016-base tracts reach ~29,580% growth; they must
    // not define the color scale (they are still shown, flagged, on click).
    const domainMax = Number(await map.getAttribute("data-domain-max"));
    expect(domainMax).toBeGreaterThan(0);
    expect(domainMax).toBeLessThan(5000);
  });

  test("CMHC starts in census tract mode shows official+estimated provenance", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );

    await page.getByLabel("Map metric").selectOption("housing_starts_total");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "housing_starts_total");

    // housing_starts_total now has REAL CMHC census-tract values where published,
    // with the allocation as a labeled estimate elsewhere -> mixed badge.
    await expect(
      page.getByTestId("data-quality-badge").filter({ hasText: /official \+ estimated/i }).first()
    ).toBeVisible();

    // 2023 has real published tract starts; select it so a covered tract shows
    // the real value (the latest year has no tract data yet).
    await page.getByLabel("Data year").selectOption("2023");

    // A covered Toronto tract shows the real value flagged "CMHC tract data".
    await page.getByTestId("geography-search").fill("5350017.01");
    const result = page.getByRole("option").filter({ hasText: "5350017.01" });
    await expect(result).toHaveCount(1);
    await result.click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel).toContainText("census tract 0017.01");
    // Real starts value carries the "CMHC tract data" badge...
    await expect(panel.getByTestId("official-flag").first()).toBeVisible();
    // ...but the badge belongs ONLY to the Housing Construction section. The
    // census "Household & Housing Profile" fields are Statistics Canada values
    // and must NOT be mislabeled "CMHC tract data" (regression).
    const censusSection = panel.locator("div", { hasText: "Household & Housing Profile" }).first();
    await expect(censusSection.getByTestId("official-flag")).toHaveCount(0);
  });

  test("a parent-tract-allocated tract is flagged 'est. (CMHC parent tract)'", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );
    await page.getByLabel("Map metric").selectOption("housing_starts_total");
    await page.getByLabel("Data year").selectOption("2023");

    // 5320003.01 split from CMHC parent 0003.00 -> allocated value, distinct
    // "est. (CMHC parent tract)" provenance (not "CMHC tract data", not plain "est.").
    await page.getByTestId("geography-search").fill("5320003.01");
    await page.getByRole("option").filter({ hasText: "5320003.01" }).first().click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel.getByTestId("parent-est-flag").first()).toBeVisible();
    await expect(panel).toContainText("CMHC parent tract");
  });

  test("map legend is titled with the metric and split into quantile classes", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    await page.getByLabel("Map metric").selectOption("population");
    await expect(map).toHaveAttribute("data-metric", "population");

    // Quantile legend: titled with the metric and split into multiple classes so
    // skewed data (population) is differentiated rather than washed into one band.
    const legend = page.getByTestId("map-legend");
    await expect(legend).toContainText("Population");
    const classes = legend.locator("[data-legend-class]");
    await expect(classes.first()).toBeVisible();
    expect(await classes.count()).toBeGreaterThanOrEqual(3);
  });

  // Full pointer-driven hover lives in tests/tooltip.spec.ts as a unit test of
  // buildTooltipHtml — MapLibre's WebGL hit-testing under synthetic mouse moves
  // is unreliable in headless CI, so the popup MARKUP (the part with real logic)
  // is covered there deterministically, and the live pointer interaction is
  // verified manually / in headed runs.

  test("data-sources footer attributes Statistics Canada and CMHC", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const footer = page.locator("footer");
    await expect(footer).toContainText("Statistics Canada");
    await expect(footer).toContainText("CMHC");
  });

  test("CMHC rate metric in tract mode is labeled inherited, not allocated", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    await page.getByLabel("Map metric").selectOption("average_rent_total");
    await expect(map).toHaveAttribute("data-metric", "average_rent_total");

    // The badge must explain that the rent is the inherited municipal value
    // (so identical values across a municipality's tracts are not seen as a bug).
    const badge = page.getByTestId("data-quality-badge").first();
    await expect(badge).toContainText(/inherited|municipal/i);
    await expect(badge).not.toContainText(/allocation/i);
  });

  test("a metric with no data shows an explicit empty state on the map", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    // turnover_rate is not collected in this dataset -> empty, not silently blank.
    await page.getByLabel("Map metric").selectOption("turnover_rate");
    await expect(map).toHaveAttribute("data-empty", "true", { timeout: 30000 });
    await expect(page.getByTestId("map-empty-state")).toContainText("No data available");
  });

  test("search with no matches shows a no-results message", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const search = page.getByTestId("geography-search");
    await search.click();
    await search.fill("zzzznomatch");
    await expect(page.getByTestId("search-empty")).toContainText("No", { timeout: 5000 });
  });

  test("the no-results message does not block other controls", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");
    // Leave a no-match query in the box so the empty-state dropdown is showing,
    // then switch geography level — the overlay must not intercept the click.
    await page.getByTestId("geography-search").fill("zzzznomatch");
    await expect(page.getByTestId("search-empty")).toBeVisible();
    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30000 }
    );
  });

  test("map exposes an accessible region label", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("role", "region");
    await expect(map).toHaveAttribute("aria-label", /map of .+ by/i);
  });
});

function countCoordinatePairs(value: unknown): number {
  if (!Array.isArray(value)) {
    return 0;
  }

  if (typeof value[0] === "number" && typeof value[1] === "number") {
    return 1;
  }

  return value.reduce((total: number, item) => total + countCoordinatePairs(item), 0);
}

async function blockExternalMapAssets(page: Page) {
  await page.route("https://*.basemaps.cartocdn.com/**", (route) => route.abort());
  await page.route("https://demotiles.maplibre.org/**", (route) => route.abort());
}
