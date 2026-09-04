import { describe, expect, it } from "vitest";

import {
  allTransitFiltersEnabled,
  anyTransitFilterEnabled,
  buildTransitFilter,
  isTransitFeatureCollection,
  TRANSIT_FILTERS_OFF,
  TRANSIT_FILTERS_ON,
  transitRouteLabels
} from "@/lib/transit-map";

describe("transit map filters", () => {
  it("represents no enabled routes with an always-empty filter", () => {
    expect(anyTransitFilterEnabled(TRANSIT_FILTERS_OFF)).toBe(false);
    expect(allTransitFiltersEnabled(TRANSIT_FILTERS_OFF)).toBe(false);
    expect(buildTransitFilter(TRANSIT_FILTERS_OFF)).toEqual([
      "==",
      "transit_category",
      "__none__"
    ]);
  });

  it("omits the MapLibre filter when every route category is enabled", () => {
    expect(anyTransitFilterEnabled(TRANSIT_FILTERS_ON)).toBe(true);
    expect(allTransitFiltersEnabled(TRANSIT_FILTERS_ON)).toBe(true);
    expect(buildTransitFilter(TRANSIT_FILTERS_ON)).toBeUndefined();
  });

  it("builds exact one-category and multi-category filters", () => {
    const one = { ...TRANSIT_FILTERS_OFF, go_transit: true };
    const many = { ...one, miway: true };

    expect(buildTransitFilter(one)).toEqual(["==", "transit_category", "go_transit"]);
    expect(buildTransitFilter(many)).toEqual([
      "in",
      "transit_category",
      "go_transit",
      "miway"
    ]);
  });
});

describe("transit route payloads", () => {
  const validRoutes = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [[-79.4, 43.7], [-79.3, 43.8]]
        },
        properties: {
          agency: "TTC",
          route_name: "1",
          route_long_name: "Yonge–University",
          route_type: "Subway",
          color: "#C23030",
          transit_category: "ttc_subway"
        }
      }
    ]
  } as const;

  it("accepts a non-empty, well-formed transit FeatureCollection", () => {
    expect(isTransitFeatureCollection(validRoutes)).toBe(true);
  });

  it("rejects empty and malformed transit payloads", () => {
    expect(isTransitFeatureCollection({ type: "FeatureCollection", features: [] })).toBe(false);
    expect(isTransitFeatureCollection({ type: "FeatureCollection", features: [{}] })).toBe(false);
    expect(isTransitFeatureCollection({ type: "not-geojson", features: validRoutes.features })).toBe(false);
  });

  it("builds deduplicated labels for keyboard-accessible route details", () => {
    if (!isTransitFeatureCollection(validRoutes)) throw new Error("Fixture should be valid");
    expect(transitRouteLabels(validRoutes)).toEqual([
      "TTC — Route 1 — Yonge–University"
    ]);
  });
});
