"use client";

import type { FilterSpecification, LngLatBoundsLike, Map as MapLibreMap, Popup } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatMetric, getMetricLabel, getTransitRoutes } from "@/lib/api";
import { FLAT_COLOR, NULL_COLOR, rampColorAt } from "@/lib/colors";
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

type ThemeName = keyof typeof BASEMAP_STYLES;

function currentTheme(): ThemeName {
  return isDarkMode() ? "dark" : "light";
}

type TransitFilters = {
  ttc_subway: boolean;
  ttc_other: boolean;
  go_transit: boolean;
  miway: boolean;
  durham_rt: boolean;
};

const TRANSIT_LAYERS = [
  { key: "ttc_subway" as const, label: "TTC Subway", color: "#C23030", indent: true },
  { key: "ttc_other" as const, label: "TTC Bus / Streetcar", color: "#888888", indent: true },
  { key: "go_transit" as const, label: "GO Transit", color: "#5C8A4D" },
  { key: "miway" as const, label: "MiWay", color: "#8C7356" },
  { key: "durham_rt" as const, label: "Durham RT", color: "#7A6B8C" },
] as const;

const ALL_OFF: TransitFilters = { ttc_subway: false, ttc_other: false, go_transit: false, miway: false, durham_rt: false };
const ALL_ON: TransitFilters = { ttc_subway: true, ttc_other: true, go_transit: true, miway: true, durham_rt: true };

function buildTransitFilter(filters: TransitFilters): FilterSpecification | undefined {
  const active = Object.entries(filters).filter(([, v]) => v).map(([k]) => k);
  if (active.length === 0) return ["==", "transit_category", "__none__"];
  if (active.length === Object.keys(filters).length) return undefined;
  if (active.length === 1) return ["==", "transit_category", active[0]];
  return ["in", "transit_category", ...active] as unknown as FilterSpecification;
}

function applyTransitFilterState(map: MapLibreMap, filters: TransitFilters) {
  if (!map.getLayer(transitLineLayerId)) return;
  const anyEnabled = Object.values(filters).some(Boolean);
  map.setLayoutProperty(transitLineLayerId, "visibility", anyEnabled ? "visible" : "none");
  map.setFilter(transitLineLayerId, buildTransitFilter(filters) ?? null);
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

  const firstSymbolLayer = map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
  if (!map.getLayer(fillLayerId)) {
    map.addLayer(
      {
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": colorExpression(data),
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
  const [transitOpen, setTransitOpen] = useState(false);
  const [transitFilters, setTransitFilters] = useState<TransitFilters>({ ...ALL_OFF });
  const onSelectRef = useRef(onSelect);
  const popupRef = useRef<Popup | null>(null);
  const latestDataRef = useRef<MapData | null>(data);
  const selectedGeoidRef = useRef(selectedGeoid);
  const transitFiltersRef = useRef<TransitFilters>(transitFilters);
  const transitRoutesRef = useRef<unknown>(null);
  const themeRef = useRef<ThemeName>(currentTheme());
  // The hover handler is registered once at init; read the live metric from a
  // ref so the tooltip always reflects the currently selected metric.
  const metricRef = useRef<MetricKey>(metric);
  const isReady = Boolean(data);
  const loadedMetric = data?.metadata.metric ?? null;

  // Same quantile computation the map paints by, so the legend always agrees.
  const legend = useMemo(() => (data ? computeColorStops(data) : null), [data]);
  // Data loaded, but every geography is null for this metric (e.g. turnover /
  // availability, not collected in this dataset). Surface an explicit empty
  // state instead of a silently blank map.
  const dataIsEmpty = Boolean(
    data && data.metadata.domain.min === null && data.metadata.domain.max === null
  );

  const anyTransitOn = Object.values(transitFilters).some(Boolean);

  useEffect(() => {
    transitFiltersRef.current = transitFilters;
    const map = mapRef.current;
    if (!map || !mapReadyRef.current || !map.getLayer(transitLineLayerId)) return;
    applyTransitFilterState(map, transitFilters);
  }, [transitFilters, anyTransitOn]);

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
        applyTransitFilterState(map, transitFiltersRef.current);
        mapReadyRef.current = true;
      };
      map.on("style.load", handleStyleLoad);

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
        fitToDataBounds(map, initialData, false);
        getTransitRoutes()
          .then((geojson) => {
            transitRoutesRef.current = geojson;
            const src = map.getSource(transitSourceId);
            if (src && "setData" in src) {
              (src as { setData: (d: never) => void }).setData(geojson as never);
            }
          })
          .catch(() => {});
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
      map.setPaintProperty(fillLayerId, "fill-color", colorExpression(data));
    }
  }, [data, metric]);

  useEffect(() => {
    selectedGeoidRef.current = selectedGeoid;
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
          padding: { top: 80, right: 80, bottom: 120, left: 80 },
          maxZoom: data?.metadata.geography_type === "census_tract" ? 11.35 : 9.15,
          duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650
        }
      );
    }
  }, [data, selectedGeoid]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const map = mapRef.current;
      if (!map) return;
      const theme = currentTheme();
      if (themeRef.current === theme) return;
      themeRef.current = theme;
      mapReadyRef.current = false;
      popupRef.current?.remove();
      map.setStyle(BASEMAP_STYLES[theme]);
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
      data-empty={dataIsEmpty ? "true" : "false"}
      role="region"
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
                className="mt-3 rounded-md border border-civic-line px-3 py-1.5 text-xs font-semibold text-civic-ink hover:bg-civic-subtle"
              >
                Retry map
              </button>
            )}
          </div>
        </div>
      )}
      {data && loading && loadedMetric !== metric && (
        <div className="absolute right-3 top-3 z-10 animate-fade-in rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs font-medium text-civic-ink shadow-panel backdrop-blur-sm">
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
      <div ref={containerRef} data-testid="map-canvas-host" className="h-full w-full" />
      {data && legend && (
        <div
          data-testid="map-legend"
          className="absolute bottom-3 left-3 max-w-[230px] rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs shadow-panel backdrop-blur-sm"
        >
          <div className="mb-1.5 font-semibold text-civic-ink">{getMetricLabel(metric)}</div>
          {legend.flat || legend.stops.length < 2 ? (
            <div data-legend-class className="flex items-center gap-2 text-civic-muted">
              <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: FLAT_COLOR }} />
              <span className="tabular-nums">{formatMetric(metric, legend.min)}</span>
            </div>
          ) : (
            <ul className="space-y-1">
              {legend.stops.map((stop, index) => {
                const isLast = index === legend.stops.length - 1;
                const upper = isLast ? legend.max : legend.stops[index + 1].value;
                return (
                  <li
                    key={`${stop.value}-${index}`}
                    data-legend-class
                    className="flex items-center gap-2 text-civic-muted"
                  >
                    <span
                      className="h-3 w-3 shrink-0 rounded-sm"
                      style={{ backgroundColor: stop.color }}
                    />
                    <span className="tabular-nums">
                      {isLast
                        ? `${formatMetric(metric, stop.value)}+`
                        : `${formatMetric(metric, stop.value)} – ${formatMetric(metric, upper)}`}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
      {data && (
        <div className="absolute bottom-9 right-3 z-10 flex flex-col items-end gap-1.5">
          {transitOpen && (
            <div className="animate-fade-in rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-xs shadow-panel backdrop-blur-sm">
              <div className="mb-2 flex items-center justify-between gap-4">
                <span className="font-semibold text-civic-ink">Transit Lines</span>
                <button
                  type="button"
                  className="text-[10px] text-civic-muted hover:text-civic-ink"
                  onClick={() => {
                    const allOn = Object.values(transitFilters).every(Boolean);
                    setTransitFilters({ ...(allOn ? ALL_OFF : ALL_ON) });
                  }}
                >
                  {Object.values(transitFilters).every(Boolean) ? "Clear all" : "Select all"}
                </button>
              </div>
              <fieldset className="space-y-1.5">
                <legend className="sr-only">Transit line filters</legend>
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-civic-muted">TTC</div>
                {TRANSIT_LAYERS.filter((l) => l.key.startsWith("ttc")).map((layer) => (
                  <label key={layer.key} className="flex cursor-pointer items-center gap-2 text-civic-muted hover:text-civic-ink">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={transitFilters[layer.key]}
                      onChange={() => setTransitFilters((prev) => ({ ...prev, [layer.key]: !prev[layer.key] }))}
                    />
                    <span
                      className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border border-civic-line peer-checked:border-transparent peer-checked:text-white"
                      style={transitFilters[layer.key] ? { backgroundColor: layer.color } : undefined}
                    >
                      {transitFilters[layer.key] && (
                        <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth={2}><path d="M2.5 6l2.5 2.5 4.5-5" /></svg>
                      )}
                    </span>
                    <span className="h-0.5 w-3 shrink-0 rounded-full" style={{ backgroundColor: layer.color }} />
                    {layer.label.replace("TTC ", "")}
                  </label>
                ))}
                <div className="mb-1 mt-2.5 text-[10px] font-medium uppercase tracking-wider text-civic-muted">Regional</div>
                {TRANSIT_LAYERS.filter((l) => !l.key.startsWith("ttc")).map((layer) => (
                  <label key={layer.key} className="flex cursor-pointer items-center gap-2 text-civic-muted hover:text-civic-ink">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={transitFilters[layer.key]}
                      onChange={() => setTransitFilters((prev) => ({ ...prev, [layer.key]: !prev[layer.key] }))}
                    />
                    <span
                      className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border border-civic-line peer-checked:border-transparent peer-checked:text-white"
                      style={transitFilters[layer.key] ? { backgroundColor: layer.color } : undefined}
                    >
                      {transitFilters[layer.key] && (
                        <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth={2}><path d="M2.5 6l2.5 2.5 4.5-5" /></svg>
                      )}
                    </span>
                    <span className="h-0.5 w-3 shrink-0 rounded-full" style={{ backgroundColor: layer.color }} />
                    {layer.label}
                  </label>
                ))}
              </fieldset>
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              if (!transitOpen) {
                setTransitOpen(true);
                if (!anyTransitOn) setTransitFilters({ ...ALL_ON });
              } else {
                setTransitOpen(false);
                setTransitFilters({ ...ALL_OFF });
              }
            }}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-panel transition-colors ${
              anyTransitOn
                ? "border-civic-teal bg-civic-teal text-white"
                : "border-civic-line bg-civic-panel text-civic-muted hover:text-civic-ink"
            }`}
            aria-pressed={anyTransitOn}
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

// Color ramp shared with the comparison chart (see lib/colors).

/**
 * Compute quantile boundaries from a sorted ascending array of values.
 * Returns `count` interior break points at evenly-spaced percentiles
 * (e.g. count=4 -> 20/40/60/80 for 5 classes). Uses linear interpolation
 * between sorted samples.
 */
function quantileBreaks(sorted: number[], count: number): number[] {
  const breaks: number[] = [];
  for (let i = 1; i <= count; i += 1) {
    const q = i / (count + 1);
    const pos = q * (sorted.length - 1);
    const lower = Math.floor(pos);
    const upper = Math.min(sorted.length - 1, lower + 1);
    const frac = pos - lower;
    breaks.push(sorted[lower] + (sorted[upper] - sorted[lower]) * frac);
  }
  return breaks;
}

/**
 * Quantile (data-driven) colour stops computed from the actual distribution of
 * the active metric's non-null feature values. This differentiates right-skewed
 * metrics far better than linear min/mid/max interpolation, which washes most
 * areas into the palest band. Returns the stop boundaries (ascending, deduped)
 * paired with the ramp colour for each, plus the domain min/max, shared by the
 * map paint expression and the legend so the two always agree.
 */
function computeColorStops(data: MapData): {
  stops: Array<{ value: number; color: string }>;
  min: number;
  max: number;
  flat: boolean;
} {
  const values = data.features
    .map((feature) => feature.properties.value)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((a, b) => a - b);

  const min = values.length ? values[0] : (data.metadata.domain.min ?? 0);
  const max = values.length ? values[values.length - 1] : (data.metadata.domain.max ?? 1);

  // All equal (or no data): flat fill, interpolate needs ascending stops.
  if (!values.length || min === max) {
    return { stops: [], min, max, flat: true };
  }

  // 5 classes -> 4 interior quantile breaks at the 20/40/60/80 percentiles.
  // Anchor with the domain min so the first stop maps to the palest colour.
  const interior = quantileBreaks(values, 4);
  const candidate = [min, ...interior];

  // Dedupe equal boundaries (heavily-tied distributions collapse quantiles)
  // to keep stops strictly ascending, MapLibre throws otherwise.
  const ascending: number[] = [];
  for (const value of candidate) {
    if (ascending.length === 0 || value > ascending[ascending.length - 1]) {
      ascending.push(value);
    }
  }

  // Need >=2 distinct stops to interpolate; otherwise fall back to flat.
  if (ascending.length < 2) {
    return { stops: [], min, max, flat: true };
  }

  const stops = ascending.map((value, index) => ({
    value,
    color: rampColorAt(index / (ascending.length - 1), data.metadata.metric)
  }));
  return { stops, min, max, flat: false };
}

function colorExpression(data: MapData): unknown[] {
  const { stops, flat } = computeColorStops(data);

  // When all features have the same value (e.g. CMA-level CMHC data),
  // min === max makes interpolate stops non-monotonic which silently
  // kills MapLibre rendering. Use a flat color instead.
  if (flat) {
    return ["case", ["==", ["get", "value"], null], NULL_COLOR, FLAT_COLOR];
  }

  const interpolateStops = stops.flatMap((stop) => [stop.value, stop.color]);
  return [
    "case",
    ["==", ["get", "value"], null],
    NULL_COLOR,
    ["interpolate", ["linear"], ["to-number", ["get", "value"]], ...interpolateStops]
  ];
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
