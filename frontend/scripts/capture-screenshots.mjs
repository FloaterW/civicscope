import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const projectRoot = resolve(frontendRoot, "..");
const screenshotDir = resolve(projectRoot, "docs", "screenshots");
const baseURL = process.env.CIVICSCOPE_SCREENSHOT_URL ?? "http://localhost:3001";

await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1320, height: 1142 } });

async function waitForDashboard() {
  await page.goto(baseURL);
  await page.getByText("$1,554", { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
}

async function save(name) {
  await page.screenshot({
    path: resolve(screenshotDir, name),
    fullPage: false
  });
}

await waitForDashboard();
await page.getByLabel("Map metric").selectOption("rent_burden_pct");
await page.getByText("51.2", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
await save("overview-dashboard.png");

await page.getByLabel("Map metric").selectOption("median_income");
await page.getByText("141K", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
await page.getByTestId("geography-search").fill("Toronto");
await page.getByRole("button").filter({ hasText: "3520005" }).click();
await page.getByTestId("detail-panel").getByText("Toronto", { exact: true }).waitFor({
  state: "visible",
  timeout: 15_000
});
await save("selected-toronto.png");

await page.getByLabel("Map metric").selectOption("population_growth_pct");
await page.getByText("44.4", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
await save("population-growth.png");

await page.getByRole("button", { name: "Census tracts" }).click();
await page.getByLabel("Map metric").selectOption("rent_burden_pct");
await page.getByText("1,334 GTA census tracts", { exact: true }).waitFor({
  state: "visible",
  timeout: 30_000
});
await page.getByText("57.6", { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
await save("census-tracts.png");

await browser.close();

console.log(`Screenshots saved to ${screenshotDir}`);
