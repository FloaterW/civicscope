import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const projectRoot = resolve(frontendRoot, "..");
const screenshotDir = resolve(projectRoot, "docs", "screenshots");
const baseURL = process.env.CIVICSCOPE_SCREENSHOT_URL ?? "http://localhost:3000";

await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1320, height: 1142 } });

async function waitForDashboard() {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.getByTestId("summary-panel").waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForFunction(() => {
    const map = document.querySelector('[data-testid="civic-map"]');
    return Number(map?.getAttribute("data-feature-count") ?? 0) > 0;
  });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({
    content: "*,*::before,*::after{animation:none!important;transition:none!important}"
  });
}

async function save(name) {
  await page.locator(".maplibregl-canvas").waitFor({ state: "visible", timeout: 15_000 });
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
  // MapLibre updates its WebGL canvas after React has committed the new data.
  // Give that paint cycle time to settle so documentation never captures a
  // populated legend over a still-blank canvas.
  await page.waitForTimeout(1_000);
  await page.screenshot({
    path: resolve(screenshotDir, name),
    fullPage: false
  });
}

await waitForDashboard();
await page.getByLabel("Map metric").selectOption("rent_burden_pct");
await page.getByTestId("civic-map").waitFor({ state: "visible" });
await save("overview-dashboard.png");

await page.getByLabel("Map metric").selectOption("median_income");
await page.getByTestId("geography-search").fill("Toronto");
await page.getByRole("option").filter({ hasText: "3520005" }).click();
await page.getByTestId("detail-panel").getByText("Toronto", { exact: true }).waitFor({
  state: "visible",
  timeout: 15_000
});
await save("selected-toronto.png");

await page.getByLabel("Map metric").selectOption("population_growth_pct");
await page.getByTestId("civic-map").waitFor({ state: "visible" });
await save("population-growth.png");

await page.getByRole("button", { name: "Census tracts" }).click();
await page.getByLabel("Map metric").selectOption("rent_burden_pct");
await page.getByTestId("civic-map").waitFor({ state: "visible" });
await page.waitForFunction(() => {
  const map = document.querySelector('[data-testid="civic-map"]');
  return map?.getAttribute("data-feature-count") === "1334";
});
await save("census-tracts.png");

await page.setViewportSize({ width: 390, height: 844 });
await waitForDashboard();
await save("mobile-overview.png");

await browser.close();

console.log(`Screenshots saved to ${screenshotDir}`);
