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
      metric_status: "official" | "estimated";
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
    await expect(
      page.getByTestId("data-quality-badge").filter({ hasText: "Estimated tract metrics" })
    ).toHaveCount(2);
    await expect(map).toHaveAttribute("data-geography-type", "census_tract");
    await expect(map).toHaveAttribute("data-feature-count", "1334");
    await expect(page.getByTestId("detail-panel")).toContainText("estimated tract metrics");

    await page.getByTestId("geography-search").fill("5350001.00");
    const tractResult = page.getByRole("button").filter({ hasText: "5350001.00" });
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
    await expect(map).toContainText("Value range");
    await expect(map).toContainText("31.6");
    await expect(map).toContainText("51.2");

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
    const torontoResult = page.getByRole("button").filter({ hasText: "3520005" });
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
    await expect(map).toContainText("141K");

    await page.getByLabel("Map metric").selectOption("population_growth_pct");
    await expect(page.getByText("Population growth by municipality")).toBeVisible();
    await expect(map).toHaveAttribute("data-metric", "population_growth_pct");
    await expect(map).toHaveAttribute("data-domain-max", "44.4");
    await expect(map).toContainText("44.4");
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
