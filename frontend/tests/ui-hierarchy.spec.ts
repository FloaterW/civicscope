import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const topics = {
  rent_burden_pct: "census",
  affordability_index: "census",
  median_income: "census",
  median_rent: "census",
  population: "population",
  population_growth_pct: "population",
  vacancy_rate: "rental",
  average_rent_total: "rental",
  housing_starts_total: "construction",
  housing_completions: "construction",
  transit_score: "transit",
  transit_route_count: "transit",
};

for (const level of ["municipality", "census_tract"]) {
  test(`${level}: every dropdown metric opens one relevant, non-duplicated profile`, async ({ page }) => {
    test.setTimeout(90_000);
    const geoid = level === "municipality" ? "3520005" : "5350403.16";
    await page.goto(`/?level=${level}&geoid=${geoid}`);
    const panel = page.getByTestId("detail-panel");
    await expect(panel.locator("[data-selected-metric]")).toBeVisible();
    await expect(page.getByTestId("summary-panel")).toHaveCount(0);
    for (const [metric, topic] of Object.entries(topics)) {
      if (level === "municipality" && topic === "transit") continue;
      await page.getByLabel("Map metric", { exact: true }).selectOption(metric);
      const active = panel.locator("[data-active-topic]");
      await expect(active).toHaveCount(1);
      await expect(active).toHaveAttribute("data-topic", topic);
      await expect(panel.locator("details").first()).toHaveAttribute("data-topic", topic);
      await expect(active).toHaveAttribute("open", "");
      await expect(panel.locator(`[data-metric="${metric}"]`)).toHaveCount(1);
      await expect(panel.locator("[data-selected-metric]")).toHaveAttribute("data-metric", metric);
      await expect(panel.locator("[data-selected-metric]")).toBeVisible();
      await expect(panel.locator("details[open]")).toHaveCount(1);
      await expect(page.getByTestId("summary-panel")).toHaveCount(0);
    }
    const sources = panel.locator('[data-topic="sources"]');
    await sources.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(sources).toHaveAttribute("open", "");
    await expect(sources).toContainText("CSV exports include the full profile");
    const accessibility = await new AxeBuilder({ page }).include('[data-testid="detail-panel"]').analyze();
    expect(accessibility.violations).toEqual([]);
    await panel.getByRole("button", { name: "Clear selected geography" }).click();
    await expect(page.getByTestId("summary-panel")).toContainText(level === "municipality" ? "25 GTA municipalities" : "1,334 GTA census tracts");
  });
}

test("desktop controls share one baseline and 44px outer height", async ({ page }) => {
  await page.goto("/?metric=average_rent_total&year=2023&geoid=3520005");
  await expect(page.getByTestId("detail-panel").locator("[data-selected-metric]")).toBeVisible();
  for (const width of [1280, 1365, 1600, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    const boxes = await page.getByTestId("dashboard-toolbar").evaluate((toolbar) => {
      const search = toolbar.querySelector<HTMLInputElement>('input')!;
      const geography = toolbar.querySelector<HTMLElement>('[role="group"]')!;
      const metric = toolbar.querySelector<HTMLElement>('[aria-label="Map metric"]')!.parentElement!;
      const year = toolbar.querySelector<HTMLElement>('[aria-label="CMHC data year"]')!.parentElement!;
      const theme = toolbar.querySelector<HTMLElement>('[aria-label="Dark theme"]')!;
      return [search, geography, metric, year, theme].map((element) => {
        const { y, height } = element.getBoundingClientRect();
        return { y, height };
      });
    });
    expect(boxes.map(({ height }) => height)).toEqual([44, 44, 44, 44, 44]);
    expect(new Set(boxes.map(({ y }) => y)).size).toBe(1);
  }
});

test("selected profile is usable without overflow at phone, tablet and desktop sizes", async ({ page }) => {
  await page.goto("/?level=census_tract&metric=rent_burden_pct&geoid=5350403.16");
  const panel = page.getByTestId("detail-panel");
  await expect(panel.locator("[data-selected-metric]")).toBeVisible();
  for (const width of [320, 375, 390, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(panel).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content, `Overflow at ${width}px`).toBeLessThanOrEqual(dimensions.client);
    const heights = await panel.locator('[data-active-topic] [data-metric]').evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect().height));
    expect(new Set(heights).size).toBe(1);
    if (width === 375 || width === 1440) {
      await page.screenshot({ path: test.info().outputPath(`profile-${width}.png`), fullPage: true });
    }
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "Dark theme" }).click();
  const accessibility = await new AxeBuilder({ page }).include('[data-testid="detail-panel"]').analyze();
  expect(accessibility.violations).toEqual([]);
  await expect(page.getByTestId("map-canvas-host")).toHaveAttribute("data-map-theme", "dark");
  await panel.screenshot({ path: test.info().outputPath("profile-mobile-dark.png") });
  await panel.locator('[data-topic="rental"] summary').click();
  await expect(panel.locator('[data-topic="rental"]')).toHaveAttribute("open", "");
  await page.getByLabel("Map metric", { exact: true }).selectOption("housing_starts_total");
  await expect(panel.locator('details[open]')).toHaveCount(1);
  await expect(panel.locator('[data-active-topic]')).toHaveAttribute("data-topic", "construction");
});

test("unpublished selected rental value is explicit, not hidden or shown as zero", async ({ page }) => {
  await page.route("**/api/map-data?**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const feature of data.features) {
      if (feature.properties.geoid === "5350403.16" && feature.properties.cmhc_metrics) {
        feature.properties.cmhc_metrics.vacancy_rate = null;
      }
    }
    await route.fulfill({ response, json: data });
  });
  await page.goto("/?level=census_tract&metric=vacancy_rate&geoid=5350403.16&year=2023");
  const selected = page.getByTestId("detail-panel").locator('[data-selected-metric]');
  await expect(selected).toContainText("Not published");
  await expect(selected).toContainText("Unavailable for this area/year");
  await expect(selected).not.toContainText("0.0%");
});

test("suppressed housing components do not produce fabricated totals or tenure shares", async ({ page }) => {
  await page.route("**/api/map-data?**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const feature of data.features) {
      if (feature.properties.geoid === "5350403.16") {
        Object.assign(feature.properties.metrics, {
          dwellings_total: 100,
          owner_households: 50,
          renter_households: null,
          dwellings_single_detached: 20,
          dwellings_semi_detached: null,
          dwellings_row_house: 10,
        });
      }
    }
    await route.fulfill({ response, json: data });
  });
  await page.goto("/?level=census_tract&geoid=5350403.16");
  const stock = page.getByTestId("detail-panel").locator('[data-topic="stock"]');
  await stock.locator("summary").click();
  await expect(stock.getByText("Owner", { exact: true }).locator("..")).toContainText("--");
  await expect(stock.getByText("Owner", { exact: true }).locator("..")).not.toContainText("100.0%");
  await expect(stock.getByText("Ground-oriented", { exact: true }).locator("..")).toContainText("Not available");
});
