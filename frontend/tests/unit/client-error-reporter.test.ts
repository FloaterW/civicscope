import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => { vi.resetModules(); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("client error reporter", () => {
  it("sends sanitized, bounded production context once per category", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubGlobal("window", {});
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { reportClientError } = await import("@/lib/error-reporting");
    const context = { operation: "map" as const, failure: "network" as const, duration: "over_60s" as const,
      status: 503, online: true, visibility: "visible" as const, secret: "must not be sent" };
    reportClientError("api_network", context);
    reportClientError("api_network", context);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/client-errors");
    expect(options.credentials).toBe("omit");
    expect(options.body).not.toContain("secret");
    expect(options.body).not.toContain("must not");
    expect(new TextEncoder().encode(options.body).length).toBeLessThanOrEqual(256);
    expect(JSON.parse(options.body).context.status).toBe(503);
  });

  it("does not send development or server-render reports", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubGlobal("window", {});
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { reportClientError } = await import("@/lib/error-reporting");
    reportClientError("render");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubGlobal("window", undefined);
    reportClientError("render");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
