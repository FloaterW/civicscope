"use client";

import { AlertCircle, ChevronUp, Database, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
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

import dynamic from "next/dynamic";

const ComparisonPanel = dynamic(
  () => import("./ComparisonPanel").then((m) => m.ComparisonPanel),
  { ssr: false }
);
const DetailPanel = dynamic(
  () => import("./DetailPanel").then((m) => m.DetailPanel),
  { ssr: false }
);

import { DataQualityBadge } from "./DataQualityBadge";
import { GeographyLevelSelector } from "./GeographyLevelSelector";
import { MetricSelector } from "./MetricSelector";
import { CivicMap } from "./CivicMap";
import { SummaryCards } from "./SummaryCards";
import { ThemeToggle } from "./ThemeToggle";
import { YearSelector } from "./YearSelector";

const defaultCompareIds = ["3520005", "3521005", "3521010", "3519036", "3519028"];

function mapCacheKey(level: GeographyLevel, metric: MetricKey, year?: number) {
  return `${level}:${metric}:${year ?? "latest"}`;
}

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
  const [mapDataByKey, setMapDataByKey] = useState<Record<string, MapData>>({});
  const [summary, setSummary] = useState<Summary | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [selected, setSelected] = useState<Geography | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<Geography[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [selectedCmhcMetrics, setSelectedCmhcMetrics] = useState<CmhcMetricValues | null>(null);
  const [selectedCmhcYear, setSelectedCmhcYear] = useState<number | undefined>(undefined);
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined);
  const [availableYears, setAvailableYears] = useState<number[]>([2021]);
  const [error, setError] = useState<string | null>(null);
  const [mapLoading, setMapLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [comparisonLoading, setComparisonLoading] = useState(true);
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false);
  const [searchHighlight, setSearchHighlight] = useState(-1);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const selectedGeoid = selected?.geoid;
  const geographyLabel = geographyLabels[geographyLevel];
  const isCmhc = isCmhcMetric(metric);
  const requestedMapYear = isCmhc ? selectedYear : undefined;
  const activeMapKey = mapCacheKey(geographyLevel, metric, requestedMapYear);
  const mapData = mapDataByKey[activeMapKey] ?? null;
  const hasCachedMapData = Boolean(mapData);
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

  function handleGeographyLevelChange(level: GeographyLevel) {
    if (level === geographyLevel) {
      return;
    }
    setGeographyLevel(level);
    setSelected(null);
    setSearch("");
    setSearchResults([]);
    setSelectedCmhcMetrics(null);
    setSelectedCmhcYear(undefined);
  }

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

    getMapData(metric, geographyLevel, controller.signal, requestedMapYear)
      .then((mapPayload) => {
        if (controller.signal.aborted) return;
        if (mapPayload.metadata.available_years?.length) {
          setAvailableYears(mapPayload.metadata.available_years);
        }
        if (mapPayload.metadata.cmhc_year !== undefined) {
          setSelectedCmhcYear(mapPayload.metadata.cmhc_year);
        }
        setMapDataByKey((current) =>
          current[activeMapKey]
            ? current
            : {
                ...current,
                [activeMapKey]: mapPayload
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
  }, [activeMapKey, geographyLevel, hasCachedMapData, metric, requestedMapYear]);

  useEffect(() => {
    if (!mapData) {
      return;
    }
    const inactiveLevel: GeographyLevel =
      geographyLevel === "municipality" ? "census_tract" : "municipality";
    const inactiveMapKey = mapCacheKey(inactiveLevel, metric, requestedMapYear);
    if (mapDataByKey[inactiveMapKey]) {
      return;
    }

    const controller = new AbortController();
    getMapData(metric, inactiveLevel, controller.signal, requestedMapYear)
      .then((mapPayload) => {
        if (controller.signal.aborted) return;
        setMapDataByKey((current) =>
          current[inactiveMapKey]
            ? current
            : {
                ...current,
                [inactiveMapKey]: mapPayload
              }
        );
      })
      .catch(() => {});

    return () => controller.abort();
  }, [geographyLevel, mapData, mapDataByKey, metric, requestedMapYear]);

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
      setSearchLoading(false);
      return;
    }
    const controller = new AbortController();
    setSearchLoading(true);
    const timer = window.setTimeout(() => {
      searchGeographies(search, geographyLevel, controller.signal)
        .then((payload) => {
          setSearchResults(payload.items);
          setSearchHighlight(-1);
          setSearchLoading(false);
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") {
            return;
          }
          setSearchResults([]);
          setSearchLoading(false);
        });
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
    setMobilePanelOpen(true);
  }

  const selectSearchResult = useCallback(
    (geography: Geography) => {
      setSelected(geography);
      setSearch(geography.name);
      setSearchHighlight(-1);
      const feature = mapData?.features.find(
        (f) => f.properties.geoid === geography.geoid
      );
      setSelectedCmhcMetrics(feature?.properties.cmhc_metrics ?? null);
      setSelectedCmhcYear(feature?.properties.cmhc_year);
      setMobilePanelOpen(true);
    },
    [mapData]
  );

  const visibleResults = searchResults.slice(0, 8);
  const searchOpen =
    visibleResults.length > 0 && Boolean(search.trim()) && search !== selected?.name;

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!searchOpen) return;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setSearchHighlight((i) => (i < visibleResults.length - 1 ? i + 1 : 0));
        break;
      case "ArrowUp":
        event.preventDefault();
        setSearchHighlight((i) => (i > 0 ? i - 1 : visibleResults.length - 1));
        break;
      case "Enter":
        event.preventDefault();
        if (searchHighlight >= 0 && searchHighlight < visibleResults.length) {
          selectSearchResult(visibleResults[searchHighlight]);
        }
        break;
      case "Escape":
        event.preventDefault();
        setSearch("");
        setSearchResults([]);
        setSearchHighlight(-1);
        searchInputRef.current?.blur();
        break;
    }
  }

  return (
    <main data-testid="dashboard-root" className="min-h-screen bg-civic-surface">
      <header className="border-b border-civic-line bg-civic-panel">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-civic-teal text-white dark:text-slate-900">
                <Database className="h-3.5 w-3.5" aria-hidden="true" />
              </div>
              <span className="text-xs font-semibold uppercase tracking-wider text-civic-teal">
                CivicScope
              </span>
            </div>
            <h1 className="text-xl font-semibold leading-tight text-civic-ink lg:text-2xl">
              Greater Toronto Housing Affordability Monitor
            </h1>
            <p className="text-xs text-civic-muted lg:text-sm">
              Rent burden, income, and CMHC housing data for 25 GTA municipalities and 1,334 census tracts.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            <div className="relative w-full sm:w-80">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-civic-muted"
                aria-hidden="true"
              />
              <input
                ref={searchInputRef}
                value={search}
                onChange={(event) => {
                  const next = event.target.value;
                  setSearch(next);
                  setSearchHighlight(-1);
                  if (next.trim()) {
                    setSearchLoading(true);
                  }
                }}
                onKeyDown={handleSearchKeyDown}
                placeholder={geographyLabel.search}
                data-testid="geography-search"
                role="combobox"
                aria-label="Search geographies"
                aria-expanded={searchOpen}
                aria-controls="geography-search-results"
                aria-autocomplete="list"
                aria-activedescendant={
                  searchOpen && searchHighlight >= 0
                    ? `search-option-${visibleResults[searchHighlight]?.geoid}`
                    : undefined
                }
                className="h-10 w-full rounded-md border border-civic-line bg-civic-panel pl-9 pr-3 text-sm text-civic-ink outline-none ring-civic-teal focus:ring-2"
              />
              {searchOpen && (
                <div id="geography-search-results" role="listbox" className="absolute right-0 z-20 mt-2 max-h-72 w-full overflow-auto rounded-md border border-civic-line bg-civic-panel shadow-panel">
                  {visibleResults.map((geography, index) => (
                    <button
                      key={geography.geoid}
                      id={`search-option-${geography.geoid}`}
                      type="button"
                      role="option"
                      aria-selected={index === searchHighlight}
                      onClick={() => selectSearchResult(geography)}
                      onMouseEnter={() => setSearchHighlight(index)}
                      className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm transition ${
                        index === searchHighlight
                          ? "bg-civic-teal/10 dark:bg-civic-teal/20"
                          : "hover:bg-civic-subtle"
                      }`}
                    >
                      <span className="font-medium text-civic-ink">{geography.name}</span>
                      <span className="text-xs text-civic-muted">{geography.geoid}</span>
                    </button>
                  ))}
                </div>
              )}
              {searchResults.length === 0 && search.trim() && search !== selected?.name && (
                <div
                  data-testid="search-empty"
                  role="status"
                  className="pointer-events-none absolute right-0 z-20 mt-2 w-full rounded-md border border-civic-line bg-civic-panel px-3 py-2 text-sm text-civic-muted shadow-panel"
                >
                  {searchLoading
                    ? "Searching…"
                    : `No ${geographyLabel.plural} match "${search.trim()}".`}
                </div>
              )}
              <div className="sr-only" aria-live="polite" aria-atomic="true">
                {searchOpen
                  ? `${visibleResults.length} result${visibleResults.length === 1 ? "" : "s"} available. Use arrow keys to navigate.`
                  : ""}
              </div>
            </div>
            <GeographyLevelSelector value={geographyLevel} onChange={handleGeographyLevelChange} />
            <MetricSelector value={metric} onChange={setMetric} />
            <YearSelector
              value={displayYear}
              availableYears={isCmhc ? availableYears : [2021]}
              disabled={!isCmhc}
              onChange={(year) => setSelectedYear(year)}
            />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1.45fr)_430px] lg:px-6">
        <section
          data-testid="map-panel"
          className="flex min-h-[400px] flex-col overflow-hidden rounded-lg border border-civic-line bg-civic-panel shadow-panel xl:min-h-[560px]"
        >
          <div className="flex flex-col gap-2 border-b border-civic-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-civic-ink">Map View</h2>
              <p className="text-xs text-civic-muted">
                {getMetricLabel(metric)} by {geographyLabel.singular}
              </p>
              {geographyLevel === "census_tract" &&
                visibleMapData?.metadata.data_quality?.metric_status === "zone" && (
                  <p className="mt-1 max-w-prose text-xs leading-5 text-teal-700 dark:text-teal-400">
                    Each tract shows its CMHC survey zone&apos;s value. Zones are sub-city areas
                    surveyed by CMHC, so tracts in the same zone share the same value.
                  </p>
                )}
              {geographyLevel === "census_tract" &&
                visibleMapData?.metadata.data_quality?.label?.includes("inherited") && (
                  <p className="mt-1 max-w-prose text-xs leading-5 text-amber-700 dark:text-amber-400">
                    Showing each tract&apos;s municipal average. CMHC does not publish this
                    metric at the survey-zone level.
                  </p>
                )}
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
          <div className="min-h-[360px] flex-1 xl:min-h-[520px]">
            <CivicMap
              key={geographyLevel}
              data={visibleMapData}
              loading={mapLoading}
              metric={metric}
              geographyLevel={geographyLevel}
              selectedGeoid={selectedGeoid}
              onSelect={handleFeatureSelect}
            />
          </div>
        </section>

        {/* Mobile: slide-up panel toggle */}
        <button
          type="button"
          onClick={() => setMobilePanelOpen(!mobilePanelOpen)}
          className="flex items-center justify-center gap-2 rounded-lg border border-civic-line bg-civic-panel py-3 text-sm font-medium text-civic-ink shadow-panel transition xl:hidden"
        >
          <ChevronUp className={`h-4 w-4 transition-transform ${mobilePanelOpen ? "rotate-180" : ""}`} />
          {selected ? selected.name : "Summary & Details"}
        </button>

        <aside className={`flex flex-col gap-4 transition-all duration-300 xl:opacity-100 xl:max-h-none ${mobilePanelOpen ? "max-h-[5000px] opacity-100" : "max-h-0 overflow-hidden opacity-0 xl:max-h-none xl:overflow-visible"}`}>
          {error && (
            <div className="animate-fade-in rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
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

        <section className="rounded-lg border border-civic-line bg-civic-panel shadow-panel xl:col-span-2">
          <ComparisonPanel
            comparison={comparison}
            metric={metric}
            geographyLevel={geographyLevel}
            loading={comparisonLoading && !comparison}
            displayYear={isCmhc ? displayYear : undefined}
          />
        </section>
      </div>

      <footer className="border-t border-civic-line bg-civic-panel">
        <div className="mx-auto max-w-[1600px] space-y-1 px-4 py-4 text-xs text-civic-muted lg:px-6">
          <p>
            Boundaries &amp; census metrics: Statistics Canada 2021 Census (cartographic boundary
            files, Census Profile).
          </p>
          <p>
            Rental &amp; housing-supply metrics: CMHC Housing Market Information Portal (Rental
            Market Survey, Starts &amp; Completions Survey).
          </p>
          <p>
            Census-tract CMHC values are inherited/allocated from the parent municipality and
            labeled as estimated.
          </p>
        </div>
      </footer>
    </main>
  );
}

function applyMetricToMapData(data: MapData | null, metric: MetricKey): MapData | null {
  if (!data) {
    return null;
  }

  const values = data.features
    .map((feature) => {
      if (
        metric === "population_growth_pct" &&
        feature.properties.metrics.data_quality?.population_growth_pct === "low_confidence"
      ) {
        return null;
      }
      const allMetrics = { ...feature.properties.metrics, ...feature.properties.cmhc_metrics } as Record<string, unknown>;
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
      const allMetrics = { ...feature.properties.metrics, ...feature.properties.cmhc_metrics } as Record<string, unknown>;
      const rawValue = allMetrics[metric];
      return {
        ...feature,
        properties: {
          ...feature.properties,
          metric,
          value: typeof rawValue === "number" ? rawValue : null
        }
      };
    })
  };
}
