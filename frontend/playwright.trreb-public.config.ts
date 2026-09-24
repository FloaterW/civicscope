import { defineConfig } from "@playwright/test";
import previewConfig from "./playwright.trreb.config";

// Reuse the complete synthetic contract suite against the public route. This
// changes no deployed flags and never publishes or copies licensed report data.
process.env.NEXT_PUBLIC_TRREB_ENABLED = "1";
export default defineConfig({
  ...previewConfig,
  use: { ...previewConfig.use, baseURL: "https://127.0.0.1:3105", ignoreHTTPSErrors: true },
  webServer: {
    command: "npm run build && node scripts/test-production-server.mjs",
    url: "https://127.0.0.1:3105",
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 180000,
    env: {
      NEXT_PUBLIC_TRREB_ENABLED: "1",
      NEXT_PUBLIC_TRREB_PREVIEW_ENABLED: "0",
      NEXT_PUBLIC_API_URL: "https://127.0.0.1:3105",
      CIVICSCOPE_TEST_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
    },
  },
});
