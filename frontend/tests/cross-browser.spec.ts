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

  test("search selection survives a held pointer and cancels a dragged release", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
    const search = page.getByTestId("geography-search");
    await search.fill("Oakville");
    const option = page.getByRole("option").filter({ hasText: "3524001" });
    await expect(option).toBeVisible();
    const box = (await option.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    let remainsOpen: boolean;
    try {
      // A press can span frames; a blur callback must not remove the click target.
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      remainsOpen = await option.isVisible();
    } finally {
      await page.mouse.up();
    }
    expect(remainsOpen).toBe(true);
    await expect(search).toBeFocused();
    await expect(page.getByTestId("detail-panel")).toContainText("Oakville");

    await search.fill("Toronto");
    const other = page.getByRole("option").filter({ hasText: "3520005" });
    await expect(other).toBeVisible();
    const otherBox = (await other.boundingBox())!;
    await page.mouse.move(otherBox.x + otherBox.width / 2, otherBox.y + otherBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(0, 0);
    await page.mouse.up();
    await expect(page.getByTestId("detail-panel")).toContainText("Oakville");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");
  });

  test("search result keyboard selection, Escape reopening, and Tab dismissal remain usable", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
    const search = page.getByTestId("geography-search");
    await search.fill("Oakville");
    const oakville = page.getByRole("option").filter({ hasText: "3524001" });
    await expect(oakville).toBeVisible();
    await search.press("Tab");
    await expect(oakville).toBeFocused();
    await oakville.press("Enter");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");
    await expect(search).toBeFocused();

    await search.fill("Toronto");
    const toronto = page.getByRole("option").filter({ hasText: "3520005" });
    await expect(toronto).toBeVisible();
    await search.press("Tab");
    await expect(toronto).toBeFocused();
    await toronto.press("Tab");
    await expect(page.getByRole("listbox")).toBeHidden();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");

    await search.focus();
    await expect(toronto).toBeVisible();
    await search.press("Escape");
    await expect(search).toBeFocused();
    await expect(search).toHaveValue("Toronto");
    await expect(search).toHaveAttribute("aria-expanded", "false");
    await expect(search).not.toHaveAttribute("aria-activedescendant");
    await search.press("Enter");
    await expect(page.getByRole("listbox")).toBeHidden();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");

    const refreshedResults = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === "/api/geographies" && url.searchParams.get("search") === "Toronto";
    });
    await search.press("ArrowDown");
    await expect(toronto).toBeVisible();
    await expect(search).toBeFocused();
    await expect(search).toHaveAttribute("aria-activedescendant", "search-option-3520005");
    await (await refreshedResults).finished();
    // Reopening refreshes the same query. Its response must not erase the
    // keyboard highlight before a user has time to press Enter.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(search).toHaveAttribute("aria-activedescendant", "search-option-3520005");
    await search.press("Enter");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
  });

  test("search arrows ignore empty results and reopen the last result with ArrowUp", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    const map = page.getByTestId("civic-map");
    await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
    const search = page.getByTestId("geography-search");

    for (const query of ["", "   ", "zzzznomatch"]) {
      await search.fill(query);
      if (query.trim()) await expect(page.getByTestId("search-empty")).toContainText("No municipalities match");
      await search.press("Escape");
      for (const key of ["ArrowDown", "ArrowUp", "Enter"]) await search.press(key);
      await expect(search).toBeFocused();
      await expect(search).toHaveAttribute("aria-expanded", "false");
      await expect(search).not.toHaveAttribute("aria-activedescendant");
      await expect(page.getByRole("listbox")).toBeHidden();
      await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
    }

    await search.fill("a");
    const options = page.getByRole("listbox").getByRole("option");
    await expect.poll(() => options.count()).toBeGreaterThan(1);
    const lastOptionId = (await options.last().getAttribute("id"))!;
    await search.press("Enter");
    await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
    await search.press("Escape");
    await search.press("ArrowUp");
    await expect(search).toHaveAttribute("aria-expanded", "true");
    await expect(search).toHaveAttribute("aria-activedescendant", lastOptionId);
    await expect(options.last()).toHaveAttribute("aria-selected", "true");
    await search.press("Enter");
    await expect(map).toHaveAttribute("data-selected-geoid", lastOptionId.replace("search-option-", ""));
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

  test("comparison values support keyboard navigation, dismissal, and pointer recovery", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    const panel = page.getByTestId("comparison-panel");
    await expect(panel).toContainText("2,794,356");
    const chart = panel.getByRole("application", { name: /Population comparison chart/ });
    const tooltip = panel.locator(".recharts-tooltip-wrapper");
    const rows = panel.locator("tbody tr");
    const firstName = await rows.nth(0).locator("td").first().innerText();
    const secondName = await rows.nth(1).locator("td").first().innerText();

    await chart.scrollIntoViewIfNeeded();
    await chart.focus();
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText(firstName);
    await chart.press("ArrowRight");
    await expect(tooltip).toContainText(secondName);
    await expect(tooltip.getByRole("status")).toHaveAttribute("aria-live", "polite");
    await chart.press("Enter");
    await expect(tooltip).toBeHidden();
    await chart.press("Enter");
    await expect(tooltip).toBeVisible();
    await chart.press("Escape");
    await expect(tooltip).toBeHidden();
    await chart.press("ArrowLeft");
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText(firstName);
    await expect(tooltip).toContainText("2,794,356");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(tooltip).toBeHidden();
    await chart.press("ArrowRight");
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText(secondName);
    await chart.press("Tab");
    await expect(chart).not.toBeFocused();
    await expect(tooltip).toBeHidden();

    await panel.locator(".recharts-bar-rectangle").first().hover();
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText(firstName);
    await expect(tooltip).toContainText("2,794,356");
    await expect(tooltip.getByRole("status")).toHaveCount(0);
    await page.mouse.move(0, 0);
    await expect(tooltip).toBeHidden();
  });

  for (const metric of ["population", "population_growth_pct", "median_income"]) {
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
      if (metric === "median_income") {
        // Identical heights expose label-to-label collisions that varied bars hide.
        await page.route("**/api/compare?**", async (route) => {
          const response = await route.fetch();
          const payload = await response.json();
          payload.items.forEach((item: { metrics: { median_income: number } }) => {
            item.metrics.median_income = 107_000;
          });
          await route.fulfill({ response, json: payload });
        });
      }
      await page.goto(`/?level=municipality&metric=${metric}&geoid=3520005`);
      const panel = page.getByTestId("comparison-panel");
      await expect(panel).toContainText(metric === "population" ? "2,794,356" : metric === "median_income" ? "$107,000" : "-20.0%");

      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await panel.scrollIntoViewIfNeeded();
        // Labels are mounted after Recharts finishes its bar animation. Require
        // actual nonzero bars and all five labels before checking their bounds.
        await expect(panel.locator(".recharts-label-list .recharts-label")).toHaveCount(5);
        if (metric === "population_growth_pct") {
          await expect(panel.locator(".recharts-label-list")).toContainText("-20.0%");
        }
        if (metric === "population") {
          await expect(panel.locator(".recharts-label-list")).toContainText(width === 1440 ? "2,794,356" : "2.8M");
          await expect(panel.locator("tbody")).toContainText("2,794,356");
        }
        if (metric === "median_income") {
          await expect(panel.locator(".recharts-label-list")).toContainText(width === 1440 ? "$107,000" : "107K");
          await expect(panel.locator('.recharts-cartesian-axis-tick-value[orientation="left"]').first()).toContainText("$");
          await expect(panel.locator("tbody")).toContainText("$107,000");
        }
        await expect.poll(async () => panel.evaluate((element) => {
          const svg = element.querySelector("svg.recharts-surface")!;
          const bounds = svg.getBoundingClientRect();
          const container = element.querySelector(".recharts-responsive-container")!.getBoundingClientRect();
          const bars = [...svg.querySelectorAll("path.recharts-rectangle")];
          const labels = [...svg.querySelectorAll(".recharts-label-list .recharts-label")];
          // Recharts 3 portals tick labels outside their axis <g> for z-index ordering.
          const axisLabels = [...svg.querySelectorAll('.recharts-cartesian-axis-tick-value[orientation="bottom"]')];
          // Do not accept old-width SVG geometry before ResizeObserver catches up.
          const resized = Math.abs(bounds.width - container.width) <= 1 &&
            bounds.left >= container.left - 1 && bounds.right <= container.right + 1;
          return resized && bars.length === 5 && labels.length === 5 && axisLabels.length > 0 && bars.every((bar) => {
            const box = bar.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
          }) && labels.every((label, index) => {
            const box = label.getBoundingClientRect();
            return box.width > 0 && box.height > 0 && box.top >= bounds.top &&
              box.bottom <= bounds.bottom && box.left >= bounds.left && box.right <= bounds.right &&
              axisLabels.every((axisLabel) => {
                const axisBox = axisLabel.getBoundingClientRect();
                return box.right <= axisBox.left || box.left >= axisBox.right || box.bottom <= axisBox.top;
              }) && labels.slice(index + 1).every((otherLabel) => {
                const otherBox = otherLabel.getBoundingClientRect();
                return box.right <= otherBox.left || box.left >= otherBox.right ||
                  box.bottom <= otherBox.top || box.top >= otherBox.bottom;
              });
          });
        })).toBe(true);
        await panel.screenshot({ path: testInfo.outputPath(`comparison-labels-${width}.png`) });
      }
    });
  }
});

test.describe("touch search", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test.beforeEach(async ({ page }) => {
    await blockExternalMapAssets(page);
  });

  test("selects a result on tap and dismisses outside", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
    const search = page.getByTestId("geography-search");
    await search.fill("Oakville");
    await page.getByRole("option").filter({ hasText: "3524001" }).tap();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");
    await search.fill("Toronto");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.getByRole("heading", { name: "Greater Toronto Housing Affordability Explorer" }).tap();
    await expect(page.getByRole("listbox")).toBeHidden();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3524001");
  });

  test("scrolling the results does not select the pressed option", async ({ page, browserName }) => {
    // Playwright's cross-browser touchscreen API supports taps only. Chromium's
    // protocol supplies a native touch sequence to verify scroll cancellation.
    test.skip(browserName !== "chromium", "Native touch drag requires Chromium's protocol");
    await page.goto("/?level=municipality&metric=population&geoid=3520005");
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
    await page.getByTestId("geography-search").fill("a");
    const results = page.getByRole("listbox");
    await expect(results.getByRole("option")).toHaveCount(8);
    const box = (await results.boundingBox())!;
    const client = await page.context().newCDPSession(page);
    const x = box.x + box.width / 2;
    const startY = box.y + box.height - 30;
    try {
      await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: startY }] });
      for (let step = 1; step <= 8; step++) {
        await client.send("Input.dispatchTouchEvent", {
          type: "touchMove", touchPoints: [{ x, y: startY - step * 20 }]
        });
      }
      await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await expect.poll(() => results.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
      await expect(page.getByTestId("civic-map")).toHaveAttribute("data-selected-geoid", "3520005");
      await expect(results).toBeVisible();
    } finally {
      await client.detach();
    }
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
