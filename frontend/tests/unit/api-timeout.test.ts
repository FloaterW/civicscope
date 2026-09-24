import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchJson, normalizeApiTimeout } from "@/lib/api";
import { reportClientError } from "@/lib/error-reporting";

vi.mock("@/lib/error-reporting", () => ({ reportClientError: vi.fn() }));


afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});


function pendingFetch() {
  return vi.fn((_url: string, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true }
      );
    })
  );
}


describe("fetchJson request deadlines", () => {
  it.each([['Service temporarily unavailable', 'Service temporarily unavailable'], ['{"detail":"Invalid year"}', 'Invalid year'], ['', 'temporarily unavailable (503)']])("preserves error response %s", async (body, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 503 })));
    await expect(fetchJson("/failed")).rejects.toThrow(message);
  });
  it.each(['<html><body>Proxy failure</body></html>', 'x'.repeat(500)])("does not expose raw proxy errors", async (body) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 502 })));
    await expect(fetchJson("/failed")).rejects.toThrow("temporarily unavailable (502)");
  });
  it("offers nontechnical recovery advice for network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(fetchJson("/offline")).rejects.toThrow("Check your connection and try again");
    expect(reportClientError).toHaveBeenCalledWith("api_network", expect.objectContaining({ operation: "other", failure: "network" }));
  });

  it("falls back to a safe deadline for invalid configuration", () => {
    expect(normalizeApiTimeout(Number.NaN)).toBe(60_000);
    expect(normalizeApiTimeout(0)).toBe(60_000);
    expect(normalizeApiTimeout(12.8)).toBe(12);
  });

  it("turns a deadline abort into an actionable timeout error", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", pendingFetch());

    const request = fetchJson("/slow", undefined, 25);
    const rejection = request.catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(25);

    expect(await rejection).toEqual(
      expect.objectContaining({
        message: expect.stringContaining("did not respond within 1 seconds")
      })
    );
    expect(reportClientError).toHaveBeenCalledWith("api_timeout", expect.objectContaining({ failure: "timeout" }));
  });

  it("preserves caller-initiated cancellation", async () => {
    vi.stubGlobal("fetch", pendingFetch());
    const controller = new AbortController();

    const request = fetchJson("/cancelled", controller.signal, 10_000);
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
    expect(reportClientError).not.toHaveBeenCalled();
  });

  it("distinguishes browser-level cancellation from caller cancellation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("private message", "AbortError")));
    await expect(fetchJson("/api/map-data?geoid=private")).rejects.toThrow("Check your connection");
    expect(reportClientError).toHaveBeenCalledWith("api_network", expect.objectContaining({ operation: "map", failure: "browser_abort" }));
  });

  it("reports malformed successful JSON separately from network and HTTP errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not JSON", { status: 200 })));
    await expect(fetchJson("/api/compare?ids=private")).rejects.toThrow("The data service returned unreadable data. Please try again.");
    expect(reportClientError).toHaveBeenCalledExactlyOnceWith("api_decode", expect.objectContaining({ operation: "compare", failure: "decode" }));
  });
});
