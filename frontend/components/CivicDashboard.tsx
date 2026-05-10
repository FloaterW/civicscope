"use client";

import { AlertCircle, Database, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getComparison,
  getMapData,
  getMetricLabel,
  getSummary,
  searchGeographies
} from "@/lib/api";
import type {
  CompareResponse,
  Geography,
  MapData,
  MapFeature,
  MetricKey,
  Summary
} from "@/types";

import { ComparisonPanel } from "./ComparisonPanel";
import { DetailPanel } from "./DetailPanel";
import { MetricSelector } from "./MetricSelector";
import { CivicMap } from "./CivicMap";
import { SummaryCards } from "./SummaryCards";

const defaultCompareIds = ["3520005", "3521005", "3521010", "3519036", "3519028"];

export function CivicDashboard() {
  const [metric, setMetric] = useState<MetricKey>("rent_burden_pct");
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [selected, setSelected] = useState<Geography | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<Geography[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mapLoading, setMapLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [comparisonLoading, setComparisonLoading] = useState(true);

  const selectedGeoid = selected?.geoid;

  const comparisonIds = useMemo(() => {
    if (!selectedGeoid) {
      return defaultCompareIds;
    }
    return [selectedGeoid, ...defaultCompareIds.filter((geoid) => geoid !== selectedGeoid)];
  }, [selectedGeoid]);

  useEffect(() => {
    const controller = new AbortController();
    setMapLoading(true);
    setError(null);

    getMapData("rent_burden_pct", controller.signal)
      .then((mapPayload) => {
        setMapData(mapPayload);
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setMapLoading(false);
        }
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setSummaryLoading(true);
    setError(null);

    getSummary(selectedGeoid, controller.signal)
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
  }, [selectedGeoid]);

  useEffect(() => {
    const controller = new AbortController();
    setComparisonLoading(true);
    setError(null);

    getComparison(comparisonIds, controller.signal)
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
  }, [comparisonIds]);

  const visibleMapData = useMemo(() => applyMetricToMapData(mapData, metric), [mapData, metric]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchGeographies(search, controller.signal)
        .then((payload) => setSearchResults(payload.items))
        .catch(() => setSearchResults([]));
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [search]);

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
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-80">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-civic-muted"
                aria-hidden="true"
              />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search municipality or ID"
                data-testid="geography-search"
                className="h-10 w-full rounded-md border border-civic-line bg-white pl-9 pr-3 text-sm outline-none ring-civic-teal focus:ring-2"
              />
              {searchResults.length > 0 && search.trim() && search !== selected?.name && (
                <div className="absolute right-0 z-20 mt-2 max-h-72 w-full overflow-auto rounded-md border border-civic-line bg-white shadow-panel">
                  {searchResults.slice(0, 8).map((geography) => (
                    <button
                      key={geography.geoid}
                      type="button"
                      onClick={() => {
                        setSelected(geography);
                        setSearch(geography.name);
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
            <MetricSelector value={metric} onChange={setMetric} />
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1.45fr)_430px] lg:px-6">
        <section
          data-testid="map-panel"
          className="min-h-[560px] overflow-hidden rounded-lg border border-civic-line bg-white shadow-panel"
        >
          <div className="flex items-center justify-between border-b border-civic-line px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-civic-ink">Map View</h2>
              <p className="text-xs text-civic-muted">{getMetricLabel(metric)} by municipality</p>
            </div>
            <div className="rounded-md border border-civic-line px-2 py-1 text-xs text-civic-muted">
              {visibleMapData?.metadata.year ?? "2021"}
            </div>
          </div>
          <div className="h-[520px]">
            <CivicMap
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

          <SummaryCards summary={summary} loading={summaryLoading && !summary} />
          <DetailPanel geography={selected} metric={metric} onClear={() => setSelected(null)} />
        </aside>

        <section className="rounded-lg border border-civic-line bg-white shadow-panel xl:col-span-2">
          <ComparisonPanel comparison={comparison} metric={metric} loading={comparisonLoading && !comparison} />
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
    .map((feature) => feature.properties.metrics[metric])
    .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));

  return {
    ...data,
    metadata: {
      ...data.metadata,
      metric,
      domain: {
        min: values.length ? Math.min(...values) : null,
        max: values.length ? Math.max(...values) : null
      }
    },
    features: data.features.map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        metric,
        value: feature.properties.metrics[metric] ?? null
      }
    }))
  };
}
