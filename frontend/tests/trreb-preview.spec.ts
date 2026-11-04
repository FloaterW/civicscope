import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { request as httpsRequest } from "node:https";

// Synthetic contract fixtures, deliberately not copied from licensed reports.
const selected = "/?level=municipality&metric=population&geoid=3520005";
const archiveResale = process.env.NEXT_PUBLIC_TRREB_ENABLED === "archive";
const publicResale = archiveResale || process.env.NEXT_PUBLIC_TRREB_ENABLED === "1";
const resaleEndpoint = archiveResale ? "/api/trreb-archive/resale" : publicResale ? "/api/trreb/resale" : "/api/trreb-preview";
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

async function mockResale(page: Page, fail: () => boolean = () => false, beforeResponse: (url: URL) => Promise<void> = async () => {}) {
  const requests: string[] = [];
  await page.route(`**${resaleEndpoint}/**`, async route => {
    const url = new URL(route.request().url());
    requests.push(url.pathname + url.search);
    await beforeResponse(url);
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
  await expect(section(page).getByText(/TRREB reporting areas, not Census boundaries/)).toBeVisible();
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

for (const width of [320, 390, 1440]) {
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

  test(`resale cards, controls and tooltips match the dashboard at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockResale(page);
    await openResale(page);
    // Measure the final font metrics rather than a transient fallback-font layout.
    await page.evaluate(async () => { await document.fonts.ready; });
    const census = page.locator('[data-topic="population"] [data-metric="population"]');
    const resale = section(page).locator('[data-metric="trreb_sales"]');
    const cardStyle = (node: Element) => {
      const value = node.querySelector('.tabular-nums')!;
      const style = getComputedStyle(value);
      const label = node.firstElementChild!;
      return {
        height: node.getBoundingClientRect().height,
        labelHeight: label.getBoundingClientRect().height,
        labelLineHeight: Number.parseFloat(getComputedStyle(label).lineHeight),
        valueTop: value.getBoundingClientRect().top - node.getBoundingClientRect().top,
        font: style.fontSize, weight: style.fontWeight, numbers: style.fontVariantNumeric,
      };
    };
    const censusStyle = await census.evaluate(cardStyle);
    expect(await resale.evaluate(cardStyle)).toEqual(censusStyle);
    expect(censusStyle.labelHeight).toBeGreaterThanOrEqual(censusStyle.labelLineHeight * 2);
    const year = page.getByLabel("Report year", { exact: true });
    expect(await year.evaluate(node => node.parentElement!.getBoundingClientRect().height)).toBe(44);
    expect(await year.evaluate(node => getComputedStyle(node).backgroundColor)).toBe(await page.getByLabel("Map metric", { exact: true }).evaluate(node => getComputedStyle(node).backgroundColor));
    for (const term of ["Median sale price", "Resale sales", "Property days on market"]) {
      const button = section(page).getByRole("button", { name: `What is ${term}?`, exact: true });
      await button.focus();
      const tooltip = page.getByRole("tooltip");
      await expect(tooltip).toBeVisible();
      await expect(tooltip).toContainText("Toronto Regional Real Estate Board");
      const box = (await tooltip.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      await page.keyboard.press("Escape");
      await expect(tooltip).toBeHidden();
    }
    await page.getByRole("button", { name: "Dark theme", exact: true }).click();
    expect(await year.evaluate(node => getComputedStyle(node).backgroundColor)).toBe(await page.getByLabel("Map metric", { exact: true }).evaluate(node => getComputedStyle(node).backgroundColor));
    expect((await new AxeBuilder({ page }).include('details[data-topic="resale"]').analyze()).violations).toEqual([]);
  });

  test(`report loading, errors and retry preserve the scrolled panel at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let failing = false;
    let hold = true;
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    await mockResale(page, () => failing, async url => {
      if (hold && url.searchParams.get("year") === "2024") await pending;
    });
    await openResale(page);
    await section(page).getByText("Source and interpretation", { exact: true }).click();
    await section(page).getByText("$123,456", { exact: true }).click();
    const year = page.getByLabel("Report year", { exact: true });
    await year.focus();
    // Allow ResizeObserver to record the expanded source content before loading.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const layout = () => page.evaluate(() => ({
      scroll: document.querySelector('[data-testid="detail-panel-scroll"]')!.scrollTop,
      yearY: document.querySelector<HTMLSelectElement>('select[aria-label="Report year"]')!.getBoundingClientRect().y,
      map: document.querySelector('[data-testid="map-panel"]')!.getBoundingClientRect().height,
    }));
    const before = await layout();
    try {
      await year.selectOption("2024");
      await expect(section(page).getByRole("status")).toContainText("Loading resale statistics");
      await expect(section(page)).not.toContainText("$123,456");
      await expect(section(page).getByRole("link", { name: /Market Watch/ })).toHaveCount(0);
      const loading = await layout();
      expect(loading.scroll).toBeCloseTo(before.scroll, 0);
      expect(loading.yearY).toBeCloseTo(before.yearY, 0);
      expect(loading.map).toBeCloseTo(before.map, 0);
      failing = true;
      release();
      await expect(section(page).getByRole("status")).toContainText("unavailable");
      const error = await layout();
      expect(error.scroll).toBeCloseTo(before.scroll, 0);
      expect(error.yearY).toBeCloseTo(before.yearY, 0);
      failing = false;
      hold = false;
      await section(page).getByRole("button", { name: "Retry resale statistics" }).click();
      await expect(section(page)).toContainText("January–December 2024");
      await expect(section(page)).toContainText("$123,456");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    } finally { release(); }
  });
}

test("a slower superseded report cannot replace the latest selected year", async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await mockResale(page, () => false, async url => {
    if (url.searchParams.get("year") === "2024") await pending;
  });
  await openResale(page);
  try {
    await page.getByLabel("Report year", { exact: true }).selectOption("2024");
    await expect(section(page).getByRole("status")).toContainText("Loading");
    await page.getByLabel("Report year", { exact: true }).selectOption("2023");
    await expect(section(page)).toContainText("January–December 2023");
    release();
    await expect(section(page)).not.toContainText("January–December 2024");
    await expect(page.getByLabel("Report year", { exact: true })).toHaveValue("2023");
  } finally { release(); }
});
