import { expect, test } from "@playwright/test";
import archive from "../data/trreb-resale-2020-2025.json";

test("real Vercel route returns all 25 municipalities at both archive endpoints", async ({ request }) => {
  for (const row of archive.observations.filter(item => ["2020-01", "2025"].includes(item.period))) {
    const query = row.period === "2025" ? "year=2025" : "year=2020&month=1";
    const response = await request.get(`/api/trreb-archive/resale/${row.geoid}?${query}`);
    expect(response.status()).toBe(200);
    expect(response.headers()["cache-control"]).toBe("no-store");
    expect(await response.json()).toMatchObject(row);
  }
  expect((await request.get("/api/trreb-archive/resale/5350400.16?year=2025")).status()).toBe(404);
  expect((await request.get("/api/trreb-archive/resale/3520005?year=2026")).status()).toBe(422);
  expect((await request.post("/api/trreb-archive/resale/3520005", { data: {} })).status()).toBe(405);
});

test("real archive works through the dashboard on desktop and narrow mobile", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const responses: string[] = [];
  page.on("response", response => {
    if (response.url().includes("/api/trreb-archive/")) responses.push(response.url());
  });
  // Keep this archive journey independent of third-party tile/font availability.
  // MapLibre and the civic geography layers still run; both data APIs are real.
  // The dashboard suite separately covers basemap layers and attribution.
  await page.route("https://tiles.openfreemap.org/styles/*", async route => {
    await route.fulfill({ json: {
      version: 8,
      sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": "#eef2ed" } }],
    } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?level=municipality&metric=population&geoid=3520005&resale_year=2025&resale_open=1");
  const section = page.locator('details[data-topic="resale"]');
  await expect(section).toContainText("$855,000");
  await expect(section).toContainText("23,196");
  await expect(section).toContainText("January–December 2025");
  await page.getByLabel("Report year", { exact: true }).selectOption("2020");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("1");
  await expect(section).toContainText("$725,000");
  await expect(section).toContainText("1,603");
  await expect(section.getByRole("link", { name: /Market Watch/ })).toHaveAttribute("href", "https://trreb.ca/wp-content/files/market-stats/market-watch/mw2001.pdf");
  await page.reload();
  await expect(section).toContainText("January 2020");
  await expect(section).toContainText("$725,000");
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await section.scrollIntoViewIfNeeded();
    await expect(section.getByText("$725,000", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  expect(responses.length).toBeGreaterThan(1);
  expect(responses.every(url => new URL(url).origin === new URL(page.url()).origin)).toBe(true);
  expect(errors).toEqual([]);
});
