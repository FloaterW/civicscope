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

  for (const metric of ["population", "population_growth_pct"]) {
    test(`comparison bar values fit inside the chart at desktop and mobile widths: ${metric}`, async ({ page }, testInfo) => {
      if (metric === "population_growth_pct") {
        // Exercise both signs, including a negative bar at the lower axis bound.
        // Population retains the actual Toronto payload that exposed the defect.
        await page.route("**/api/compare?**", async (route) => {
          const response = await route.fetch();
          const payload = await response.json();
          payload.items.forEach((item: { metrics: { population_growth_pct: number; data_quality: Record<string, string> } }, index: number) => {
            item.metrics.population_growth_pct = [-20, -2.5, 1, 2.5, 20][index];
            item.metrics.data_quality.population_growth_pct = "derived";
          });
          await route.fulfill({ response, json: payload });
        });
      }
      await page.goto(`/?level=municipality&metric=${metric}&geoid=3520005`);
      const panel = page.getByTestId("comparison-panel");
      await expect(panel).toContainText(metric === "population" ? "2,794,356" : "-20.0%");

      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await panel.scrollIntoViewIfNeeded();
        // Labels are mounted after Recharts finishes its bar animation. Require
        // actual nonzero bars and all five labels before checking their bounds.
        await expect(panel.locator(".recharts-label-list .recharts-label")).toHaveCount(5);
        if (metric === "population_growth_pct") {
          await expect(panel.locator(".recharts-label-list")).toContainText("-20.0%");
        }
        await expect.poll(async () => panel.evaluate((element) => {
          const svg = element.querySelector("svg.recharts-surface")!;
          const bounds = svg.getBoundingClientRect();
          const container = element.querySelector(".recharts-responsive-container")!.getBoundingClientRect();
          const bars = [...svg.querySelectorAll("path.recharts-rectangle")];
          const labels = [...svg.querySelectorAll(".recharts-label-list .recharts-label")];
          // Do not accept old-width SVG geometry before ResizeObserver catches up.
          const resized = Math.abs(bounds.width - container.width) <= 1 &&
            bounds.left >= container.left - 1 && bounds.right <= container.right + 1;
          return resized && bars.length === 5 && labels.length === 5 && bars.every((bar) => {
            const box = bar.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
          }) && labels.every((label) => {
            const box = label.getBoundingClientRect();
            return box.width > 0 && box.height > 0 && box.top >= bounds.top &&
              box.bottom <= bounds.bottom && box.left >= bounds.left && box.right <= bounds.right;
          });
        })).toBe(true);
        await panel.screenshot({ path: testInfo.outputPath(`comparison-labels-${width}.png`) });
      }
    });
  }
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
