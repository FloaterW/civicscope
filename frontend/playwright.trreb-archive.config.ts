import { defineConfig } from "@playwright/test";
import publicConfig from "./playwright.trreb-public.config";

process.env.NEXT_PUBLIC_TRREB_ENABLED = "archive";
export default defineConfig({
  ...publicConfig,
  testMatch: ["trreb-preview.spec.ts", "trreb-archive.spec.ts"],
  webServer: {
    command: "npm run build && node scripts/test-production-server.mjs",
    url: "https://127.0.0.1:3105",
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 180000,
    env: {
      NEXT_PUBLIC_TRREB_ENABLED: "archive",
      NEXT_PUBLIC_TRREB_PREVIEW_ENABLED: "0",
      NEXT_PUBLIC_API_URL: "https://127.0.0.1:3105",
      CIVICSCOPE_TEST_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
    },
  },
});
