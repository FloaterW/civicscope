import { readFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
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
      metric_status: "official" | "derived" | "estimated" | "mixed" | "zone";
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
      page.getByRole("heading", { name: "Greater Toronto Housing Affordability Explorer" })
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
    await expect(legend.locator("[data-legend-no-data]")).toContainText("No data");

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
    await expect(page.getByTestId("detail-panel")).not.toContainText("No data");

    expect(consoleErrors.filter((message) => !message.includes("Failed to load resource"))).toEqual([]);
  });

  test("slow API startup shows an honest loading state instead of zero regions", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.route(`${API_BASE}/api/**`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_800));
      await route.continue();
    });
    await page.goto("/");

    const summary = page.getByTestId("summary-panel");
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("aria-busy", "true");
    await expect(summary).toContainText("Loading GTA data");
    await expect(summary).not.toContainText("0 GTA municipalities");
    await expect(page.getByTestId("data-service-status")).toContainText(
      "Still connecting to the CivicScope data service"
    );
    await expect(summary).toContainText("25 GTA municipalities", { timeout: 15_000 });
    await expect(map).toHaveAttribute("aria-busy", "false");
    await expect(page.getByTestId("data-service-status")).toHaveCount(0);
  });

  test("comparison tooltip is dismissed when the viewport changes", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const chart = page.getByTestId("comparison-panel");
    const bar = chart.locator(".recharts-bar-rectangle").first();
    await expect(bar).toBeVisible();
    await bar.hover();
    await expect(chart.locator(".recharts-tooltip-wrapper")).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(chart.locator(".recharts-tooltip-wrapper")).toBeHidden();
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  });

  test("metric information stays inside a phone viewport and dismisses cleanly", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const trigger = page
      .getByRole("button", { name: "What is Affordability index?" })
      .first();
    await trigger.click();
    const tooltip = page.getByRole("tooltip");
    await expect(tooltip).toBeVisible();

    const bounds = await tooltip.boundingBox();
    const viewport = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(bounds).not.toBeNull();
    expect(bounds?.x).toBeGreaterThanOrEqual(0);
    expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(
      viewport.clientWidth
    );
    expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);

    await page.keyboard.press("Escape");
    await expect(tooltip).toBeHidden();
    await trigger.click();
    await expect(tooltip).toBeVisible();
    await page.getByRole("heading", { name: "GTA housing data map" }).click();
    await expect(tooltip).toBeHidden();
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

  test("search results dismiss outside and Escape preserves the user's query", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("dashboard-root")).toHaveAttribute("data-url-state-ready", "true");
    const search = page.getByTestId("geography-search");

    await search.fill("Toronto");
    await expect(page.getByRole("option").filter({ hasText: "3520005" })).toBeVisible();
    await page.getByRole("heading", { name: "GTA housing data map" }).click();
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await expect(search).toHaveValue("Toronto");

    await search.focus();
    await expect(page.getByRole("option").filter({ hasText: "3520005" })).toBeVisible();
    await search.press("Escape");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await expect(search).toHaveValue("Toronto");
  });

  test("a slower stale search response cannot replace newer results", async ({ page }) => {
    await page.addInitScript(() => {
      const nativeFetch = window.fetch.bind(window);
      window.fetch = async (input, init) => {
        const requestUrl =
          typeof input === "string"
            ? input
            : input instanceof Request
              ? input.url
              : input.toString();
        if (!requestUrl.includes("/api/geographies?")) {
          return nativeFetch(input, init);
        }

        const query = new URL(requestUrl).searchParams.get("search") ?? "";
        const isOldQuery = query === "old";
        return {
          ok: true,
          status: 200,
          json: () =>
            new Promise((resolve) => {
              window.setTimeout(
                () =>
                  resolve({
                    items: [
                      {
                        id: isOldQuery ? 1 : 2,
                        geoid: isOldQuery ? "old-id" : "new-id",
                        name: isOldQuery ? "Old result" : "New result",
                        type: "municipality",
                        county: null,
                        state: "ON",
                        bbox: [-79.5, 43.5, -79.4, 43.6],
                        geometry_source: "Test fixture"
                      }
                    ]
                  }),
                isOldQuery ? 650 : 40
              );
            })
        } as Response;
      };
    });
    await blockExternalMapAssets(page);
    await page.goto("/");

    const search = page.getByTestId("geography-search");
    await search.fill("old");
    await page.waitForTimeout(230);
    await search.fill("new");
    await expect(page.getByRole("option").filter({ hasText: "New result" })).toBeVisible();
    await page.waitForTimeout(700);
    await expect(page.getByRole("option").filter({ hasText: "New result" })).toBeVisible();
    await expect(page.getByRole("option").filter({ hasText: "Old result" })).toHaveCount(0);
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
    await expect(optgroups).toHaveCount(3);
    await expect(optgroups.nth(0)).toHaveAttribute("label", "Census Profile");
    await expect(optgroups.nth(1)).toHaveAttribute("label", "CMHC Rental Market");
    await expect(optgroups.nth(2)).toHaveAttribute("label", "Transit Access");

    await select.selectOption("vacancy_rate");
    await expect(page.getByText("Vacancy rate by municipality")).toBeVisible();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "vacancy_rate");

    await select.selectOption("transit_score");
    await expect(page.getByText("Transit access score by census tract")).toBeVisible();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "transit_score");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-geography-type", "census_tract");
    await expect(page.getByRole("button", { name: "Municipalities" })).toBeDisabled();
    await expect(page.getByText("Transit metrics use census tracts.")).toBeVisible();
    const coverage = page.getByTestId("transit-coverage-notice");
    await expect(coverage).toContainText("Partial transit snapshot");
    await expect(coverage).toContainText("TTC");
    await expect(coverage).toContainText("Not included: Brampton Transit");
    await expect(page.getByText(/all GTA transit agencies/i)).toHaveCount(0);
    const comparisonPanel = page.getByTestId("comparison-panel");
    await expect(comparisonPanel.getByText(/^Transit snapshot \d{4}-\d{2}-\d{2}$/)).toBeVisible();
    await expect(comparisonPanel.locator("caption")).toContainText(
      /from the transit snapshot packaged \d{4}-\d{2}-\d{2}/
    );
    await expect(comparisonPanel.getByRole("columnheader")).toHaveCount(2);
    await expect(comparisonPanel.getByRole("columnheader", { name: "Ratio" })).toHaveCount(0);
  });

  test("transit overlay is lazy, reports failure, and retries successfully", async ({ page }) => {
    await blockExternalMapAssets(page);
    let transitRequests = 0;
    let failTransit = true;
    await page.route(`${API_BASE}/api/transit-routes`, async (route) => {
      transitRequests += 1;
      if (failTransit) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ type: "FeatureCollection", features: [] })
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: [[-79.4, 43.7], [-79.3, 43.8]]
              },
              properties: {
                agency: "TTC",
                route_name: "1",
                route_long_name: "Yonge–University",
                route_type: "Subway",
                color: "#C23030",
                transit_category: "ttc_subway"
              }
            }
          ]
        })
      });
    });

    await page.goto("/");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-feature-count", "25");
    expect(transitRequests).toBe(0);

    const transitButton = page.getByRole("button", { name: "Transit", exact: true });
    await transitButton.click();
    await expect(transitButton).toHaveAttribute("aria-expanded", "true");
    await expect(transitButton).not.toHaveAttribute("aria-pressed", /.*/);
    await expect(
      page.getByRole("alert").filter({ hasText: "Transit lines could not be loaded" }),
    ).toBeVisible();
    expect(transitRequests).toBe(1);

    failTransit = false;
    await page.getByRole("button", { name: "Retry transit lines" }).click();
    await expect(page.getByRole("checkbox", { name: "Subway" })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: "GO Transit" })).toBeChecked();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-transit-status", "loaded");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-transit-feature-count", "1");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-transit-visible", "true");
    await page.getByRole("button", { name: "Browse route details (1)" }).click();
    await expect(page.locator("#transit-route-details")).toContainText(
      "TTC — Route 1 — Yonge–University"
    );
    expect(transitRequests).toBe(2);

    await page.getByRole("button", { name: "Dark theme" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.getByRole("checkbox", { name: "Subway" })).toBeChecked();
  });

  test("basemap attribution remains visible", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");

    const attribution = page.locator(".maplibregl-ctrl-attrib");
    await expect(attribution).toBeVisible({ timeout: 30000 });
    await expect(attribution).toContainText("OpenStreetMap");
    await expect(attribution).toContainText("OpenFreeMap");
    expect(
      await page.locator("canvas.maplibregl-canvas").getAttribute("aria-label")
    ).toBeTruthy();
  });

  test("theme switching keeps civic layers above every basemap fill and line", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");

    const mapHost = page.getByTestId("map-canvas-host");
    await expect(mapHost).toHaveAttribute("data-civic-layer-order", "valid");
    await expect(mapHost).toHaveAttribute("data-map-theme", "light");

    const themeToggle = page.getByRole("button", { name: "Dark theme" });
    await themeToggle.click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(themeToggle).toHaveAttribute("aria-pressed", "true");
    await expect(mapHost).toHaveAttribute("data-map-theme", "dark");
    await expect(mapHost).toHaveAttribute("data-civic-layer-order", "valid");

    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(themeToggle).toBeVisible();
    await expect(mapHost).toHaveAttribute("data-map-theme", "dark");
    await expect(mapHost).toHaveAttribute("data-civic-layer-order", "valid");
  });

  test("theme switching still completes when browser storage is unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(Storage.prototype, "setItem", {
        configurable: true,
        value: () => {
          throw new DOMException("Storage blocked", "SecurityError");
        }
      });
    });
    await blockExternalMapAssets(page);
    await page.goto("/");

    const themeToggle = page.getByRole("button", { name: "Dark theme" });
    await themeToggle.click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(themeToggle).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => page.locator("html").getAttribute("class")).not.toContain(
      "theme-changing"
    );
  });

  test("year selector is disabled for Census metrics and enabled for CMHC metrics", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const censusYearSelect = page.getByLabel("Census data year", { exact: true });
    await expect(censusYearSelect).toBeDisabled();

    await page.getByLabel("Map metric").selectOption("vacancy_rate");
    const yearSelect = page.getByLabel("CMHC data year", { exact: true });
    await expect(yearSelect).toBeEnabled();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "vacancy_rate");
    await expect
      .poll(() => yearSelect.locator("option").count())
      .toBeGreaterThan(1);

    const yearOptions = await yearSelect.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value)
    );
    expect(yearOptions.length).toBeGreaterThan(1);
    const earliestYear = yearOptions[0];
    const latestYear = yearOptions.at(-1)!;

    await yearSelect.selectOption(earliestYear);
    await expect.poll(() => new URL(page.url()).searchParams.get("year")).toBe(earliestYear);
    await yearSelect.selectOption(latestYear);
    await expect.poll(() => new URL(page.url()).searchParams.get("year")).toBe(latestYear);

    await page.goBack();
    await expect(yearSelect).toHaveValue(earliestYear);
    await expect(page.getByTestId("map-panel")).toContainText(`CMHC ${earliestYear}`);
    await page.goForward();
    await expect(yearSelect).toHaveValue(latestYear);
    await expect(page.getByTestId("map-panel")).toContainText(`CMHC ${latestYear}`);

    await page.getByLabel("Map metric").selectOption("rent_burden_pct");
    await expect(page.getByLabel("Census data year", { exact: true })).toBeDisabled();
  });

  test("a shared URL restores state, preserves unrelated parts, and supports Back", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto(
      "/?campaign=civic&level=census_tract&metric=population&geoid=5350001.00#comparison"
    );

    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30_000 });
    await expect(map).toHaveAttribute("data-metric", "population");
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto census tract 0001.00");
    await expect(page.getByTestId("geography-search")).toHaveValue(
      "Toronto census tract 0001.00"
    );

    let current = new URL(page.url());
    expect(current.searchParams.get("campaign")).toBe("civic");
    expect(current.searchParams.get("level")).toBe("census_tract");
    expect(current.searchParams.get("metric")).toBe("population");
    expect(current.searchParams.get("geoid")).toBe("5350001.00");
    expect(current.searchParams.has("year")).toBe(false);
    expect(current.hash).toBe("#comparison");

    await page.getByLabel("Map metric").selectOption("median_income");
    await expect(map).toHaveAttribute("data-metric", "median_income");
    expect(new URL(page.url()).searchParams.get("metric")).toBe("median_income");

    await page.goBack();
    await expect(map).toHaveAttribute("data-metric", "population");
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");
    current = new URL(page.url());
    expect(current.searchParams.get("campaign")).toBe("civic");
    expect(current.hash).toBe("#comparison");

    await page.goForward();
    await expect(map).toHaveAttribute("data-metric", "median_income");
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");

    await page.getByRole("button", { name: "Clear selected geography" }).click();
    await expect(map).toHaveAttribute("data-selected-geoid", "");
    await expect.poll(() => new URL(page.url()).searchParams.has("geoid")).toBe(false);

    await page.goBack();
    await expect(map).toHaveAttribute("data-selected-geoid", "5350001.00");
    await page.goForward();
    await expect(map).toHaveAttribute("data-selected-geoid", "");
  });

  test("invalid shared parameters are sanitized without losing unrelated state", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/?keep=yes&level=ward&metric=unknown&year=9999&geoid=bad#map");
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "municipality"
    );

    await expect
      .poll(() => {
        const url = new URL(page.url());
        return [
          url.searchParams.get("keep"),
          url.searchParams.get("level"),
          url.searchParams.get("metric"),
          url.searchParams.has("year"),
          url.searchParams.has("geoid"),
          url.hash
        ].join("|");
      })
      .toBe("yes|municipality|rent_burden_pct|false|false|#map");
    const current = new URL(page.url());
    expect(current.searchParams.get("keep")).toBe("yes");
    expect(current.searchParams.get("level")).toBe("municipality");
    expect(current.searchParams.get("metric")).toBe("rent_burden_pct");
    expect(current.searchParams.has("year")).toBe(false);
    expect(current.searchParams.has("geoid")).toBe(false);
    expect(current.hash).toBe("#map");
  });

  test("a CMHC deep link recovers when year catalog metadata is missing", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.route(`${API_BASE}/api/map-data**`, async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("metric") !== "housing_starts_total") {
        await route.continue();
        return;
      }

      const response = await route.fetch();
      const payload = (await response.json()) as {
        metadata: { available_years?: number[]; cmhc_year?: number };
      };
      delete payload.metadata.available_years;
      await route.fulfill({ response, json: payload });
    });

    await page.goto(
      "/?level=census_tract&metric=housing_starts_total&year=1901&geoid=5350017.01"
    );
    const year = page.getByLabel("CMHC data year", { exact: true });
    await expect(year).toBeEnabled({ timeout: 30_000 });
    await expect(year).toHaveValue("2025");
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-selected-geoid",
      "5350017.01"
    );
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto census tract 0017.01");
    await expect(page.getByTestId("comparison-panel")).toContainText(
      "Toronto census tract 0017.01"
    );
    expect(new URL(page.url()).searchParams.get("year")).toBe("2025");
  });

  test("CMHC catalog drift keeps the selector, map, and URL on one valid year", async ({ page }) => {
    await blockExternalMapAssets(page);
    let catalogShrunk = false;
    await page.route(`${API_BASE}/api/map-data**`, async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("metric") !== "vacancy_rate") {
        await route.continue();
        return;
      }

      const response = await route.fetch();
      const payload = (await response.json()) as {
        metadata: { available_years?: number[]; cmhc_year?: number };
      };
      payload.metadata.available_years = catalogShrunk ? [2023] : [2018, 2023];
      payload.metadata.cmhc_year = 2023;
      await route.fulfill({ response, json: payload });
    });

    await page.goto("/?level=municipality&metric=vacancy_rate&year=2023");
    const year = page.getByLabel("CMHC data year", { exact: true });
    await expect(year).toHaveValue("2023", { timeout: 30_000 });
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-metric", "vacancy_rate");
    await expect(year).toBeEnabled();
    await expect(year.locator("option")).toHaveCount(2);

    catalogShrunk = true;
    await year.selectOption("2018");

    await expect(year).toHaveValue("2023");
    await expect(page.getByTestId("map-panel")).toContainText("CMHC 2023");
    await expect.poll(() => new URL(page.url()).searchParams.get("year")).toBe("2023");
  });

  test("navigation away from a pending CMHC deep link cannot be overwritten", async ({ page }) => {
    await blockExternalMapAssets(page);
    let signalRequestStarted!: () => void;
    const requestStarted = new Promise<void>((resolve) => {
      signalRequestStarted = resolve;
    });
    await page.route(`${API_BASE}/api/map-data**`, async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("metric") !== "housing_starts_total") {
        await route.continue();
        return;
      }
      signalRequestStarted();
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.continue().catch(() => undefined);
    });

    await page.goto("/?level=census_tract&metric=housing_starts_total&year=1901");
    await requestStarted;
    await page.evaluate(() => {
      window.history.pushState({}, "", "/?keep=navigation&level=municipality&metric=population");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "municipality");
    await expect(map).toHaveAttribute("data-metric", "population");
    await page.waitForTimeout(750);
    await expect(map).toHaveAttribute("data-metric", "population");
    await expect.poll(() => {
      const url = new URL(page.url());
      return `${url.searchParams.get("keep")}|${url.searchParams.get("metric")}|${url.searchParams.has("year")}`;
    }).toBe("navigation|population|false");
  });

  test("comparison keeps requested areas when a metric is unavailable", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByLabel("Map metric").selectOption("vacancy_rate");

    const comparison = page.getByTestId("comparison-panel");
    await expect(comparison).toContainText("default GTA municipalities");
    await expect(comparison.locator("tbody tr")).toHaveCount(5);
    await expect(comparison).toContainText("Not available");
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

    await page.getByLabel("Map metric").selectOption("population_growth_pct");
    const comparisonPanel = page.getByTestId("comparison-panel");
    await expect(comparisonPanel).toContainText("Low confidence — very small 2016 base");
    await expect(comparisonPanel).toContainText(
      "Chart omitted because the available growth values are low confidence"
    );

    const downloadPromise = page.waitForEvent("download");
    await comparisonPanel.getByRole("button", { name: "Export comparison data as CSV" }).click();
    const download = await downloadPromise;
    const downloadPath = await download.path();
    expect(downloadPath).not.toBeNull();
    const csv = await readFile(downloadPath!, "utf8");
    expect(csv).toContain("low_confidence");
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
    const scaleMax = Number(await map.getAttribute("data-scale-max"));
    expect(domainMax).toBeGreaterThan(0);
    expect(domainMax).toBeLessThan(5000);
    expect(scaleMax).toBe(domainMax);
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
    await page.getByLabel("CMHC data year", { exact: true }).selectOption("2023");

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
    const censusSection = panel.locator("[data-section='census']");
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
    await page.getByLabel("CMHC data year", { exact: true }).selectOption("2023");

    // 5320003.01 split from CMHC parent 0003.00 -> allocated value, distinct
    // "est. (CMHC parent tract)" provenance (not "CMHC tract data", not plain "est.").
    await page.getByTestId("geography-search").fill("5320003.01");
    await page.getByRole("option").filter({ hasText: "5320003.01" }).first().click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel.getByTestId("parent-est-flag").first()).toBeVisible();
    await expect(panel).toContainText("CMHC parent tract");
  });

  test("census tract CMHC rent varies by survey zone, not flat per city", async ({ request }) => {
    const response = await request.get(
      `${API_BASE}/api/map-data?metric=average_rent_total&type=census_tract&detail=display`
    );
    expect(response.ok()).toBeTruthy();
    const payload = (await response.json()) as MapPayload;

    expect(payload.metadata.data_quality.metric_status).toBe("mixed");
    expect(payload.metadata.data_quality.label).toContain("municipal fallback");

    const toronto = payload.features.filter((f) => f.properties.name?.includes("Toronto census tract"));
    const values = new Set(toronto.map((f) => (f.properties as Record<string, unknown>).value));
    expect(values.size).toBeGreaterThan(5);
  });

  test("a combined-zone municipality discloses its shared CMHC survey zone", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    // Municipality mode (default). Select a CMHC metric so rental data loads.
    await page.getByLabel("Map metric").selectOption("vacancy_rate");
    await page.getByTestId("geography-search").fill("Richmond Hill");
    await page.getByRole("option").filter({ hasText: "Richmond Hill" }).first().click();

    const panel = page.getByTestId("detail-panel");
    await expect(panel.getByTestId("survey-zone-note")).toBeVisible();
    await expect(panel.getByTestId("survey-zone-note")).toContainText("Richmond Hill / Vaughan / King");
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

  test("CMHC rate metric in tract mode shows survey-zone badge", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    await page.getByLabel("Map metric").selectOption("average_rent_total");
    await expect(map).toHaveAttribute("data-metric", "average_rent_total");

    const badge = page.getByTestId("data-quality-badge").first();
    await expect(badge).toContainText(/survey-zone/i);
    await expect(badge).not.toContainText(/allocation/i);
  });

  test("metric dropdown does not include unsupported metrics", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const select = page.getByLabel("Map metric");
    const options = select.locator("option");
    const texts = await options.allTextContents();
    expect(texts).not.toContain("Turnover rate");
    expect(texts).not.toContain("Availability rate");
  });

  test("search with no matches shows a no-results message", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("dashboard-root")).toHaveAttribute("data-url-state-ready", "true");
    const search = page.getByTestId("geography-search");
    await search.click();
    await search.fill("zzzznomatch");
    await expect(page.getByTestId("search-empty")).toContainText("No", { timeout: 5000 });
  });

  test("API failure is visible and retry restores the map", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.route(`${API_BASE}/api/summary**`, (route) => route.abort("failed"));
    let failMap = true;
    await page.route(`${API_BASE}/api/map-data**`, async (route) => {
      if (failMap) {
        await route.abort("failed");
      } else {
        await route.continue();
      }
    });

    await page.goto("/");
    await expect(page.getByText("Map data is unavailable")).toBeVisible();
    await expect(page.getByTestId("summary-panel")).toContainText("GTA data unavailable");
    await expect(page.getByTestId("summary-panel")).not.toContainText("0 GTA municipalities");

    const globalRetry = page.getByTestId("api-error").getByRole("button", { name: "Retry" });
    await globalRetry.focus();
    expect(await globalRetry.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe(
      "none"
    );
    const mapRetry = page.getByRole("button", { name: "Retry map", exact: true });
    await mapRetry.focus();
    expect(await mapRetry.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe(
      "none"
    );

    failMap = false;
    await mapRetry.click();
    await expect(page.getByText("Map data is unavailable")).toBeHidden({ timeout: 30000 });
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-feature-count", "25");
  });

  test("search network failures are not reported as no matches", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.route(`${API_BASE}/api/geographies**`, (route) => route.abort("failed"));
    await page.goto("/");
    await expect(page.getByTestId("dashboard-root")).toHaveAttribute("data-url-state-ready", "true");
    await page.getByTestId("geography-search").fill("Toronto");

    await expect(page.getByTestId("search-error")).toContainText("temporarily unavailable");
    await expect(page.getByTestId("search-empty")).toHaveCount(0);
  });

  test("mobile details control exposes its expanded state", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await blockExternalMapAssets(page);
    await page.goto("/");

    const summaryBox = await page.getByTestId("summary-panel").boundingBox();
    const mapBox = await page.getByTestId("map-panel").boundingBox();
    expect(summaryBox).not.toBeNull();
    expect(mapBox).not.toBeNull();
    expect(summaryBox?.y).toBeLessThan(mapBox?.y ?? 0);

    const toggle = page.getByTestId("details-toggle");
    const panel = page.locator("#selected-geography-details");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAttribute("aria-controls", "selected-geography-details");
    await expect(panel).toBeHidden();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(panel).toBeVisible();
  });

  test("keyboard focus is visibly indicated on primary controls", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("dashboard-root")).toHaveAttribute("data-url-state-ready", "true");

    const metric = page.getByLabel("Map metric");
    await metric.focus();
    await expect(metric).toBeFocused();
    const metricShadow = await metric.evaluate((element) => getComputedStyle(element).boxShadow);
    expect(metricShadow).not.toBe("none");

    const theme = page.getByRole("button", { name: "Dark theme" });
    await theme.focus();
    await expect(theme).toBeFocused();
    const themeShadow = await theme.evaluate((element) => getComputedStyle(element).boxShadow);
    expect(themeShadow).not.toBe("none");

    const search = page.getByTestId("geography-search");
    await search.fill("Toronto");
    const searchOption = page.locator("#geography-search-results").getByRole("option").first();
    await expect(searchOption).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(searchOption).toBeFocused();
    expect(await searchOption.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe(
      "none"
    );

    await search.fill("5");
    const resultList = page.locator("#geography-search-results");
    await expect(resultList.getByRole("option")).toHaveCount(8);
    for (let index = 0; index < 8; index += 1) {
      await page.keyboard.press("ArrowDown");
    }
    const activeResultId = await search.getAttribute("aria-activedescendant");
    expect(activeResultId).toBeTruthy();
    const activeResult = page.locator(`#${activeResultId}`);
    await expect(activeResult).toHaveAttribute("aria-selected", "true");
    expect(
      await activeResult.evaluate((element) => {
        const optionBounds = element.getBoundingClientRect();
        const listBounds = element.parentElement?.getBoundingClientRect();
        return Boolean(
          listBounds &&
            optionBounds.top >= listBounds.top - 1 &&
            optionBounds.bottom <= listBounds.bottom + 1
        );
      })
    ).toBe(true);

    const exportButton = page.getByRole("button", { name: "Export comparison data as CSV" });
    await exportButton.focus();
    expect(await exportButton.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe(
      "none"
    );
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

  test("selecting Toronto via search sets map selected state", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    await page.getByTestId("geography-search").fill("Toronto");
    await page.getByRole("option").filter({ hasText: "3520005" }).click();

    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
    // After selection animation settles, the map should still show data
    await expect(map).toHaveAttribute("data-feature-count", "25");
  });

  test("selecting a census tract sets map selected state", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Census tracts" }).click();
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30000 });

    await page.getByTestId("geography-search").fill("5350092.00");
    const result = page.getByRole("option").filter({ hasText: "5350092.00" });
    await expect(result).toHaveCount(1);
    await result.click();

    await expect(map).toHaveAttribute("data-selected-geoid", "5350092.00");
    await expect(page.getByTestId("detail-panel")).toContainText("census tract");
  });

  test("map exposes an accessible region label", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("role", "region");
    await expect(map).toHaveAttribute("aria-label", /map of .+ by/i);
  });

  test("no critical or serious accessibility violations on initial load", async ({ page }) => {
    await blockExternalMapAssets(page);
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");
    const results = await new AxeBuilder({ page })
      .exclude("[data-testid='map-canvas-host']")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    );
    expect(serious, `Accessibility violations: ${JSON.stringify(serious, null, 2)}`).toHaveLength(0);
  });

  test("no critical or serious accessibility violations in a populated mobile transit state", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await blockExternalMapAssets(page);
    await page.goto("/");
    await page.getByLabel("Map metric").selectOption("transit_score");
    await expect(page.getByTestId("transit-coverage-notice")).toContainText(
      "Partial transit snapshot"
    );
    await page.getByTestId("geography-search").fill("5350001.00");
    await page.getByRole("option").filter({ hasText: "5350001.00" }).click();

    const detailsToggle = page.getByTestId("details-toggle");
    await expect(detailsToggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#selected-geography-details")).toBeVisible();
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto census tract 0001.00");
    await page.getByRole("button", { name: "What is Transit access score?" }).first().click();
    await expect(page.getByRole("tooltip")).toBeVisible();

    const lightResults = await new AxeBuilder({ page })
      .exclude("[data-testid='map-canvas-host']")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const lightSerious = lightResults.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious"
    );
    expect(
      lightSerious,
      `Light-theme accessibility violations: ${JSON.stringify(lightSerious, null, 2)}`
    ).toHaveLength(0);

    await page.getByRole("button", { name: "Dark theme" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    const transitButton = page.getByRole("button", { name: "Transit", exact: true });
    await transitButton.click();
    await expect(transitButton).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#transit-layer-panel")).toBeVisible();
    const darkResults = await new AxeBuilder({ page })
      .exclude("[data-testid='map-canvas-host']")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const darkSerious = darkResults.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious"
    );
    expect(
      darkSerious,
      `Dark-theme accessibility violations: ${JSON.stringify(darkSerious, null, 2)}`
    ).toHaveLength(0);
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
  await page.route("https://tiles.openfreemap.org/**", async (route) => {
    if (new URL(route.request().url()).pathname.startsWith("/styles/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          version: 8,
          glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
          sources: {
            "openfreemap-attribution": {
              type: "geojson",
              data: { type: "FeatureCollection", features: [] },
              attribution: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap"
            }
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#eef2ed" }
            },
            {
              id: "early-symbol",
              type: "symbol",
              source: "openfreemap-attribution",
              layout: { "text-field": "" }
            },
            {
              id: "openfreemap-attribution-layer",
              type: "circle",
              source: "openfreemap-attribution",
              paint: { "circle-opacity": 0 }
            },
            {
              id: "top-label",
              type: "symbol",
              source: "openfreemap-attribution",
              layout: { "text-field": "" }
            }
          ]
        })
      });
      return;
    }
    await route.abort();
  });
}
