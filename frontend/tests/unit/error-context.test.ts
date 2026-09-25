import { afterEach, describe, expect, it, vi } from "vitest";
import { apiErrorContext, sanitizeErrorContext } from "@/lib/error-context";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("bounded diagnostic context", () => {
  it("never retains queries, IDs, raw errors, or arbitrary fields", () => {
    vi.spyOn(Date, "now").mockReturnValue(2000);
    const context = apiErrorContext("/api/geographies?search=private+query", 500, "network");
    expect(context).toMatchObject({ operation: "search", failure: "network", duration: "1_to_10s" });
    expect(JSON.stringify(context)).not.toContain("private");
    expect(apiErrorContext("/api/trreb/resale/3520005?year=2020", 500, "http", 503)).toMatchObject({ operation: "resale", status: 503 });
    expect(apiErrorContext("/api/trreb-archive/resale/3520005?year=2020", 500, "http", 503)).toMatchObject({ operation: "resale", status: 503 });
    expect(sanitizeErrorContext({ operation: "private", failure: "TypeError: private", status: "503", online: "yes", message: "private" })).toEqual({});
    expect(sanitizeErrorContext(null)).toEqual({});
    expect(sanitizeErrorContext([])).toEqual({});
  });

  it.each([0, 999, 1000, 9999, 10000, 59999, 60000])("buckets elapsed time %i", (elapsed) => {
    vi.spyOn(Date, "now").mockReturnValue(100000);
    const expected = elapsed < 1000 ? "under_1s" : elapsed < 10000 ? "1_to_10s" : elapsed < 60000 ? "10_to_60s" : "over_60s";
    expect(apiErrorContext("/unlisted", 100000 - elapsed, "timeout")).toMatchObject({ operation: "other", duration: expected });
  });

  it("allows only browser state and valid HTTP error status", () => {
    vi.stubGlobal("navigator", { onLine: false });
    vi.stubGlobal("document", { visibilityState: "hidden" });
    expect(apiErrorContext("/api/map-data", Date.now(), "browser_abort")).toMatchObject({ online: false, visibility: "hidden", failure: "browser_abort" });
    for (const status of [0, 200, 600, NaN, 503.2]) expect(sanitizeErrorContext({ status })).toEqual({});
  });
});
