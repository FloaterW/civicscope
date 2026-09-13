import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const selectedView = "/?level=census_tract&metric=rent_burden_pct&geoid=5350400.16&compare=5350403.16%2C5350403.05";

for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
  test(`desktop ${viewport.width}: expanding topics preserves map and comparison layout`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(selectedView);
    const panel = page.getByTestId("detail-panel");
    const scroll = page.getByTestId("detail-panel-scroll");
    const map = page.getByTestId("map-panel");
    await expect(panel).toContainText("Markham census tract 0400.16");
    await expect(page.getByTestId("comparison-panel").locator("tbody tr")).toHaveCount(2);
    const originalMap = await map.boundingBox();
    const comparisonTop = () => page.getByTestId("comparison-panel").evaluate(el => el.getBoundingClientRect().top + window.scrollY);
    const originalComparisonTop = await comparisonTop();
    for (const topic of ["population", "rental", "construction", "transit", "sources"]) {
      await panel.locator(`[data-topic="${topic}"] summary`).click();
      await expect(panel.locator(`[data-topic="${topic}"]`)).toHaveAttribute("open", "");
      expect((await map.boundingBox())!.height).toBeCloseTo(originalMap!.height, 0);
      expect((await panel.boundingBox())!.height).toBeCloseTo(originalMap!.height, 0);
      expect(await comparisonTop()).toBeCloseTo(originalComparisonTop, 0);
    }
    await expect(panel.locator("details[open]")).toHaveCount(6);
    expect(await scroll.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    const headerOffset = await page.getByTestId("detail-panel-header").evaluate(el => el.getBoundingClientRect().top - el.parentElement!.getBoundingClientRect().top);
    await scroll.focus();
    await page.keyboard.press("End");
    await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    expect(await page.getByTestId("detail-panel-header").evaluate(el => el.getBoundingClientRect().top - el.parentElement!.getBoundingClientRect().top)).toBeCloseTo(headerOffset, 0);
    await expect(panel.getByRole("button", { name: "Export geography data as CSV" })).toBeVisible();
    expect((await new AxeBuilder({ page }).include('[data-testid="detail-panel"]').analyze()).violations).toEqual([]);
    await page.getByLabel("Map metric", { exact: true }).selectOption("population");
    await expect(panel.locator('[data-active-topic]')).toHaveAttribute("data-topic", "population");
    await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBe(0);
    expect((await map.boundingBox())!.height).toBeCloseTo(originalMap!.height, 0);
  });
}

test("mobile topics use normal page flow without stretching the map", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(selectedView);
  const panel = page.getByTestId("detail-panel");
  await expect(panel).toContainText("Markham census tract 0400.16");
  const mapHeight = (await page.getByTestId("map-panel").boundingBox())!.height;
  const panelHeight = (await panel.boundingBox())!.height;
  for (const topic of ["population", "rental", "construction"]) {
    await panel.locator(`[data-topic="${topic}"] summary`).click();
  }
  expect((await panel.boundingBox())!.height).toBeGreaterThan(panelHeight);
  expect((await page.getByTestId("map-panel").boundingBox())!.height).toBeCloseTo(mapHeight, 0);
  expect(await page.getByTestId("detail-panel-scroll").evaluate(el => getComputedStyle(el).overflowY)).toBe("visible");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
