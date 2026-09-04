"use client";

import type { FilterSpecification, LngLatBoundsLike, Map as MapLibreMap, Popup } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatMetric, getMetricLabel, getTransitRoutes } from "@/lib/api";
import {
  buildChoroplethScale,
  choroplethColorExpression,
  FLAT_COLOR,
  NULL_COLOR,
  type ChoroplethClass
} from "@/lib/colors";
import { mapAnimationDuration } from "@/lib/map-motion";
import {
  allTransitFiltersEnabled,
  anyTransitFilterEnabled,
  buildTransitFilter,
  TRANSIT_FILTERS_OFF,
  TRANSIT_FILTERS_ON,
  TRANSIT_LAYERS,
  transitRouteLabels,
  type TransitFeatureCollection,
  type TransitFilters
} from "@/lib/transit-map";
import { buildTooltipHtml, escapeHtml, safeJsonParse } from "@/lib/tooltip";
import type { GeographyLevel, MapData, MapFeature, MetricKey } from "@/types";

type Props = {
  data: MapData | null;
  loading: boolean;
  metric: MetricKey;
  geographyLevel: GeographyLevel;
  selectedGeoid?: string;
  onSelect: (feature: MapFeature["properties"]) => void;
  error?: string | null;
  onRetry?: () => void;
};

const sourceId = "civic-geographies";
const placesSourceId = "gta-reference-places";
const fillLayerId = "civic-geographies-fill";
const selectedFillLayerId = "civic-geographies-selected-fill";
const lineLayerId = "civic-geographies-line";
const selectedLineLayerId = "civic-geographies-selected";
const placeCircleLayerId = "gta-reference-places-circle";
const transitSourceId = "transit-routes";
const transitLineLayerId = "transit-routes-line";
const CIVIC_LAYER_IDS = new Set([
  fillLayerId,
  selectedFillLayerId,
  lineLayerId,
  selectedLineLayerId,
  placeCircleLayerId,
  transitLineLayerId
]);

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

function isDarkMode(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

const BASEMAP_STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark"
} as const;

const PRECISE_LEGEND_CURRENCY = new Intl.NumberFormat("en-CA", {
  style: "currency",
  currency: "CAD",
  maximumFractionDigits: 2
});
const PRECISE_LEGEND_NUMBER = new Intl.NumberFormat("en-CA", {
  maximumFractionDigits: 3
});

type ThemeName = keyof typeof BASEMAP_STYLES;

type TransitLoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded" }
  | { status: "error"; message: string };

function currentTheme(): ThemeName {
  return isDarkMode() ? "dark" : "light";
}

function applyTransitFilterState(
  map: MapLibreMap,
  filters: TransitFilters,
  routesAreLoaded: boolean
) {
  if (!map.getLayer(transitLineLayerId)) return;
  const anyEnabled = routesAreLoaded && anyTransitFilterEnabled(filters);
  map.setLayoutProperty(transitLineLayerId, "visibility", anyEnabled ? "visible" : "none");
  map.setFilter(transitLineLayerId, buildTransitFilter(filters) ?? null);
}

function firstLabelAboveBasemap(map: MapLibreMap): string | undefined {
  const layers = map.getStyle().layers;
  let lastNonSymbolIndex = -1;
  layers.forEach((layer, index) => {
    if (layer.type !== "symbol") lastNonSymbolIndex = index;
  });
  return layers.slice(lastNonSymbolIndex + 1).find((layer) => layer.type === "symbol")?.id;
}

function civicLayersAreAboveBasemap(map: MapLibreMap): boolean {
  const layers = map.getStyle().layers;
  const civicFillIndex = layers.findIndex((layer) => layer.id === fillLayerId);
  const lastBasemapNonSymbolIndex = layers.reduce(
    (last, layer, index) =>
      layer.type !== "symbol" && !CIVIC_LAYER_IDS.has(layer.id) ? index : last,
    -1
  );
  return civicFillIndex > lastBasemapNonSymbolIndex;
}

function addCivicLayers(
  map: MapLibreMap,
  data: MapData,
  selectedGeoid: string | undefined,
  theme: ThemeName,
  transitRoutes: unknown
) {
  if (!map.getSource(sourceId)) {
    map.addSource(sourceId, { type: "geojson", data: data as never });
  }
  if (!map.getSource(placesSourceId)) {
    map.addSource(placesSourceId, { type: "geojson", data: referencePlaces as never });
  }
  if (!map.getSource(transitSourceId)) {
    map.addSource(transitSourceId, {
      type: "geojson",
      data: (transitRoutes ?? { type: "FeatureCollection", features: [] }) as never
    });
  }

  // Some basemap styles interleave early symbol layers with later road/land
  // layers. Insert before the first label *after* every non-symbol basemap
  // layer so civic polygons cannot be painted underneath the basemap.
  const firstSymbolLayer = firstLabelAboveBasemap(map);
  if (!map.getLayer(fillLayerId)) {
    map.addLayer(
      {
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": choroplethColorExpression(data),
          "fill-opacity": 0.68
        } as never
      },
      firstSymbolLayer
    );
  }
  if (!map.getLayer(lineLayerId)) {
    map.addLayer(
      {
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#314154",
          "line-width": ["case", ["==", ["get", "type"], "census_tract"], 0.45, 1],
          "line-opacity": ["case", ["==", ["get", "type"], "census_tract"], 0.32, 0.45]
        } as never
      },
      firstSymbolLayer
    );
  }
  if (!map.getLayer(selectedFillLayerId)) {
    map.addLayer(
      {
        id: selectedFillLayerId,
        type: "fill",
        source: sourceId,
        filter: ["==", ["get", "geoid"], selectedGeoid ?? ""],
        paint: { "fill-color": "#ffffff", "fill-opacity": 0.2 }
      },
      firstSymbolLayer
    );
  }
  if (!map.getLayer(selectedLineLayerId)) {
    map.addLayer(
      {
        id: selectedLineLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "geoid"], selectedGeoid ?? ""],
        paint: {
          "line-color": theme === "dark" ? "#f8fafc" : "#0f172a",
          "line-width": 4,
          "line-opacity": 0.95
        }
      },
      firstSymbolLayer
    );
  }
  if (!map.getLayer(transitLineLayerId)) {
    map.addLayer(
      {
        id: transitLineLayerId,
        type: "line",
        source: transitSourceId,
        layout: {
          "line-cap": "round",
          "line-join": "round",
          visibility: "none"
        },
        paint: {
          "line-color": ["get", "color"],
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            7, ["case", ["==", ["get", "transit_category"], "ttc_subway"], 2, 0.8],
            10, ["case", ["==", ["get", "transit_category"], "ttc_subway"], 4, 2],
            12, ["case", ["==", ["get", "transit_category"], "ttc_subway"], 5.5, 3]
          ],
          "line-opacity": ["case", ["==", ["get", "transit_category"], "ttc_subway"], 0.9, 0.65]
        } as never
      },
      firstSymbolLayer
    );
  }
  if (!map.getLayer(placeCircleLayerId)) {
    map.addLayer(
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
      },
      firstSymbolLayer
    );
  }
}

export function CivicMap({
  data,
  loading,
  metric,
  geographyLevel,
  selectedGeoid,
  onSelect,
  error,
  onRetry
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const mapReadyRef = useRef(false);
  const initialViewportAppliedRef = useRef(false);
  const pendingViewportFitRef = useRef(true);
  const [transitOpen, setTransitOpen] = useState(false);
  const [transitFilters, setTransitFilters] = useState<TransitFilters>({
    ...TRANSIT_FILTERS_OFF
  });
  const [transitLoadState, setTransitLoadState] = useState<TransitLoadState>({
    status: "idle"
  });
  const [transitRouteList, setTransitRouteList] = useState<string[]>([]);
  const [transitFeatureCount, setTransitFeatureCount] = useState(0);
  const [routeDetailsOpen, setRouteDetailsOpen] = useState(false);
  const onSelectRef = useRef(onSelect);
  const popupRef = useRef<Popup | null>(null);
  const latestDataRef = useRef<MapData | null>(data);
  const selectedGeoidRef = useRef(selectedGeoid);
  const transitFiltersRef = useRef<TransitFilters>(transitFilters);
  const transitRoutesRef = useRef<TransitFeatureCollection | null>(null);
  const transitRequestRef = useRef(0);
  const themeRef = useRef<ThemeName>(currentTheme());
  // The hover handler is registered once at init; read the live metric from a
  // ref so the tooltip always reflects the currently selected metric.
  const metricRef = useRef<MetricKey>(metric);
  const isReady = Boolean(data);
  const loadedMetric = data?.metadata.metric ?? null;

  // The same stepped quantile scale drives both paint and legend semantics.
  const legend = useMemo(() => (data ? buildChoroplethScale(data) : null), [data]);
  // Data loaded, but every geography is null for this metric (e.g. turnover /
  // availability, not collected in this dataset). Surface an explicit empty
  // state instead of a silently blank map.
  const dataIsEmpty = Boolean(
    data && data.metadata.domain.min === null && data.metadata.domain.max === null
  );

  const anyTransitOn = anyTransitFilterEnabled(transitFilters);

  const loadTransitRoutes = useCallback(async () => {
    const requestId = transitRequestRef.current + 1;
    transitRequestRef.current = requestId;
    setTransitLoadState({ status: "loading" });

    try {
      const geojson = await getTransitRoutes();
      if (requestId !== transitRequestRef.current) return;

      transitRoutesRef.current = geojson;
      setTransitRouteList(transitRouteLabels(geojson));
      setTransitFeatureCount(geojson.features.length);
      const map = mapRef.current;
      const source = map?.getSource(transitSourceId);
      if (source && "setData" in source) {
        (source as { setData: (payload: never) => void }).setData(geojson as never);
      }
      if (map && mapReadyRef.current) {
        applyTransitFilterState(map, transitFiltersRef.current, true);
      }
      setTransitLoadState({ status: "loaded" });
    } catch (transitError) {
      if (requestId !== transitRequestRef.current) return;
      transitRoutesRef.current = null;
      setTransitRouteList([]);
      setTransitFeatureCount(0);
      setRouteDetailsOpen(false);
      const map = mapRef.current;
      if (map && mapReadyRef.current) {
        applyTransitFilterState(map, transitFiltersRef.current, false);
      }
      console.error("Transit route overlay failed to load.", transitError);
      setTransitLoadState({
        status: "error",
        message: "Transit lines could not be loaded. Check your connection and try again."
      });
    }
  }, []);

  useEffect(() => {
    transitFiltersRef.current = transitFilters;
    const map = mapRef.current;
    if (!map || !mapReadyRef.current || !map.getLayer(transitLineLayerId)) return;
    applyTransitFilterState(map, transitFilters, transitRoutesRef.current !== null);
  }, [transitFilters]);

  useEffect(
    () => () => {
      transitRequestRef.current += 1;
    },
    []
  );

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    metricRef.current = metric;
  }, [metric]);

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

      const theme = currentTheme();
      themeRef.current = theme;
      const map = new maplibregl.Map({
        container: containerRef.current,
        center: [-79.45, 43.78],
        zoom: 8.15,
        minZoom: 7,
        maxZoom: 12.5,
        style: BASEMAP_STYLES[theme]
      });

      const handleStyleLoad = () => {
        const latestData = latestDataRef.current ?? initialData;
        addCivicLayers(
          map,
          latestData,
          selectedGeoidRef.current,
          themeRef.current,
          transitRoutesRef.current
        );
        applyTransitFilterState(
          map,
          transitFiltersRef.current,
          transitRoutesRef.current !== null
        );
        containerRef.current?.setAttribute(
          "data-civic-layer-order",
          civicLayersAreAboveBasemap(map) ? "valid" : "invalid"
        );
        containerRef.current?.setAttribute("data-map-theme", themeRef.current);
        mapReadyRef.current = true;
        if (pendingViewportFitRef.current) {
          const didFitViewport = fitToCurrentGeography(
            map,
            latestData,
            selectedGeoidRef.current,
            false
          );
          if (didFitViewport) {
            pendingViewportFitRef.current = false;
            initialViewportAppliedRef.current = true;
          }
        }
      };
      map.on("style.load", handleStyleLoad);

      map.on("styleimagemissing", ({ id }) => {
        if (!map.hasImage(id)) {
          map.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
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
        mapReadyRef.current = true;
        if (!initialViewportAppliedRef.current) {
          const didFitViewport = fitToCurrentGeography(
            map,
            latestDataRef.current ?? initialData,
            selectedGeoidRef.current,
            false
          );
          initialViewportAppliedRef.current = didFitViewport;
          pendingViewportFitRef.current = !didFitViewport;
        }
      });

      map.on("click", fillLayerId, (event) => {
        const feature = event.features?.[0];
        if (!feature) {
          return;
        }
        onSelectRef.current(normalizeFeatureProperties(feature));
      });

      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 8,
        className: "civic-map-popup"
      });
      popupRef.current = popup;

      map.on("mousemove", fillLayerId, (event) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = event.features?.[0];
        if (!feature) {
          popup.remove();
          return;
        }
        const html = buildTooltipHtml(feature.properties ?? {}, metricRef.current);
        if (!html) {
          popup.remove();
          return;
        }
        popup.setLngLat(event.lngLat).setHTML(html).addTo(map);
      });

      map.on("mouseleave", fillLayerId, () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      map.on("mousemove", transitLineLayerId, (event) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = event.features?.[0];
        if (!feature) { popup.remove(); return; }
        const p = feature.properties ?? {};
        const name = escapeHtml(String(p.route_long_name || p.route_name || ""));
        const agency = escapeHtml(String(p.agency || ""));
        const type = escapeHtml(String(p.route_type || ""));
        popup.setLngLat(event.lngLat).setHTML(
          `<div style="font-size:12px;line-height:1.4"><strong>${agency}</strong><br/>${p.route_name ? `Route ${escapeHtml(String(p.route_name))} — ` : ""}${name}<br/><span style="color:#6b7280">${type}</span></div>`
        ).addTo(map);
      });

      map.on("mouseleave", transitLineLayerId, () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      mapRef.current = map;
    }

    initializeMap();

    return () => {
      cancelled = true;
      mapReadyRef.current = false;
      initialViewportAppliedRef.current = false;
      pendingViewportFitRef.current = true;
      if (popupRef.current) {
        popupRef.current.remove();
        popupRef.current = null;
      }
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map initializes once when data first arrives; subsequent data/selection updates are handled by separate effects below
  }, [isReady]);

  useEffect(() => {
    latestDataRef.current = data;
    const map = mapRef.current;
    if (!map || !data || !mapReadyRef.current) {
      return;
    }
    const source = map.getSource(sourceId);
    if (!source) {
      return;
    }
    if ("setData" in source) {
      (source as { setData: (payload: never) => void }).setData(data as never);
    }
    if (map.getLayer(fillLayerId)) {
      map.setPaintProperty(fillLayerId, "fill-color", choroplethColorExpression(data));
    }
  }, [data, metric]);

  useEffect(() => {
    selectedGeoidRef.current = selectedGeoid;
    const map = mapRef.current;
    if (!map || !mapReadyRef.current || !map.getLayer(selectedLineLayerId)) {
      pendingViewportFitRef.current = true;
      return;
    }
    const selectedFilter: FilterSpecification = ["==", ["get", "geoid"], selectedGeoid ?? ""];
    if (map.getLayer(selectedFillLayerId)) {
      map.setFilter(selectedFillLayerId, selectedFilter);
    }
    map.setFilter(selectedLineLayerId, selectedFilter);
    const didFitViewport = fitToCurrentGeography(map, data, selectedGeoid, true);
    pendingViewportFitRef.current = !didFitViewport;
    if (didFitViewport) initialViewportAppliedRef.current = true;
  }, [data, selectedGeoid]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const map = mapRef.current;
      if (!map) return;
      const theme = currentTheme();
      if (themeRef.current === theme) return;
      themeRef.current = theme;
      mapReadyRef.current = false;
      containerRef.current?.setAttribute("data-civic-layer-order", "loading");
      popupRef.current?.remove();
      // Force a full style lifecycle. URL-to-URL diffing can complete without a
      // new map-level style.load event, leaving custom sources absent.
      map.setStyle(BASEMAP_STYLES[theme], { diff: false });
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

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
      data-scale-min={legend?.min ?? ""}
      data-scale-max={legend?.max ?? ""}
      data-transit-status={transitLoadState.status}
      data-transit-feature-count={transitFeatureCount}
      data-transit-visible={
        transitLoadState.status === "loaded" && anyTransitOn ? "true" : "false"
      }
      data-empty={dataIsEmpty ? "true" : "false"}
      role="region"
      aria-busy={loading}
      aria-label={`Map of ${getMetricLabel(metric)} by ${
        (data?.metadata.geography_type ?? geographyLevel) === "census_tract"
          ? "census tract"
          : "municipality"
      }. Use the search box to inspect a specific geography.`}
      className="relative h-full w-full"
    >
      {!data && loading && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-civic-panel text-sm text-civic-muted">
          <div className="flex flex-col items-center gap-3">
            <div className="skeleton h-3 w-40" />
            <div className="skeleton h-3 w-28" />
          </div>
        </div>
      )}
      {!data && !loading && error && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-civic-panel p-6 text-center">
          <div>
            <p className="text-sm font-semibold text-civic-ink">Map data is unavailable</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-civic-muted">{error}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 rounded-md border border-civic-line px-3 py-1.5 text-xs font-semibold text-civic-ink hover:bg-civic-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel"
              >
                Retry map
              </button>
            )}
          </div>
        </div>
      )}
      {data && loading && loadedMetric !== metric && (
        <div role="status" className="absolute right-3 top-3 z-10 animate-fade-in rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs font-medium text-civic-ink shadow-panel backdrop-blur-sm">
          Updating map...
        </div>
      )}
      {dataIsEmpty && (
        <div
          data-testid="map-empty-state"
          role="status"
          className="pointer-events-none absolute inset-x-0 top-3 z-10 mx-auto w-fit max-w-[90%] rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-center text-xs text-civic-muted shadow-panel backdrop-blur-sm"
        >
          No data available for {getMetricLabel(metric)} in this dataset.
        </div>
      )}
      <div
        ref={containerRef}
        data-testid="map-canvas-host"
        data-civic-layer-order="loading"
        className="h-full w-full"
      />
      {data && legend && (
        <div
          data-testid="map-legend"
          aria-label={`${getMetricLabel(metric)} map legend`}
          className="absolute bottom-3 left-3 max-w-[230px] rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs shadow-panel backdrop-blur-sm"
        >
          <div className="mb-1.5 font-semibold text-civic-ink">{getMetricLabel(metric)}</div>
          {legend.classes.length === 0 ? (
            <p className="text-civic-muted">No values available</p>
          ) : legend.flat ? (
            <div data-legend-class className="flex items-center gap-2 text-civic-muted">
              <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-500 dark:border-slate-400" style={{ backgroundColor: FLAT_COLOR }} />
              <span className="tabular-nums">{formatMetric(metric, legend.classes[0].lower)}</span>
            </div>
          ) : (
            <div>
              <p className="mb-1 text-[11px] text-civic-muted">Grouped by quantiles</p>
              <ul className="space-y-1" aria-label="Quantile ranges">
                {legend.classes.map((colorClass, index) => (
                  <li
                    key={`${colorClass.lower}-${index}`}
                    data-legend-class
                    className="flex items-center gap-2 text-civic-muted"
                  >
                    <span
                      className="h-3 w-3 shrink-0 rounded-sm border border-slate-500 dark:border-slate-400"
                      style={{ backgroundColor: colorClass.color }}
                    />
                    <span className="tabular-nums">
                      {formatLegendClass(metric, colorClass)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div
            data-legend-no-data
            className="mt-1.5 flex items-center gap-2 border-t border-civic-line pt-1.5 text-civic-muted"
          >
            <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-500 dark:border-slate-400" style={{ backgroundColor: NULL_COLOR }} />
            <span>
              No data{legend.noDataCount > 0 ? ` (${legend.noDataCount.toLocaleString("en-CA")})` : ""}
            </span>
          </div>
        </div>
      )}
      {data && (
        <div className="absolute bottom-9 right-3 z-10 flex flex-col items-end gap-1.5">
          {transitOpen && (
            <div
              id="transit-layer-panel"
              className="animate-fade-in min-w-56 rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs shadow-panel backdrop-blur-sm"
            >
              <div className="mb-2 flex items-center justify-between gap-4">
                <span className="font-semibold text-civic-ink">Transit Lines</span>
                {transitLoadState.status === "loaded" && (
                  <button
                    type="button"
                    className="min-h-8 rounded px-2 py-1 text-[11px] text-civic-muted hover:text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal"
                    onClick={() => {
                      const allOn = allTransitFiltersEnabled(transitFilters);
                      setTransitFilters({
                        ...(allOn ? TRANSIT_FILTERS_OFF : TRANSIT_FILTERS_ON)
                      });
                    }}
                  >
                    {allTransitFiltersEnabled(transitFilters) ? "Clear all" : "Select all"}
                  </button>
                )}
              </div>
              {transitLoadState.status === "loading" && (
                <div role="status" className="flex items-center gap-2 py-2 text-civic-muted">
                  <span
                    aria-hidden="true"
                    className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-civic-line border-t-civic-teal motion-reduce:animate-none"
                  />
                  Loading transit lines…
                </div>
              )}
              {transitLoadState.status === "error" && (
                <div role="alert" className="max-w-64 py-1 text-civic-muted">
                  <p className="leading-5">{transitLoadState.message}</p>
                  <button
                    type="button"
                    onClick={loadTransitRoutes}
                    className="mt-2 min-h-9 rounded-md border border-civic-line px-2.5 py-1.5 font-semibold text-civic-ink hover:bg-civic-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal"
                  >
                    Retry transit lines
                  </button>
                </div>
              )}
              {transitLoadState.status === "loaded" && (
                <div>
                  <fieldset className="space-y-0.5">
                    <legend className="sr-only">Transit line filters</legend>
                    <div className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-civic-muted">TTC</div>
                    {TRANSIT_LAYERS.filter((layer) => layer.key.startsWith("ttc")).map((layer) => (
                      <TransitFilterOption
                        key={layer.key}
                        layer={layer}
                        checked={transitFilters[layer.key]}
                        label={layer.label.replace("TTC ", "")}
                        onToggle={() =>
                          setTransitFilters((previous) => ({
                            ...previous,
                            [layer.key]: !previous[layer.key]
                          }))
                        }
                      />
                    ))}
                    <div className="mb-0.5 mt-2 text-[11px] font-medium uppercase tracking-wider text-civic-muted">Regional</div>
                    {TRANSIT_LAYERS.filter((layer) => !layer.key.startsWith("ttc")).map((layer) => (
                      <TransitFilterOption
                        key={layer.key}
                        layer={layer}
                        checked={transitFilters[layer.key]}
                        label={layer.label}
                        onToggle={() =>
                          setTransitFilters((previous) => ({
                            ...previous,
                            [layer.key]: !previous[layer.key]
                          }))
                        }
                      />
                    ))}
                  </fieldset>
                  <button
                    type="button"
                    onClick={() => setRouteDetailsOpen((open) => !open)}
                    aria-expanded={routeDetailsOpen}
                    aria-controls="transit-route-details"
                    className="mt-2 w-full rounded-md border border-civic-line px-2 py-1.5 text-left text-[11px] font-medium text-civic-muted hover:bg-civic-subtle hover:text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal"
                  >
                    Browse route details ({transitRouteList.length})
                  </button>
                  {routeDetailsOpen && (
                    <ul
                      id="transit-route-details"
                      className="mt-1.5 max-h-36 space-y-1 overflow-y-auto rounded-md bg-civic-subtle p-2 text-civic-ink"
                    >
                      {transitRouteList.map((routeLabel) => (
                        <li key={routeLabel}>{routeLabel}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              if (!transitOpen) {
                setTransitOpen(true);
                if (!anyTransitOn) setTransitFilters({ ...TRANSIT_FILTERS_ON });
                if (
                  transitLoadState.status === "idle" ||
                  transitLoadState.status === "error"
                ) {
                  void loadTransitRoutes();
                }
              } else {
                setTransitOpen(false);
                setTransitFilters({ ...TRANSIT_FILTERS_OFF });
                setRouteDetailsOpen(false);
              }
            }}
            className={`flex min-h-9 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-panel focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel ${
              transitOpen
                ? "border-civic-teal bg-civic-teal text-white dark:text-slate-950"
                : "border-civic-line bg-civic-panel text-civic-muted hover:text-civic-ink"
            }`}
            aria-controls="transit-layer-panel"
            aria-expanded={transitOpen}
            aria-busy={transitLoadState.status === "loading"}
            title={transitOpen ? "Hide transit lines" : "Show transit lines"}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden="true"
            >
              <rect x="4" y="3" width="16" height="18" rx="2" />
              <path d="M12 3v18" />
              <path d="M4 9h16" />
              <path d="M4 15h16" />
            </svg>
            Transit
          </button>
        </div>
      )}
    </div>
  );
}

function TransitFilterOption({
  layer,
  checked,
  label,
  onToggle
}: {
  layer: (typeof TRANSIT_LAYERS)[number];
  checked: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <label className="flex min-h-8 cursor-pointer items-center gap-2 rounded px-0.5 text-civic-muted hover:text-civic-ink">
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        onChange={onToggle}
      />
      <span
        className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] border border-civic-line peer-checked:border-transparent peer-checked:text-white peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-civic-teal peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-civic-panel"
        style={checked ? { backgroundColor: layer.color } : undefined}
      >
        {checked && (
          <svg
            viewBox="0 0 12 12"
            className="h-2.5 w-2.5"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path d="M2.5 6l2.5 2.5 4.5-5" />
          </svg>
        )}
      </span>
      <span
        aria-hidden="true"
        className="h-0.5 w-3 shrink-0 rounded-full"
        style={{ backgroundColor: layer.color }}
      />
      {label}
    </label>
  );
}

function formatLegendClass(metric: MetricKey, colorClass: ChoroplethClass): string {
  let lower = formatMetric(metric, colorClass.lower);
  if (colorClass.upper === null) return `${lower} and above`;
  let upper = formatMetric(metric, colorClass.upper);
  if (lower === upper) {
    lower = formatPreciseLegendBoundary(metric, colorClass.lower);
    upper = formatPreciseLegendBoundary(metric, colorClass.upper);
  }
  return `${lower} to under ${upper}`;
}

function formatPreciseLegendBoundary(metric: MetricKey, value: number): string {
  const formatted = formatMetric(metric, value);
  if (formatted.startsWith("$")) {
    return PRECISE_LEGEND_CURRENCY.format(value);
  }
  if (formatted.endsWith("%")) {
    const percentage = metric === "rent_to_income_ratio" ? value * 100 : value;
    return `${PRECISE_LEGEND_NUMBER.format(percentage)}%`;
  }
  return PRECISE_LEGEND_NUMBER.format(value);
}

function normalizeFeatureProperties(feature: {
  properties?: Record<string, unknown> | null;
  geometry: unknown;
}): MapFeature["properties"] {
  const properties = feature.properties ?? {};
  const metrics = safeJsonParse(properties.metrics, {} as MapFeature["properties"]["metrics"]);
  const bbox = safeJsonParse(properties.bbox, null as [number, number, number, number] | null);
  const cmhc_metrics = safeJsonParse(properties.cmhc_metrics, undefined as MapFeature["properties"]["cmhc_metrics"]);

  return {
    id: Number(properties.id),
    geoid: String(properties.geoid),
    name: String(properties.name),
    type: String(properties.type),
    county: properties.county ? String(properties.county) : null,
    state: String(properties.state ?? "ON"),
    bbox: bbox as [number, number, number, number],
    geometry: feature.geometry as unknown as MapFeature["geometry"],
    geometry_source: properties.geometry_source != null ? String(properties.geometry_source) : "",
    metric: String(properties.metric) as MetricKey,
    value: properties.value === null ? null : Number(properties.value),
    metrics: metrics as MapFeature["properties"]["metrics"],
    cmhc_metrics: cmhc_metrics,
    cmhc_year: properties.cmhc_year != null ? Number(properties.cmhc_year) : undefined,
  };
}

// (formatLegendValue removed, the legend now renders quantile classes via formatMetric.)

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

function fitToCurrentGeography(
  map: MapLibreMap,
  data: MapData | null | undefined,
  selectedGeoid: string | undefined,
  animated: boolean
): boolean {
  if (!selectedGeoid) return fitToDataBounds(map, data, animated);

  const selectedFeature = data?.features.find(
    (feature) => feature.properties.geoid === selectedGeoid
  );
  const bbox = selectedFeature?.properties.bbox;
  if (!bbox || bbox.some((value) => !Number.isFinite(value))) return false;

  const [minLng, minLat, maxLng, maxLat] = bbox;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  map.fitBounds(
    [
      [minLng, minLat],
      [maxLng, maxLat]
    ],
    {
      padding: { top: 80, right: 80, bottom: 120, left: 80 },
      maxZoom: data?.metadata.geography_type === "census_tract" ? 11.35 : 9.15,
      duration: mapAnimationDuration(animated, reduceMotion, 650)
    }
  );
  return true;
}

function fitToDataBounds(
  map: MapLibreMap,
  data?: MapData | null,
  animated = true
): boolean {
  const bounds = getDataBounds(data);
  if (!bounds) {
    return false;
  }

  map.fitBounds(bounds, {
    padding: 40,
    maxZoom: 8.65,
    duration: mapAnimationDuration(
      animated,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      450
    )
  });
  return true;
}
