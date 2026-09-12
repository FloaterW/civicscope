import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

async function selectArea(page: Page, name: string) {
  await page.getByTestId("geography-search").fill(name);
  await page.getByRole("option").filter({ hasText: name }).click();
  await expect(page.getByTestId("detail-panel")).toContainText(name);
}

test.describe("launch comparison journeys", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("https://tiles.openfreemap.org/**", async (route) => {
      if (new URL(route.request().url()).pathname.startsWith("/styles/")) {
        await route.fulfill({ json: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#eef2ed" } }] } });
      } else await route.abort();
    });
  });

  test("custom Oakville and Burlington comparison survives sharing, reload, and history", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/?campaign=launch#comparison");
    const panel = page.getByTestId("comparison-panel");
    const add = panel.getByRole("button", { name: "Add selected area to comparison" });
    await selectArea(page, "Oakville");
    await add.click();
    await expect(panel.locator("tbody tr")).toHaveCount(1);
    await selectArea(page, "Burlington");
    await add.click();
    await expect(panel.locator("tbody tr")).toHaveCount(2);
    await expect(panel.locator("tbody")).toContainText("Oakville");
    await expect(panel.locator("tbody")).toContainText("Burlington");
    await expect(add).toBeDisabled();
    const shared = new URL(page.url());
    expect(shared.searchParams.get("compare")?.split(",")).toHaveLength(2);
    expect(shared.searchParams.get("campaign")).toBe("launch");
    expect(shared.hash).toBe("#comparison");
    await panel.getByRole("button", { name: "Copy view link" }).click();
    await expect(panel.getByRole("status")).toHaveText("View link copied.");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(shared.href);
    await page.reload();
    await expect(panel.locator("tbody tr")).toHaveCount(2);
    await panel.getByRole("button", { name: "Remove Oakville from comparison" }).click();
    await expect(panel.locator("tbody tr")).toHaveCount(1);
    await expect(panel.locator("tbody")).toContainText("Burlington");
    await page.goBack();
    await expect(panel.locator("tbody tr")).toHaveCount(2);
    expect(new URL(page.url()).searchParams.get("compare")).toBe(shared.searchParams.get("compare"));
  });

  test("search and comparisons remain usable when WebGL2 is unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
        value: function (this: HTMLCanvasElement, kind: string, options?: unknown) {
          return kind === "webgl2" ? null : Reflect.apply(original, this, [kind, options]);
        }
      });
    });
    await page.goto("/");
    await expect(page.getByTestId("civic-map").getByRole("alert")).toContainText("WebGL2");
    await selectArea(page, "Oakville");
    const panel = page.getByTestId("comparison-panel");
    await panel.getByRole("button", { name: "Add selected area to comparison" }).click();
    await expect(panel.locator("tbody tr")).toHaveCount(1);
    await expect(panel.locator("tbody")).toContainText("Oakville");
  });

  test("comparison CSV preserves Census period and source for selected areas", async ({ page }) => {
    await page.goto("/?metric=population");
    const panel = page.getByTestId("comparison-panel");
    for (const area of ["Oakville", "Burlington"]) {
      await selectArea(page, area);
      await panel.getByRole("button", { name: "Add selected area to comparison" }).click();
    }
    await expect(panel.locator("tbody tr")).toHaveCount(2);
    const pending = page.waitForEvent("download");
    await panel.getByRole("button", { name: "Export comparison data as CSV" }).click();
    const download = await pending;
    const path = await download.path();
    expect(path).not.toBeNull();
    const csv = await readFile(path!, "utf8");
    const lines = csv.trim().split(/\r?\n/);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain('"Period","Source","Method"');
    for (const name of ["Oakville", "Burlington"]) {
      const row = lines.find((line) => line.startsWith(`"${name}",`));
      expect(row).toContain('"2021 Census","Statistics Canada Census Profile","Published value"');
    }
    expect(download.suggestedFilename()).toBe("civicscope-population-municipality-2021.csv");
  });

  test("switching geography clears custom pins and stale shared-view announcements", async ({ page }) => {
    await page.goto("/?level=municipality&metric=population&geoid=3520005&compare=3520005");
    await expect(page.getByText("Loaded the shared view for Toronto.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Census tracts", exact: true }).click();
    await expect(page.getByTestId("civic-map")).toHaveAttribute("data-geography-type", "census_tract", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Reset comparison", exact: true })).toHaveCount(0);
    await expect(page.getByText("Loaded the shared view for Toronto.", { exact: true })).toHaveCount(0);
    expect(new URL(page.url()).searchParams.has("compare")).toBe(false);
    expect(new URL(page.url()).searchParams.has("geoid")).toBe(false);
  });
});
