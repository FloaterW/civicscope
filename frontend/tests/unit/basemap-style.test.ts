import { describe, expect, it, vi } from "vitest";
import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import type { LineLayerSpecification, StyleSpecification } from "maplibre-gl";
import { normalizeBasemapStyle } from "@/lib/basemap-style";

const boundary: LineLayerSpecification = {
  id: "boundary_3", type: "line", source: "openmaptiles", "source-layer": "boundary",
  filter: ["all", [">=", ["get", "admin_level"], 3], ["<=", ["get", "admin_level"], 6],
    ["!=", ["get", "maritime"], 1], ["!=", ["get", "disputed"], 1], ["!", ["has", "claimed_by"]]]
};
const style: StyleSpecification = { version: 8, sources: {}, layers: [boundary, { id: "background", type: "background" }] };

describe("basemap boundary filter", () => {
  it("excludes invalid levels without warnings, preserving valid range and exclusions", () => {
    const normalized = normalizeBasemapStyle(style);
    const compiled = featureFilter((normalized.layers[0] as LineLayerSpecification).filter, "test");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      for (const level of [undefined, null, "unknown", "4", 2, 7]) {
        expect(compiled.filter({ zoom: 10 }, { type: "LineString", properties: { admin_level: level } })).toBe(false);
      }
      for (const level of [3, 4, 5, 6]) {
        expect(compiled.filter({ zoom: 10 }, { type: "LineString", properties: { admin_level: level } })).toBe(true);
      }
      for (const extra of [{ maritime: 1 }, { disputed: 1 }, { claimed_by: "example" }]) {
        expect(compiled.filter({ zoom: 10 }, { type: "LineString", properties: { admin_level: 4, ...extra } })).toBe(false);
      }
      expect(warn).not.toHaveBeenCalled();
    } finally { warn.mockRestore(); }
    expect(style.layers[0]).toBe(boundary);
    expect(normalized.layers[1]).toBe(style.layers[1]);
    expect(normalizeBasemapStyle(normalized)).toEqual(normalized);
  });

  it("does not override an upstream filter revision or unrelated layer", () => {
    const revised: LineLayerSpecification = { ...boundary, filter: ["==", ["get", "admin_level"], 4] };
    expect(normalizeBasemapStyle({ ...style, layers: [revised] }).layers[0]).toBe(revised);
    const other: LineLayerSpecification = { ...boundary, id: "other" };
    expect(normalizeBasemapStyle({ ...style, layers: [other] }).layers[0]).toBe(other);
  });
});
