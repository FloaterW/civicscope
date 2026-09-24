import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const origin = "https://civicscope.example";
const request = (body: string, headers: Record<string, string> = {}) => new Request(`${origin}/api/client-errors`, {
  method: "POST", headers: { origin, "content-type": "application/json", ...headers }, body
});

describe("privacy-preserving client error endpoint", () => {
  beforeEach(() => { vi.resetModules(); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("rejects cross-origin reports before logging", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const { POST } = await import("@/app/api/client-errors/route");
    expect((await POST(request('{"code":"render"}', { origin: "https://attacker.example" }))).status).toBe(403);
    expect(log).not.toHaveBeenCalled();
  });

  it.each(["null", "[]", "{", '{"code":"private error message"}', '{"code":123}', "{}"])("rejects invalid report %s", async (body) => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const { POST } = await import("@/app/api/client-errors/route");
    expect((await POST(request(body))).status).toBe(400);
    expect(log).not.toHaveBeenCalled();
  });

  it("enforces content type and actual UTF-8 byte length", async () => {
    const { POST } = await import("@/app/api/client-errors/route");
    expect((await POST(request('{"code":"render"}', { "content-type": "text/plain" }))).status).toBe(415);
    expect((await POST(request(JSON.stringify({ code: "render", message: "é".repeat(130) })))).status).toBe(413);
  });

  it("logs only fixed category and release, omitting arbitrary personal fields and deduplicating reports", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "test-release");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const now = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
    const { POST } = await import("@/app/api/client-errors/route");
    const body = JSON.stringify({ code: "render", email: "private@example.test", stack: "private stack", query: "private query" });
    const response = await POST(request(body));
    expect(response.status).toBe(204);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(log).toHaveBeenCalledExactlyOnceWith(JSON.stringify({ event: "client_error", code: "render", release: "test-release" }));
    await POST(request(body));
    expect(log).toHaveBeenCalledTimes(1);
    now.mockReturnValue(1_060_000);
    await POST(request(body));
    expect(log).toHaveBeenCalledTimes(2);
  });

  it("accepts bounded diagnostic fields but strips arbitrary nested values", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "test-release");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const { POST } = await import("@/app/api/client-errors/route");
    const response = await POST(request(JSON.stringify({ code: "api_network", context: {
      operation: "search", failure: "network", duration: "under_1s", online: false,
      visibility: "visible", url: "private", message: "private"
    } })));
    expect(response.status).toBe(204);
    expect(JSON.parse(log.mock.calls[0][0])).toEqual({ event: "client_error", code: "api_network", release: "test-release",
      context: { operation: "search", failure: "network", duration: "under_1s", online: false, visibility: "visible" } });
  });
});
