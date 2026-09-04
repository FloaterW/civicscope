import { chromium } from "@playwright/test";
import { copyFile, mkdir, readdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const projectRoot = resolve(frontendRoot, "..");
const demoDir = resolve(projectRoot, "docs", "demo");
const tempVideoDir = resolve(demoDir, ".tmp-video");
const outputPath = resolve(demoDir, "civicscope-demo.webm");
const baseURL = process.env.CIVICSCOPE_SCREENSHOT_URL ?? "http://localhost:3000";

await rm(tempVideoDir, { recursive: true, force: true });
await mkdir(tempVideoDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1320, height: 900 },
  recordVideo: {
    dir: tempVideoDir,
    size: { width: 1320, height: 900 }
  }
});
const page = await context.newPage();

await page.goto(baseURL);
await page.getByText("$1,554", { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
await page.waitForTimeout(900);

await page.getByLabel("Map metric").selectOption("median_income");
await page.getByText("141K", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
await page.waitForTimeout(900);

await page.getByTestId("geography-search").fill("Toronto");
await page.getByRole("button").filter({ hasText: "3520005" }).click();
await page.getByTestId("detail-panel").getByText("Toronto", { exact: true }).waitFor({
  state: "visible",
  timeout: 15_000
});
await page.waitForTimeout(1_200);

await page.getByRole("button", { name: "Census tracts" }).click();
await page.getByText("1,334 GTA census tracts", { exact: true }).waitFor({
  state: "visible",
  timeout: 30_000
});
await page.waitForTimeout(900);

await page.getByTestId("geography-search").fill("5350001.00");
await page.getByRole("button").filter({ hasText: "5350001.00" }).click();
await page.getByTestId("detail-panel").getByText("Toronto census tract 0001.00", { exact: true }).waitFor({
  state: "visible",
  timeout: 15_000
});
await page.waitForTimeout(1_200);

await context.close();
await browser.close();

const videos = (await readdir(tempVideoDir)).filter((name) => name.endsWith(".webm"));
if (videos.length !== 1) {
  throw new Error(`Expected one recorded video, found ${videos.length}.`);
}

await copyFile(resolve(tempVideoDir, videos[0]), outputPath);
await rm(tempVideoDir, { recursive: true, force: true });

console.log(`Demo video saved to ${outputPath}`);
