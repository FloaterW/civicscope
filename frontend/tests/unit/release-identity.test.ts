import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "@/app/api/release/route";

afterEach(() => vi.unstubAllEnvs());

describe("public release identity", () => {
  it("reports the provider commit instead of a stale local override, without caching", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "A".repeat(40));
    vi.stubEnv("CIVICSCOPE_BUILD_SHA", "b".repeat(40));
    const response = await GET();
    expect(await response.json()).toEqual({ service: "civicscope-frontend", commit: "a".repeat(40) });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it.each(["", "main", "a".repeat(7), "g".repeat(40), "a".repeat(40) + "\n", "private-token"])("does not expose invalid environment %j", async value => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", value);
    vi.stubEnv("CIVICSCOPE_BUILD_SHA", "b".repeat(40));
    expect((await (await GET()).json()).commit).toBeNull();
  });

  it("supports local builds and explicit unknown identity", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", undefined);
    vi.stubEnv("CIVICSCOPE_BUILD_SHA", "c".repeat(40));
    expect((await (await GET()).json()).commit).toBe("c".repeat(40));
    vi.stubEnv("CIVICSCOPE_BUILD_SHA", undefined);
    expect((await (await GET()).json()).commit).toBeNull();
  });
});
