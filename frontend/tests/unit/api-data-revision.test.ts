import { afterEach, expect, it, vi } from "vitest";
import { CORE_DATA_REVISION, getComparison, getMapData, getSummary, searchGeographies } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

it("revises and revalidates core payloads while preserving selection parameters", async () => {
  const calls: Array<{ url: URL; cache?: RequestCache }> = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url: new URL(url), cache: init.cache });
    return new Response("{}");
  }));
  await getMapData("population", "municipality");
  await getMapData("average_rent_total", "census_tract", undefined, 2024);
  await getSummary("3520005", "municipality", undefined, 2025);
  await getComparison(["3520005", "3524001"], "municipality", undefined, 2025);
  expect(calls.map(call => call.url.pathname)).toEqual(["/api/map-data", "/api/map-data", "/api/summary", "/api/compare"]);
  for (const call of calls) {
    expect(call.url.searchParams.get("data_revision")).toBe(CORE_DATA_REVISION);
    expect(call.cache).toBe("no-cache");
  }
  expect(calls[0].url.searchParams.get("metric")).toBe("population");
  expect(calls[1].url.searchParams.get("year")).toBe("2024");
  expect(calls[1].url.searchParams.get("type")).toBe("census_tract");
  expect(calls[2].url.searchParams.get("ids")).toBe("3520005");
  expect(calls[3].url.searchParams.get("ids")).toBe("3520005,3524001");
});

it("leaves search caching unchanged and does not add a revision to user input", async () => {
  const fetchMock = vi.fn(async () => new Response("{}"));
  vi.stubGlobal("fetch", fetchMock);
  await searchGeographies(" Toronto ", "municipality");
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(new URL(url).searchParams.get("search")).toBe("Toronto");
  expect(new URL(url).searchParams.has("data_revision")).toBe(false);
  expect(init.cache).toBe("default");
});
