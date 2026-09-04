import type { FilterSpecification } from "maplibre-gl";

export type TransitFilters = {
  ttc_subway: boolean;
  ttc_other: boolean;
  go_transit: boolean;
  miway: boolean;
  durham_rt: boolean;
};

export const TRANSIT_LAYERS = [
  { key: "ttc_subway" as const, label: "TTC Subway", color: "#C23030" },
  { key: "ttc_other" as const, label: "TTC Bus / Streetcar", color: "#888888" },
  { key: "go_transit" as const, label: "GO Transit", color: "#5C8A4D" },
  { key: "miway" as const, label: "MiWay", color: "#8C7356" },
  { key: "durham_rt" as const, label: "Durham RT", color: "#7A6B8C" }
] as const;

const TRANSIT_CATEGORIES = new Set(TRANSIT_LAYERS.map((layer) => layer.key));

export type TransitRouteFeature = {
  type: "Feature";
  geometry: {
    type: "LineString" | "MultiLineString";
    coordinates: unknown[];
  };
  properties: {
    agency: string;
    route_name?: string;
    route_long_name?: string;
    route_type?: string;
    color: string;
    transit_category: (typeof TRANSIT_LAYERS)[number]["key"];
  };
};

export type TransitFeatureCollection = {
  type: "FeatureCollection";
  features: TransitRouteFeature[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isTransitFeatureCollection(value: unknown): value is TransitFeatureCollection {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) {
    return false;
  }
  if (value.features.length === 0) return false;

  return value.features.every((feature) => {
    if (!isRecord(feature) || feature.type !== "Feature") return false;
    const geometry = feature.geometry;
    const properties = feature.properties;
    if (
      !isRecord(geometry) ||
      (geometry.type !== "LineString" && geometry.type !== "MultiLineString") ||
      !Array.isArray(geometry.coordinates) ||
      geometry.coordinates.length === 0 ||
      !isRecord(properties)
    ) {
      return false;
    }
    return (
      typeof properties.agency === "string" &&
      properties.agency.trim().length > 0 &&
      typeof properties.color === "string" &&
      TRANSIT_CATEGORIES.has(String(properties.transit_category) as TransitRouteFeature["properties"]["transit_category"])
    );
  });
}

export function transitRouteLabels(routes: TransitFeatureCollection): string[] {
  const labels = routes.features.map(({ properties }) => {
    const routeNumber = properties.route_name?.trim();
    const routeName = properties.route_long_name?.trim();
    const route = [routeNumber ? `Route ${routeNumber}` : "", routeName ?? ""]
      .filter(Boolean)
      .join(" — ");
    return route ? `${properties.agency} — ${route}` : properties.agency;
  });
  return [...new Set(labels)].sort((a, b) => a.localeCompare(b, "en-CA"));
}

export const TRANSIT_FILTERS_OFF: TransitFilters = {
  ttc_subway: false,
  ttc_other: false,
  go_transit: false,
  miway: false,
  durham_rt: false
};

export const TRANSIT_FILTERS_ON: TransitFilters = {
  ttc_subway: true,
  ttc_other: true,
  go_transit: true,
  miway: true,
  durham_rt: true
};

export function anyTransitFilterEnabled(filters: TransitFilters): boolean {
  return Object.values(filters).some(Boolean);
}

export function allTransitFiltersEnabled(filters: TransitFilters): boolean {
  return Object.values(filters).every(Boolean);
}

export function buildTransitFilter(filters: TransitFilters): FilterSpecification | undefined {
  const active = Object.entries(filters)
    .filter(([, enabled]) => enabled)
    .map(([key]) => key);

  if (active.length === 0) return ["==", "transit_category", "__none__"];
  if (active.length === Object.keys(filters).length) return undefined;
  if (active.length === 1) return ["==", "transit_category", active[0]];
  return ["in", "transit_category", ...active] as unknown as FilterSpecification;
}
