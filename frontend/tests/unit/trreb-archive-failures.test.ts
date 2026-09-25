import { afterEach, expect, it, vi } from "vitest";
import original from "@/data/trreb-resale-2020-2025.json";

afterEach(() => {
  vi.doUnmock("@/data/trreb-resale-2020-2025.json");
  vi.doUnmock("@/lib/trreb-mode");
  vi.resetModules();
});

it("fails closed if an aggregate is changed without updating the approved fingerprint", async () => {
  const modified = structuredClone(original);
  modified.observations[0].sales += 1;
  vi.doMock("@/data/trreb-resale-2020-2025.json", () => ({ default: modified }));
  vi.resetModules();
  const { GET } = await import("@/app/api/trreb-archive/resale/[geoid]/route");
  const response = await GET(new Request("https://example.test/api/trreb-archive/resale/3520005"), { params: Promise.resolve({ geoid: "3520005" }) });
  expect(response.status).toBe(503);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(await response.json()).toEqual({ detail: "TRREB archive is temporarily unavailable." });
});

it("does not expose the archive when its build-time mode is disabled", async () => {
  vi.doMock("@/lib/trreb-mode", () => ({ TRREB_MODE: "disabled" }));
  vi.resetModules();
  const { GET } = await import("@/app/api/trreb-archive/resale/[geoid]/route");
  const response = await GET(new Request("https://example.test/api/trreb-archive/resale/3520005"), { params: Promise.resolve({ geoid: "3520005" }) });
  expect(response.status).toBe(404);
});
