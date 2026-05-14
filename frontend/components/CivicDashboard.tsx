"use client";

import { AlertCircle, Database, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  CMHC_METRIC_KEYS,
  getComparison,
  getMapData,
  getMetricLabel,
  getSummary,
  isCmhcMetric,
  searchGeographies
} from "@/lib/api";
import type {
  CmhcMetricValues,
  CompareResponse,
  GeographyLevel,
  Geography,
  MapData,
  MapFeature,
  MetricKey,
  Summary
} from "@/types";

import { ComparisonPanel } from "./ComparisonPanel";
import { DataQualityBadge } from "./DataQualityBadge";
import { DetailPanel } from "./DetailPanel";
import { GeographyLevelSelector } from "./GeographyLevelSelector";
import { MetricSelector } from "./MetricSelector";
import { CivicMap } from "./CivicMap";
import { SummaryCards } from "./SummaryCards";
import { YearSelector } from "./YearSelector";

const defaultCompareIds = ["3520005", "3521005", "3521010", "3519036", "3519028"];

const geographyLabels: Record<GeographyLevel, { singular: string; plural: string; search: string }> = {
  municipality: {
    singular: "municipality",
    plural: "municipalities",
    search: "Search municipality or ID"
  },
  census_tract: {
    singular: "census tract",
    plural: "census tracts",
    search: "Search tract, municipality, or ID"
  }
};

export function CivicDashboard() {
  const [metric, setMetric] = useState<MetricKey>("rent_burden_pct");
  const [geographyLevel, setGeographyLevel] = useState<GeographyLevel>("municipality");
  const [mapDataByLevel, setMapDataByLevel] = useState<Partial<Record<GeographyLevel, MapData>>>({});
  const [summary, setSummary] = useState<Summary | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [selected, setSelected] = useState<Geography | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<Geography[]>([]);
  const [selectedCmhcMetrics, setSelectedCmhcMetrics] = useState<CmhcMetricValues | null>(null);
  const [selectedCmhcYear, setSelectedCmhcYear] = useState<number | undefined>(undefined);
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined);
  const [availableYears, setAvailableYears] = useState<number[]>([2021]);
  const [error, setError] = useState<string | null>(null);
  const [mapLoading, setMapLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [comparisonLoading, setComparisonLoading] = useState(true);
  const selectedGeoid = selected?.geoid;
  const geographyLabel = geographyLabels[geographyLevel];
  const mapData = mapDataByLevel[geographyLevel] ?? null;
  const hasCachedMapData = Boolean(mapData);
  const isCmhc = isCmhcMetric(metric);
  const displayYear = isCmhc ? (selectedYear ?? availableYears[availableYears.length - 1]) : 2021;

  const comparisonIds = useMemo(() => {
    if (geographyLevel === "census_tract") {
      return selectedGeoid ? [selectedGeoid] : [];
    }
    if (!selectedGeoid) {
      return defaultCompareIds;
    }
    return [selectedGeoid, ...defaultCompareIds.filter((geoid) => geoid !== selectedGeoid)];
  }, [geographyLevel, selectedGeoid]);

  useEffect(() => {
    setSelected(null);
    setSearch("");
    setSearchResults([]);
  }, [geographyLevel]);

  useEffect(() => {
    // Clear all cached map data and cancel in-flight prefetches so stale
    // responses from the previous metric don't re-pollute the cache.
    setMapDataByLevel({});
  }, [metric, selectedYear]);

  // Keep selected geography's CMHC data in sync with current map data.
  // Handles: search selection, metric switch, year switch — all paths
  // that change mapData while a geography is selected.
  useEffect(() => {
    if (!selected || !mapData) {
      return;
    }
    const feature = mapData.features.find(
      (f) => f.properties.geoid === selected.geoid
    );
    setSelectedCmhcMetrics(feature?.properties.cmhc_metrics ?? null);
    setSelectedCmhcYear(feature?.properties.cmhc_year);
  }, [selected, mapData]);

  useEffect(() => {
    if (hasCachedMapData) {
      setMapLoading(false);
      return;
    }
    setMapLoading(true);
    setError(null);
    const controller = new AbortController();

    getMapData(metric, geographyLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((mapPayload) => {
        if (controller.signal.aborted) return;
        if (mapPayload.metadata.available_years?.length) {
          setAvailableYears(mapPayload.metadata.available_years);
        }
        if (mapPayload.metadata.cmhc_year !== undefined) {
          setSelectedCmhcYear(mapPayload.metadata.cmhc_year);
        }
        setMapDataByLevel((current) =>
          current[geographyLevel]
            ? current
            : {
                ...current,
                [geographyLevel]: mapPayload
              }
        );
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) return;
        setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setMapLoading(false);
        }
      });

    return () => controller.abort();
  }, [geographyLevel, hasCachedMapData, metric, selectedYear, isCmhc]);

  useEffect(() => {
    if (!mapData) {
      return;
    }
    const inactiveLevel: GeographyLevel =
      geographyLevel === "municipality" ? "census_tract" : "municipality";
    if (mapDataByLevel[inactiveLevel]) {
      return;
    }

    const controller = new AbortController();
    getMapData(metric, inactiveLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((mapPayload) => {
        if (controller.signal.aborted) return;
        setMapDataByLevel((current) =>
          current[inactiveLevel]
            ? current
            : {
                ...current,
                [inactiveLevel]: mapPayload
              }
        );
      })
      .catch(() => {});

    return () => controller.abort();
  }, [geographyLevel, mapData, mapDataByLevel, metric, selectedYear, isCmhc]);

  useEffect(() => {
    const controller = new AbortController();
    setSummaryLoading(true);
    setError(null);

    getSummary(selectedGeoid, geographyLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((summaryPayload) => setSummary(summaryPayload))
      .catch((requestError: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSummaryLoading(false);
        }
      });

    return () => controller.abort();
  }, [geographyLevel, selectedGeoid, selectedYear, isCmhc]);

  useEffect(() => {
    const controller = new AbortController();
    setComparisonLoading(true);
    setError(null);

    getComparison(comparisonIds, geographyLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((comparisonPayload) => setComparison(comparisonPayload))
      .catch((requestError: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setComparisonLoading(false);
        }
      });

    return () => controller.abort();
  }, [comparisonIds, geographyLevel, selectedYear, isCmhc]);

  const visibleMapData = useMemo(() => applyMetricToMapData(mapData, metric), [mapData, metric]);

  useEffect(() => {
    if (!search.trim()) {
      setSearchResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchGeographies(search, geographyLevel, controller.signal)
        .then((payload) => setSearchResults(payload.items))
        .catch(() => setSearchResults([]));
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [geographyLevel, search]);

  function handleFeatureSelect(feature: MapFeature["properties"]) {
    setSelected({
      id: feature.id,
      geoid: feature.geoid,
      name: feature.name,
      type: feature.type,
      county: feature.county,
      state: feature.state,
      bbox: feature.bbox,
      geometry: feature.geometry,
      geometry_source: feature.geometry_source,
      metrics: feature.metrics
    });
    setSelectedCmhcMetrics(feature.cmhc_metrics ?? null);
    setSelectedCmhcYear(feature.cmhc_year);
  }

  return (
    <main data-testid="dashboard-root" className="min-h-screen bg-civic-surface">
      <header className="border-b border-civic-line bg-white">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-civic-teal">
              <Database className="h-4 w-4" aria-hidden="true" />
              CivicScope
            </div>
            <h1 className="mt-1 text-2xl font-semibold text-civic-ink">
              Greater Toronto Housing Affordability Monitor
            </h1>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            <div className="relative w-full sm:w-80">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-civic-muted"
                aria-hidden="true"
              />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={geographyLabel.search}
                data-testid="geography-search"
                role="combobox"
                aria-label="Search geographies"
                aria-expanded={searchResults.length > 0 && Boolean(search.trim()) && search !== selected?.name}
                aria-controls="geography-search-results"
                aria-autocomplete="list"
                className="h-10 w-full rounded-md border border-civic-line bg-white pl-9 pr-3 text-sm outline-none ring-civic-teal focus:ring-2"
              />
              {searchResults.length > 0 && search.trim() && search !== selected?.name && (
                <div id="geography-search-results" role="listbox" className="absolute right-0 z-20 mt-2 max-h-72 w-full overflow-auto rounded-md border border-civic-line bg-white shadow-panel">
                  {searchResults.slice(0, 8).map((geography) => (
                    <button
                      key={geography.geoid}
                      type="button"
                      role="option"
                      aria-selected={selected?.geoid === geography.geoid}
                      onClick={() => {
                        setSelected(geography);
                        setSearch(geography.name);
                        // Propagate CMHC metrics from current map data so
                        // the detail panel displays them (same as map-click path).
                        const feature = mapData?.features.find(
                          (f) => f.properties.geoid === geography.geoid
                        );
                        setSelectedCmhcMetrics(feature?.properties.cmhc_metrics ?? null);
                        setSelectedCmhcYear(feature?.properties.cmhc_year);
                      }}
                      className="flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm hover:bg-slate-50"
                    >
                      <span className="font-medium text-civic-ink">{geography.name}</span>
                      <span className="text-xs text-civic-muted">{geography.geoid}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <GeographyLevelSelector value={geographyLevel} onChange={setGeographyLevel} />
            <MetricSelector value={metric} onChange={setMetric} />
            <YearSelector
              value={displayYear}
              availableYears={isCmhc ? availableYears : [2021]}
              disabled={!isCmhc}
              onChange={(year) => setSelectedYear(year)}
            />
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1.45fr)_430px] lg:px-6">
        <section
          data-testid="map-panel"
          className="flex min-h-[560px] flex-col overflow-hidden rounded-lg border border-civic-line bg-white shadow-panel"
        >
          <div className="flex flex-col gap-2 border-b border-civic-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-civic-ink">Map View</h2>
              <p className="text-xs text-civic-muted">
                {getMetricLabel(metric)} by {geographyLabel.singular}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <DataQualityBadge
                geographyLevel={geographyLevel}
                dataQualityLabel={visibleMapData?.metadata.data_quality?.label}
                metricStatus={visibleMapData?.metadata.data_quality?.metric_status}
              />
              <div className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
                {visibleMapData?.metadata.year ?? "2021"}
              </div>
            </div>
          </div>
          <div className="min-h-[520px] flex-1">
            <CivicMap
              key={geographyLevel}
              data={visibleMapData}
              loading={mapLoading}
              metric={metric}
              selectedGeoid={selectedGeoid}
              onSelect={handleFeatureSelect}
            />
          </div>
        </section>

        <aside className="flex flex-col gap-4">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              <div className="flex items-center gap-2 font-semibold">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                API error
              </div>
              <p className="mt-1 text-xs">{error}</p>
            </div>
          )}

          <SummaryCards
            summary={summary}
            geographyLevel={geographyLevel}
            loading={summaryLoading && !summary}
          />
          <DetailPanel
            geography={selected}
            metric={metric}
            geographyLevel={geographyLevel}
            cmhcMetrics={selectedCmhcMetrics}
            cmhcYear={selectedCmhcYear}
            dataQualityLabel={visibleMapData?.metadata.data_quality?.label}
            metricStatus={visibleMapData?.metadata.data_quality?.metric_status}
            onClear={() => {
              setSelected(null);
              setSelectedCmhcMetrics(null);
              setSelectedCmhcYear(undefined);
            }}
          />
        </aside>

        <section className="rounded-lg border border-civic-line bg-white shadow-panel xl:col-span-2">
          <ComparisonPanel
            comparison={comparison}
            metric={metric}
            geographyLevel={geographyLevel}
            loading={comparisonLoading && !comparison}
            displayYear={isCmhc ? displayYear : undefined}
          />
        </section>
      </div>
    </main>
  );
}

function applyMetricToMapData(data: MapData | null, metric: MetricKey): MapData | null {
  if (!data) {
    return null;
  }

  const values = data.features
    .map((feature) => {
      const allMetrics = { ...feature.properties.metrics, ...feature.properties.cmhc_metrics } as Record<string, number | boolean | null>;
      return allMetrics[metric];
    })
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));

  return {
    ...data,
    metadata: {
      ...data.metadata,
      metric,
      domain: {
        min: values.length ? values.reduce((a, b) => Math.min(a, b), Infinity) : null,
        max: values.length ? values.reduce((a, b) => Math.max(a, b), -Infinity) : null
      }
    },
    features: data.features.map((feature) => {
      const allMetrics = { ...feature.properties.metrics, ...feature.properties.cmhc_metrics } as Record<string, number | boolean | null>;
      return {
        ...feature,
        properties: {
          ...feature.properties,
          metric,
          value: typeof allMetrics[metric] === "number" ? allMetrics[metric] : null
        }
      };
    })
  };
}
