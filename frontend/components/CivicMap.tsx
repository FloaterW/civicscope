"use client";

import type { FilterSpecification, LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { MapData, MapFeature, MetricKey } from "@/types";

type Props = {
  data: MapData | null;
  loading: boolean;
  metric: MetricKey;
  selectedGeoid?: string;
  onSelect: (feature: MapFeature["properties"]) => void;
};

const sourceId = "civic-geographies";
const basemapSourceId = "carto-light";
const placesSourceId = "gta-reference-places";
const fillLayerId = "civic-geographies-fill";
const selectedFillLayerId = "civic-geographies-selected-fill";
const lineLayerId = "civic-geographies-line";
const selectedLineLayerId = "civic-geographies-selected";
const placeCircleLayerId = "gta-reference-places-circle";

const referencePlaces = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.3832, 43.6532] }, properties: { name: "Toronto" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.6441, 43.589] }, properties: { name: "Mississauga" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.7624, 43.7315] }, properties: { name: "Brampton" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.5085, 43.8561] }, properties: { name: "Vaughan" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.337, 43.8561] }, properties: { name: "Markham" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-78.8658, 43.8971] }, properties: { name: "Oshawa" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.6877, 43.4643] }, properties: { name: "Oakville" } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-79.8711, 43.3255] }, properties: { name: "Burlington" } }
  ]
};

export function CivicMap({ data, loading, metric, selectedGeoid, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const isReady = Boolean(data);
  const loadedMetric = data?.metadata.metric ?? null;

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !data) {
      return;
    }

    let cancelled = false;
    const initialData = data;

    async function initializeMap() {
      const maplibregl = (await import("maplibre-gl")).default;
      if (cancelled || !containerRef.current) {
        return;
      }

      const map = new maplibregl.Map({
        container: containerRef.current,
        center: [-79.45, 43.78],
        zoom: 8.15,
        minZoom: 7,
        maxZoom: 12.5,
        style: {
          version: 8,
          glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
          sources: {
            [basemapSourceId]: {
              type: "raster",
              tiles: [
                "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
                "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
                "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
              ],
              tileSize: 256,
              attribution: "OpenStreetMap contributors, CARTO"
            },
            [sourceId]: {
              type: "geojson",
              data: initialData as never
            },
            [placesSourceId]: {
              type: "geojson",
              data: referencePlaces as never
            }
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: {
                "background-color": "#eef2ed"
              }
            },
            {
              id: "carto-light-basemap",
              type: "raster",
              source: basemapSourceId,
              paint: {
                "raster-opacity": 0.82
              }
            },
            {
              id: fillLayerId,
              type: "fill",
              source: sourceId,
              paint: {
                "fill-color": colorExpression(initialData),
                "fill-opacity": 0.68
              } as never
            },
            {
              id: lineLayerId,
              type: "line",
              source: sourceId,
              paint: {
                "line-color": "#314154",
                "line-width": [
                  "case",
                  ["==", ["get", "type"], "census_tract"],
                  0.45,
                  1
                ],
                "line-opacity": [
                  "case",
                  ["==", ["get", "type"], "census_tract"],
                  0.32,
                  0.45
                ]
              } as never
            },
            {
              id: selectedFillLayerId,
              type: "fill",
              source: sourceId,
              filter: ["==", ["get", "geoid"], selectedGeoid ?? ""],
              paint: {
                "fill-color": "#fef3c7",
                "fill-opacity": 0.5
              }
            },
            {
              id: selectedLineLayerId,
              type: "line",
              source: sourceId,
              filter: ["==", ["get", "geoid"], selectedGeoid ?? ""],
              paint: {
                "line-color": "#0f172a",
                "line-width": 4,
                "line-opacity": 0.95
              }
            },
            {
              id: placeCircleLayerId,
              type: "circle",
              source: placesSourceId,
              paint: {
                "circle-color": "#ffffff",
                "circle-radius": 4,
                "circle-stroke-color": "#117c78",
                "circle-stroke-width": 2
              }
            }
          ]
        }
      });

      map.on("error", (event) => {
        const mapError = event.error;
        const message = mapError?.message ?? "";
        if (
          message.includes("Failed to fetch") ||
          message.includes("NetworkError") ||
          message.includes("Load failed")
        ) {
          console.warn(
            "Optional basemap asset failed to load; continuing with CivicScope geography layers.",
            message
          );
          return;
        }

        console.error(mapError ?? event);
      });

      map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
      map.on("load", () => {
        fitToDataBounds(map, initialData, false);
      });

      map.on("click", fillLayerId, (event) => {
        const feature = event.features?.[0];
        if (!feature) {
          return;
        }
        onSelectRef.current(normalizeFeatureProperties(feature));
      });

      map.on("mousemove", fillLayerId, () => {
        map.getCanvas().style.cursor = "pointer";
      });

      map.on("mouseleave", fillLayerId, () => {
        map.getCanvas().style.cursor = "";
      });

      mapRef.current = map;
    }

    initializeMap();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [isReady]);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(sourceId);
    if (!map || !data || !source) {
      return;
    }
    if ("setData" in source) {
      (source as { setData: (payload: never) => void }).setData(data as never);
    }
    if (map.getLayer(fillLayerId)) {
      map.setPaintProperty(fillLayerId, "fill-color", colorExpression(data));
    }
  }, [data, metric]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(selectedLineLayerId)) {
      return;
    }
    const selectedFilter: FilterSpecification = ["==", ["get", "geoid"], selectedGeoid ?? ""];
    if (map.getLayer(selectedFillLayerId)) {
      map.setFilter(selectedFillLayerId, selectedFilter);
    }
    map.setFilter(selectedLineLayerId, selectedFilter);
    if (!selectedGeoid) {
      fitToDataBounds(map, data, true);
      return;
    }
    const selectedFeature = data?.features.find(
      (feature) => feature.properties.geoid === selectedGeoid
    );
    if (selectedFeature?.properties.bbox) {
      const [minLng, minLat, maxLng, maxLat] = selectedFeature.properties.bbox;
      map.fitBounds(
        [
          [minLng, minLat],
          [maxLng, maxLat]
        ],
        {
          padding: 96,
          maxZoom: data?.metadata.geography_type === "census_tract" ? 11.35 : 9.15,
          duration: 650
        }
      );
    }
  }, [data, selectedGeoid]);

  return (
    <div
      data-testid="civic-map"
      data-feature-count={data?.features.length ?? 0}
      data-metric={loadedMetric ?? ""}
      data-requested-metric={metric}
      data-selected-geoid={selectedGeoid ?? ""}
      data-geography-type={data?.metadata.geography_type ?? ""}
      data-domain-min={data?.metadata.domain.min ?? ""}
      data-domain-max={data?.metadata.domain.max ?? ""}
      className="relative h-full w-full"
    >
      {!data && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-white text-sm text-civic-muted">
          Loading map data...
        </div>
      )}
      {data && loading && loadedMetric !== metric && (
        <div className="absolute right-3 top-3 z-10 rounded-md border border-civic-line bg-white/95 px-3 py-2 text-xs font-medium text-civic-ink shadow-panel">
          Updating map...
        </div>
      )}
      <div ref={containerRef} data-testid="map-canvas-host" className="h-full w-full" />
      {data && (
        <div className="absolute bottom-3 left-3 rounded-md border border-civic-line bg-white/95 px-3 py-2 text-xs shadow-panel">
          <div className="mb-1 font-semibold text-civic-ink">Value range</div>
          <div className="flex items-center gap-2 text-civic-muted">
            <span>{formatLegendValue(data.metadata.domain.min)}</span>
            <span className="h-2 w-28 rounded-full bg-gradient-to-r from-[#f1f7f0] via-[#68b7aa] to-[#a64822]" />
            <span>{formatLegendValue(data.metadata.domain.max)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function colorExpression(data: MapData): unknown[] {
  const min = data.metadata.domain.min ?? 0;
  const max = data.metadata.domain.max ?? 1;
  const mid = min + (max - min) / 2 || 1;
  return [
    "case",
    ["==", ["get", "value"], null],
    "#d8dee6",
    [
      "interpolate",
      ["linear"],
      ["to-number", ["get", "value"]],
      min,
      "#f1f7f0",
      mid,
      "#68b7aa",
      max,
      "#a64822"
    ]
  ];
}

function normalizeFeatureProperties(feature: {
  properties?: Record<string, unknown> | null;
  geometry: unknown;
}): MapFeature["properties"] {
  const properties = feature.properties ?? {};
  const metrics =
    typeof properties.metrics === "string"
      ? JSON.parse(properties.metrics)
      : properties.metrics;
  const bbox =
    typeof properties.bbox === "string" ? JSON.parse(properties.bbox) : properties.bbox;

  return {
    id: Number(properties.id),
    geoid: String(properties.geoid),
    name: String(properties.name),
    type: String(properties.type),
    county: properties.county ? String(properties.county) : null,
    state: String(properties.state ?? "ON"),
    bbox: bbox as [number, number, number, number],
    geometry: feature.geometry as unknown as MapFeature["geometry"],
    geometry_source: String(properties.geometry_source),
    metric: String(properties.metric) as MetricKey,
    value: properties.value === null ? null : Number(properties.value),
    metrics: metrics as MapFeature["properties"]["metrics"]
  };
}

function formatLegendValue(value: number | null): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return Math.abs(value) >= 1000
    ? new Intl.NumberFormat("en-US", { notation: "compact" }).format(value)
    : value.toFixed(1);
}

function getDataBounds(data?: MapData | null): LngLatBoundsLike | null {
  if (!data?.features.length) {
    return null;
  }

  const bounds = data.features.reduce<[number, number, number, number] | null>(
    (current, feature) => {
      const bbox = feature.properties.bbox;
      if (!bbox || bbox.some((value) => !Number.isFinite(value))) {
        return current;
      }
      if (!current) {
        return [...bbox];
      }
      return [
        Math.min(current[0], bbox[0]),
        Math.min(current[1], bbox[1]),
        Math.max(current[2], bbox[2]),
        Math.max(current[3], bbox[3])
      ];
    },
    null
  );

  if (!bounds) {
    return null;
  }

  return [
    [bounds[0], bounds[1]],
    [bounds[2], bounds[3]]
  ];
}

function fitToDataBounds(map: MapLibreMap, data?: MapData | null, animated = true) {
  const bounds = getDataBounds(data);
  if (!bounds) {
    return;
  }

  map.fitBounds(bounds, {
    padding: 40,
    maxZoom: 8.65,
    duration: animated ? 450 : 0
  });
}
