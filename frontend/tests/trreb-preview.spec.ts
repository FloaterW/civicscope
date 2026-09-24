import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { request as httpsRequest } from "node:https";

// Synthetic contract fixtures, deliberately not copied from licensed reports.
const selected = "/?level=municipality&metric=population&geoid=3520005";
const publicResale = process.env.NEXT_PUBLIC_TRREB_ENABLED === "1";
const resaleEndpoint = publicResale ? "/api/trreb/resale" : "/api/trreb-preview";
const section = (page: Page) => page.locator('details[data-topic="resale"]');

if (publicResale) {
  test("production TLS preserves CSP, same-origin telemetry and a loopback-only proxy", async ({ request }) => {
    const origin = "https://127.0.0.1:3105";
    const response = await request.get("/");
    expect(response.headers()["content-security-policy"]).toContain("upgrade-insecure-requests");
    const accepted = await request.post("/api/client-errors", {
      headers: { origin }, data: { code: "api_network" },
    });
    expect(accepted.status()).toBe(204);
    const rejected = await request.post("/api/client-errors", {
      headers: { origin: "https://unrelated.example" }, data: { code: "api_network" },
    });
    expect(rejected.status()).toBe(403);
    const certificate = await request.get("/__test/certificate.pem");
    expect(certificate.status()).toBe(200);
    const ca = await certificate.text();
    // Send raw request targets; URL clients normalize these before sending.
    for (const target of ["https://example.invalid/", "//example.invalid/", "/\\example.invalid/"]) {
      const status = await new Promise<number | undefined>((resolve, reject) => {
        const probe = httpsRequest(origin, { path: target, ca }, result => {
          result.resume();
          result.on("end", () => resolve(result.statusCode));
        });
        probe.on("error", reject);
        probe.end();
      });
      expect(status).toBe(400);
    }
  });
}

async function mockResale(page: Page, fail: () => boolean = () => false) {
  const requests: string[] = [];
  await page.route(`**${resaleEndpoint}/**`, async route => {
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
  expect(requests.at(-1)).toBe(`${resaleEndpoint}/3520005?year=2020&month=1`);
  await expect(section(page).getByRole("link", { name: "Market Watch, page 3" })).toHaveAttribute("href", "https://trreb.ca/synthetic-test-report.pdf");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("");
  await expect(section(page)).toContainText("January–December 2020");
  await expect(section(page)).toContainText("$123,456");
});

test("resale display identifies its archive or preview mode and excludes CSV", async ({ page }) => {
  await mockResale(page);
  await openResale(page);
  await expect(section(page)).toContainText(publicResale ? "Archive · 2020–2025" : "Local preview");
  await expect(section(page)).toContainText("TRREB statistics are not included in CSV downloads");
  await expect(section(page)).not.toContainText("Permission conditions pending");
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

test("collapse commits its share URL during activation before a reload can interrupt it", async ({ page }) => {
  await mockResale(page);
  await openResale(page);
  await expect(page).toHaveURL(/resale_open=1/);
  // Native details toggle is queued as a later task. Capture the URL in the
  // activation task itself so navigation cannot hide this lost-update race.
  const collapsedUrl = await section(page).locator("summary").first().evaluate(summary => {
    (summary as HTMLElement).click();
    return window.location.href;
  });
  expect(new URL(collapsedUrl).searchParams.has("resale_open")).toBe(false);
  await page.reload();
  await expect(section(page)).not.toHaveAttribute("open", "");
});

test("historical context survives map changes, sharing, reload and history", async ({ page, context }) => {
  const hydrationErrors: string[] = [];
  page.on("console", message => {
    if (["error", "warning"].includes(message.type()) && /hydration|hydrated/i.test(message.text())) hydrationErrors.push(message.text());
  });
  await mockResale(page);
  await openResale(page);
  await expect(section(page).getByText(/equivalence to the selected Census boundary is not certified/)).toBeVisible();
  await page.getByLabel("Report year", { exact: true }).selectOption("2020");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("1");
  await expect(section(page)).toContainText("January 2020");
  await page.getByRole("combobox", { name: "Map metric", exact: true }).selectOption("rent_burden_pct");
  await expect(section(page)).toHaveAttribute("open", "");
  await expect(page.getByLabel("Report year", { exact: true })).toHaveValue("2020");
  await expect(page.getByLabel("Reporting period", { exact: true })).toHaveValue("1");
  await page.getByTestId("geography-search").fill("Oakville");
  await page.getByRole("option").filter({ hasText: "Oakville" }).click();
  await expect(section(page)).toContainText("Oakville · January 2020");
  const sharedUrl = page.url();
  expect(new URL(sharedUrl).searchParams.get("resale_year")).toBe("2020");
  expect(new URL(sharedUrl).searchParams.get("resale_month")).toBe("1");
  const shared = await context.newPage();
  await mockResale(shared);
  await shared.goto(sharedUrl);
  await expect(section(shared)).toContainText("Oakville · January 2020");
  await shared.close();
  await page.reload();
  await expect(section(page)).toContainText("Oakville · January 2020");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("2");
  await expect(section(page)).toContainText("February 2020");
  await page.goBack();
  await expect(section(page)).toContainText("January 2020");
  await page.goForward();
  await expect(section(page)).toContainText("February 2020");
  await page.getByLabel("Reporting period", { exact: true }).selectOption("");
  await expect(section(page)).toContainText("January–December 2020");
  await section(page).locator("summary").first().click();
  await page.reload();
  await expect(section(page)).not.toHaveAttribute("open", "");
  await section(page).locator("summary").first().click();
  await expect(page.getByLabel("Report year", { exact: true })).toHaveValue("2020");
  await expect(page.getByLabel("Reporting period", { exact: true })).toHaveValue("");
  expect(hydrationErrors).toEqual([]);
});

test("comparison only shows the rent ratio for housing metrics", async ({ page }) => {
  await mockResale(page);
  await page.goto(selected);
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /Rent-to-income/ })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Map metric", exact: true }).selectOption("population_growth_pct");
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /Rent-to-income/ })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Map metric", exact: true }).selectOption("rent_burden_pct");
  await expect(page.getByRole("columnheader", { name: /Rent-to-income/ })).toBeVisible();
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
    await page.keyboard.press("Space");
    await expect(section(page)).not.toHaveAttribute("open", "");
  });
}
