import { expect, test, type Page } from "@playwright/test";

test.describe("critical cross-browser journeys", () => {
  test.beforeEach(async ({ page }) => {
    await blockExternalMapAssets(page);
  });

  test("loads the live data dashboard and changes geography level", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: "Greater Toronto Housing Affordability Explorer" })
    ).toBeVisible();
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-feature-count", "25");
    await expect(page.getByTestId("comparison-panel")).toContainText("Toronto");

    await page.getByRole("button", { name: "Census tracts" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute(
      "data-geography-type",
      "census_tract",
      { timeout: 30_000 }
    );
    await expect(page.getByTestId("summary-panel")).toContainText("1,334 GTA census tracts");
  });

  test("supports search, selection, theme, and browser history", async ({ page }) => {
    await page.goto("/?campaign=compatibility#dashboard");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    await page.getByTestId("geography-search").fill("Toronto");
    await page.getByRole("option").filter({ hasText: "3520005" }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
    await expect(page).toHaveURL(/geoid=3520005/);

    await page.getByRole("button", { name: "Dark theme" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    await page.goBack();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "");
    expect(new URL(page.url()).searchParams.get("campaign")).toBe("compatibility");
    expect(new URL(page.url()).hash).toBe("#dashboard");

    await page.goForward();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
  });

  test("keeps the mobile layout usable without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByTestId("summary-panel")).toContainText("25 GTA municipalities");

    const summaryBox = await page.getByTestId("summary-panel").boundingBox();
    const mapBox = await page.getByTestId("map-panel").boundingBox();
    expect(summaryBox).not.toBeNull();
    expect(mapBox).not.toBeNull();
    expect(summaryBox!.y).toBeLessThan(mapBox!.y);

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);

    const detailsToggle = page.getByTestId("details-toggle");
    await expect(detailsToggle).toBeVisible();
    await detailsToggle.click();
    await expect(detailsToggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#selected-geography-details")).toBeVisible();
  });
});

async function blockExternalMapAssets(page: Page) {
  await page.route("https://tiles.openfreemap.org/**", async (route) => {
    if (new URL(route.request().url()).pathname.startsWith("/styles/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          version: 8,
          glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
          sources: {
            attribution: {
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
              id: "labels",
              type: "symbol",
              source: "attribution",
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
