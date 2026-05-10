import { defineConfig } from "@playwright/test";

const host = "127.0.0.1";
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3101);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://${host}:${port}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  expect: {
    timeout: 15_000
  },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : "list",
  use: {
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    viewport: {
      width: 1365,
      height: 900
    }
  },
  webServer: {
    command: `npm run dev -- --hostname ${host} --port ${port}`,
    env: {
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
    },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    url: baseURL
  }
});
