import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchJson, normalizeApiTimeout } from "@/lib/api";


afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
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
  });

  it("preserves caller-initiated cancellation", async () => {
    vi.stubGlobal("fetch", pendingFetch());
    const controller = new AbortController();

    const request = fetchJson("/cancelled", controller.signal, 10_000);
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
});
