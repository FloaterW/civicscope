import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "@/app/api/trreb-archive/resale/[geoid]/route";
import { readArchivedResale, SOURCE_RELEASE } from "@/lib/server/trreb-archive";
import archive from "@/data/trreb-resale-2020-2025.json";
import { API_BASE, fetchJson } from "@/lib/api";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
const request = (query = "", geoid = "3520005") => GET(new Request(`https://example.test/api/trreb-archive/resale/${geoid}${query}`), { params: Promise.resolve({ geoid }) });

describe("approved public TRREB archive", () => {
  it("delivers all 1,950 unchanged observations with complete six-year coverage", () => {
    expect(Object.keys(archive).sort()).toEqual(["observations", "schema_version", "source_release"]);
    expect(archive.observations).toHaveLength(1950);
    const ids = new Set(archive.observations.map(row => row.geoid));
    expect(ids.size).toBe(25);
    for (const id of ids) for (let year = 2020; year <= 2025; year++) for (let month = 0; month <= 12; month++) {
      const row = readArchivedResale(id, year, month || undefined)!;
      expect(row).toBeDefined();
      expect(row.release_id).toBe(SOURCE_RELEASE);
      const { release_id, archive_sha256, preview_only, ...original } = row;
      expect({ release_id, archive_sha256, preview_only }).toMatchObject({ release_id: SOURCE_RELEASE, preview_only: false });
      expect(archive.observations.find(item => item.geoid === id && item.period === row.period)).toEqual(original);
    }
  });
  it("returns actual monthly and year-end Toronto figures, with provenance and no-store", async () => {
    const monthly = await request("?year=2020&month=1");
    expect(monthly.status).toBe(200);
    expect(monthly.headers.get("cache-control")).toBe("no-store");
    expect(await monthly.json()).toMatchObject({ period: "2020-01", median_price: 725000, sales: 1603, property_days: 33, source_page: 3, preview_only: false });
    expect(await (await request()).json()).toMatchObject({ period: "2025", median_price: 855000, sales: 23196, property_days: 44, source_page: 5 });
  });
  it.each(["?year=2019", "?year=2026", "?year=", "?year=2025.0", "?year=2025&year=2020", "?month=0", "?month=13", "?month=1.5", "?month=", "?month=1&month=2"])("rejects invalid period %s", async query => {
    expect((await request(query)).status).toBe(422);
  });
  it.each(["5350400.16", "9999999", "__proto__", "3520005junk"])("does not allocate/fallback for %s", async id => {
    expect((await request("", id)).status).toBe(404);
  });
  it("supports emergency server-side disable without changing the archive", async () => {
    vi.stubEnv("TRREB_ARCHIVE_DISABLED", "1");
    expect((await request()).status).toBe(404);
  });
  it("fetches the archive on the website origin, leaving existing API routing unchanged", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(Response.json({ ok: true })));
    vi.stubGlobal("fetch", fetch);
    await fetchJson("/api/trreb-archive/resale/3520005", undefined, 1000, "same-origin");
    expect(fetch.mock.calls[0][0]).toBe("/api/trreb-archive/resale/3520005");
    await fetchJson("/api/summary");
    expect(fetch.mock.calls[1][0]).toBe(`${API_BASE}/api/summary`);
  });
});
