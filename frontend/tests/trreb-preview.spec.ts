import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Synthetic contract fixtures, deliberately not copied from licensed reports.
const selected = "/?level=municipality&metric=population&geoid=3520005";
const section = (page: Page) => page.locator('details[data-topic="resale"]');

async function mockResale(page: Page, fail: () => boolean = () => false) {
  const requests: string[] = [];
  await page.route("**/api/trreb-preview/**", async route => {
    const url = new URL(route.request().url());
    requests.push(url.pathname + url.search);
    if (fail()) {
      await route.fulfill({ status: 503, json: { detail: "Synthetic outage" } });
      return;
    }
    const geoid = url.pathname.split("/").at(-1);
    const year = url.searchParams.get("year");
    const month = url.searchParams.get("month");
    await route.fulfill({ json: {
      geoid, source_area: geoid === "3520005" ? "City of Toronto" : "Oakville",
      period: month ? `${year}-${month.padStart(2, "0")}` : year,
      period_type: month ? "month" : "year",
      median_price: month ? 654321 : 123456, sales: month ? 12 : 34, property_days: 21,
      source_url: "https://trreb.ca/synthetic-test-report.pdf", source_page: month ? 3 : 5,
      geography_note: "Synthetic reporting-area context; boundary equivalence not certified.",
      vintage_note: "Archived report vintage.",
      warnings: geoid === "3524001" ? [{ area: "Halton Region", field: "sales" }] : []
    } });
  });
  return requests;
}

async function openResale(page: Page) {
  await page.goto(selected);
  await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
  await section(page).locator("summary").first().click();
  await expect(section(page)).toContainText("$123,456");
}

test("lazy request, year/month controls and direct attribution", async ({ page }) => {
  const requests = await mockResale(page);
  await page.goto(selected);
  await expect(section(page)).toBeVisible();
  expect(requests).toHaveLength(0);
  await section(page).locator("summary").first().click();
  await expect(section(page)).toContainText("$123,456");
  await page.getByLabel("Report year", { exact: true }).selectOption("2020");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("1");
  await expect(section(page)).toContainText("January 2020");
  await expect(section(page)).toContainText("$654,321");
  expect(requests.at(-1)).toBe("/api/trreb-preview/3520005?year=2020&month=1");
  await expect(section(page).getByRole("link", { name: "Market Watch, page 3" })).toHaveAttribute("href", "https://trreb.ca/synthetic-test-report.pdf");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("");
  await expect(section(page)).toContainText("January–December 2020");
  await expect(section(page)).toContainText("$123,456");
});

test("outage hides stale values and retry recovers", async ({ page }) => {
  let failing = false;
  await mockResale(page, () => failing);
  await openResale(page);
  failing = true;
  await page.getByLabel("Report year", { exact: true }).selectOption("2024");
  await expect(section(page)).toContainText("Resale statistics are unavailable");
  await expect(section(page)).not.toContainText("$123,456");
  failing = false;
  await section(page).getByRole("button", { name: "Retry resale statistics" }).click();
  await expect(section(page)).toContainText("$123,456");
  await expect(section(page)).toContainText("January–December 2024");
});

test("municipality selection updates context; census tracts have no resale fallback", async ({ page }) => {
  const requests = await mockResale(page);
  await openResale(page);
  await page.getByTestId("geography-search").fill("Oakville");
  await page.getByRole("option").filter({ hasText: "Oakville" }).click();
  await expect(page.getByTestId("detail-panel")).toContainText("Oakville");
  if (!await section(page).getAttribute("open").then(value => value !== null)) {
    await section(page).locator("summary").first().click();
  }
  await expect(section(page)).toContainText("Oakville · January–December 2025");
  await expect(section(page)).toContainText("regional totals do not fully reconcile");
  expect(requests.at(-1)).toContain("/3524001?");
  await page.getByRole("button", { name: "Census tracts", exact: true }).click();
  await expect(section(page)).toHaveCount(0);
});

for (const width of [390, 1440]) {
  test(`keyboard, accessibility and stable map at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockResale(page);
    await page.goto(selected);
    const summary = section(page).locator("summary").first();
    await expect(summary).toBeVisible();
    const before = (await page.getByTestId("map-panel").boundingBox())!.height;
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(section(page)).toContainText("$123,456");
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Report year", { exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Reporting period", { exact: true })).toBeFocused();
    expect((await page.getByTestId("map-panel").boundingBox())!.height).toBeCloseTo(before, 0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).include('details[data-topic="resale"]').analyze()).violations).toEqual([]);
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(section(page)).not.toHaveAttribute("open", "");
  });
}
