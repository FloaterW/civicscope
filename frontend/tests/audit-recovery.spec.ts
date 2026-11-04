import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const localStyle = { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#eef2ed" } }] };

test("regional snapshot discloses approximations and estimate methodology", async ({ page }) => {
  await page.route("https://tiles.openfreemap.org/styles/*", route => route.fulfill({ json: localStyle }));
  await page.goto("/");
  const summary = page.getByTestId("summary-panel");
  await expect(summary).toContainText("25 GTA municipalities");
  await expect(summary).toContainText("Income (local medians)");
  await expect(summary).toContainText("Rent (local medians)");
  await expect(summary.getByTestId("summary-methodology")).toContainText("not official regional medians");
  await summary.getByText("How this snapshot is calculated", { exact: true }).click();
  await expect(summary).toContainText("falling back to a rent-and-income estimate");
});

test("initial basemap failure keeps geography layers usable and can recover", async ({ page }) => {
  let failStyle = true;
  await page.route("https://tiles.openfreemap.org/styles/*", route => failStyle ? route.abort() : route.fulfill({ json: localStyle }));
  await page.goto("/?level=municipality&metric=population&geoid=3520005");
  const map = page.getByTestId("civic-map");
  await expect(map).toHaveAttribute("data-basemap-status", "fallback");
  await expect(page.getByTestId("map-canvas-host")).toHaveAttribute("data-civic-layer-order", "valid");
  await expect(page.getByTestId("detail-panel")).toContainText("Toronto");
  await expect(map).toContainText("Geography boundaries and statistics still work");
  await page.getByRole("button", { name: "Dark theme", exact: true }).click();
  await expect(map).toHaveAttribute("data-basemap-status", "fallback");
  await expect(page.getByTestId("map-canvas-host")).toHaveAttribute("data-map-theme", "dark");
  failStyle = false;
  await map.getByRole("button", { name: "Retry background map" }).click();
  await expect(map).toHaveAttribute("data-basemap-status", "ready");
  await expect(page.getByTestId("map-canvas-host")).toHaveAttribute("data-civic-layer-order", "valid");
  await expect(map).toHaveAttribute("data-selected-geoid", "3520005");
  await expect(map.getByRole("button", { name: "Retry background map" })).toHaveCount(0);
});

test("CSV waits for the selected CMHC year and stays blocked after a load failure", async ({ page }) => {
  await page.route("https://tiles.openfreemap.org/styles/*", route => route.fulfill({ json: localStyle }));
  await page.goto("/?level=municipality&metric=average_rent_total&geoid=3520005&year=2023");
  const exportCsv = page.getByRole("button", { name: "Export geography data as CSV" });
  await expect(exportCsv).toBeEnabled();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let fail = true;
  await page.route("**/api/map-data?**", async route => {
    if (new URL(route.request().url()).searchParams.get("year") !== "2022") return route.continue();
    await gate;
    if (fail) return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    return route.continue();
  });
  try {
    await page.getByRole("combobox", { name: "CMHC data year", exact: true }).selectOption("2022");
    await expect(exportCsv).toBeDisabled();
    await expect(page.getByText("CSV export will be available when the selected year's data finishes loading.", { exact: true })).toBeVisible();
  } finally { release(); }
  await expect(page.getByText("CSV export is unavailable because rental and construction data could not be loaded.", { exact: true })).toBeVisible();
  await expect(exportCsv).toBeDisabled();
  fail = false;
  await page.getByTestId("detail-panel").getByRole("button", { name: "Retry rental and construction data", exact: true }).click();
  await expect(exportCsv).toBeEnabled();
  const downloaded = page.waitForEvent("download");
  await exportCsv.click();
  const download = await downloaded;
  const csv = await readFile((await download.path())!, "utf8");
  expect(csv).toContain("2022");
  expect(csv).toContain("CMHC");
  expect(csv).toContain("Average rent");
});
