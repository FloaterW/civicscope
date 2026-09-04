"use client";

import { AlertCircle, ChevronDown, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getComparison,
  getMapData,
  getMetricLabel,
  getSummary,
  isCmhcMetric,
  mapDataCacheKey,
  searchGeographies
} from "@/lib/api";
import {
  buildDashboardUrl,
  DEFAULT_DASHBOARD_LEVEL,
  DEFAULT_DASHBOARD_METRIC,
  parseDashboardUrl
} from "@/lib/dashboard-url";
import { isTransitMetric } from "@/lib/transit";
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

import { BrandMark } from "./BrandMark";

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
import { TransitCoverageNotice } from "./TransitCoverageNotice";
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

type RequestState<T> = {
  key: string;
  data: T | null;
  error: string | null;
};

type UrlHistoryMode = "push" | "replace";

function isPlausibleDataYear(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 1900 && Number(value) <= 2100;
}

function firstPlausibleDataYear(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (isPlausibleDataYear(value)) {
      return value;
    }
  }
  return undefined;
}

function joinAnnouncements(current: string, next: string): string {
  return current ? `${current} ${next}` : next;
}

function commitDashboardUrl(
  state: {
    level: GeographyLevel;
    metric: MetricKey;
    year?: number;
    geoid?: string;
  },
  mode: UrlHistoryMode
) {
  if (typeof window === "undefined") {
    return;
  }

  const nextUrl = buildDashboardUrl(window.location.href, state);
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextUrl === currentUrl) {
    return;
  }

  const historyState = { ...window.history.state, civicScopeDashboard: true };
  if (mode === "push") {
    window.history.pushState(historyState, "", nextUrl);
  } else {
    window.history.replaceState(historyState, "", nextUrl);
  }
}

export function CivicDashboard() {
  const [metric, setMetric] = useState<MetricKey>(DEFAULT_DASHBOARD_METRIC);
  const [geographyLevel, setGeographyLevel] = useState<GeographyLevel>(
    DEFAULT_DASHBOARD_LEVEL
  );
  const [mapDataByKey, setMapDataByKey] = useState<Record<string, MapData>>({});
  const [summaryState, setSummaryState] = useState<RequestState<Summary> | null>(null);
  const [comparisonState, setComparisonState] = useState<RequestState<CompareResponse> | null>(null);
  const [selected, setSelected] = useState<Geography | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<Geography[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined);
  const [availableYears, setAvailableYears] = useState<number[]>([2021]);
  const [mapFailure, setMapFailure] = useState<{ key: string; error: string } | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(false);
  const [searchHighlight, setSearchHighlight] = useState(-1);
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [slowConnectionKey, setSlowConnectionKey] = useState<string | null>(null);
  const [contextAnnouncement, setContextAnnouncement] = useState("");
  const [urlStateReady, setUrlStateReady] = useState(false);
  const [pendingUrlYear, setPendingUrlYear] = useState<number | null>(null);
  const [pendingUrlGeoid, setPendingUrlGeoid] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const searchRequestRef = useRef(0);
  const availableYearsRef = useRef<number[]>([2021]);
  const cmhcYearsResolvedRef = useRef(false);
  const selectedGeoid = selected?.geoid;
  const geographyLabel = geographyLabels[geographyLevel];
  const isCmhc = isCmhcMetric(metric);
  const isTransit = isTransitMetric(metric);
  const requestedMapYear = isCmhc ? selectedYear : undefined;
  const activeMapKey = mapDataCacheKey(geographyLevel, metric, requestedMapYear);
  const mapData = mapDataByKey[activeMapKey] ?? null;
  const hasCachedMapData = Boolean(mapData);
  const displayYear = isCmhc
    ? (selectedYear ?? pendingUrlYear ?? availableYears[availableYears.length - 1])
    : 2021;
  const displayedYearOptions =
    isCmhc && pendingUrlYear !== null && !availableYears.includes(pendingUrlYear)
      ? [...availableYears, pendingUrlYear].sort((a, b) => a - b)
      : availableYears;

  const comparisonIds = useMemo(() => {
    if (geographyLevel === "census_tract") {
      return selectedGeoid ? [selectedGeoid] : [];
    }
    if (!selectedGeoid) {
      return defaultCompareIds;
    }
    return [selectedGeoid, ...defaultCompareIds.filter((geoid) => geoid !== selectedGeoid)];
  }, [geographyLevel, selectedGeoid]);

  const mapRequestKey = `${activeMapKey}:${retryKey}`;
  const summaryRequestKey = `${geographyLevel}:${selectedGeoid ?? "all"}:${isCmhc ? selectedYear ?? "latest" : "census"}:${retryKey}`;
  const comparisonRequestKey = `${geographyLevel}:${comparisonIds.join(",")}:${isCmhc ? selectedYear ?? "latest" : "census"}:${retryKey}`;
  const dataRequestKey = `${mapRequestKey}|${summaryRequestKey}|${comparisonRequestKey}`;
  const mapError = mapFailure?.key === mapRequestKey ? mapFailure.error : null;
  const mapLoading = !hasCachedMapData && !mapError;
  const summary = summaryState?.key === summaryRequestKey ? summaryState.data : null;
  const summaryError = summaryState?.key === summaryRequestKey ? summaryState.error : null;
  const summaryLoading = summaryState?.key !== summaryRequestKey;
  const comparison = comparisonState?.key === comparisonRequestKey ? comparisonState.data : null;
  const comparisonError = comparisonState?.key === comparisonRequestKey ? comparisonState.error : null;
  const comparisonLoading = comparisonState?.key !== comparisonRequestKey;
  const dataLoading = mapLoading || summaryLoading || comparisonLoading;
  const error = summaryError ?? comparisonError;
  const selectedFeature = selected
    ? mapData?.features.find((feature) => feature.properties.geoid === selected.geoid)
    : undefined;
  const selectedCmhcMetrics: CmhcMetricValues | null =
    selectedFeature?.properties.cmhc_metrics ?? null;
  const selectedCmhcYear = selectedFeature?.properties.cmhc_year;

  const applyUrlState = useCallback(() => {
    const parsed = parseDashboardUrl(window.location.search);
    const knownCmhcYears = availableYearsRef.current;
    const hasResolvedCmhcYears = cmhcYearsResolvedRef.current;
    const yearIsAvailable =
      parsed.year !== undefined &&
      hasResolvedCmhcYears &&
      knownCmhcYears.includes(parsed.year);
    const canonicalYear = hasResolvedCmhcYears
      ? yearIsAvailable
        ? parsed.year
        : knownCmhcYears.at(-1)
      : parsed.year;

    setMetric(parsed.metric);
    setGeographyLevel(parsed.level);
    setSelectedYear(yearIsAvailable ? parsed.year : undefined);
    setPendingUrlYear(hasResolvedCmhcYears ? null : (parsed.year ?? null));
    setPendingUrlGeoid(parsed.geoid ?? null);
    setSelected(null);
    setSearch("");
    setSearchResults([]);
    setSearchLoading(false);
    setSearchError(null);
    setSearchHighlight(-1);
    setSearchExpanded(false);
    setDetailsPanelOpen(false);
    setContextAnnouncement(
      parsed.adjustedForTransit
        ? "Transit metrics are available by census tract, so this shared view was opened at the census tract level."
        : parsed.year !== undefined && hasResolvedCmhcYears && !yearIsAvailable
          ? `CMHC data for ${parsed.year} is unavailable. Showing the latest available year instead.`
          : ""
    );
    setUrlStateReady(true);

    commitDashboardUrl(
      {
        level: parsed.level,
        metric: parsed.metric,
        year: canonicalYear,
        geoid: parsed.geoid
      },
      "replace"
    );
  }, []);

  useEffect(() => {
    const initializationTimer = window.setTimeout(applyUrlState, 0);
    window.addEventListener("popstate", applyUrlState);
    return () => {
      window.clearTimeout(initializationTimer);
      window.removeEventListener("popstate", applyUrlState);
    };
  }, [applyUrlState]);

  function currentShareableYear(): number | undefined {
    return (
      selectedYear ??
      pendingUrlYear ??
      (cmhcYearsResolvedRef.current ? availableYearsRef.current.at(-1) : undefined)
    );
  }

  function updateDashboardUrl(
    overrides: Partial<{
      level: GeographyLevel;
      metric: MetricKey;
      year: number | undefined;
      geoid: string | undefined;
    }>,
    mode: UrlHistoryMode = "push"
  ) {
    commitDashboardUrl(
      {
        level: overrides.level ?? geographyLevel,
        metric: overrides.metric ?? metric,
        year: "year" in overrides ? overrides.year : currentShareableYear(),
        geoid: "geoid" in overrides ? overrides.geoid : selectedGeoid
      },
      mode
    );
  }

  useEffect(() => {
    if (!urlStateReady || !dataLoading) return;
    const timer = window.setTimeout(() => setSlowConnectionKey(dataRequestKey), 1_500);
    return () => window.clearTimeout(timer);
  }, [dataLoading, dataRequestKey, urlStateReady]);

  function handleGeographyLevelChange(level: GeographyLevel) {
    if (level === geographyLevel) {
      return;
    }
    if (isTransit && level !== "census_tract") {
      setContextAnnouncement(
        "Transit metrics are only available by census tract. Choose a non-transit metric before switching to municipalities."
      );
      return;
    }
    setGeographyLevel(level);
    setSelected(null);
    setPendingUrlGeoid(null);
    setSearch("");
    setSearchResults([]);
    setSearchLoading(false);
    setSearchError(null);
    setSearchExpanded(false);
    setDetailsPanelOpen(false);
    updateDashboardUrl({ level, geoid: undefined });
  }

  function handleMetricChange(nextMetric: MetricKey) {
    const requiresTracts = isTransitMetric(nextMetric);
    const nextLevel = requiresTracts ? "census_tract" : geographyLevel;
    const changesGeography = nextLevel !== geographyLevel;

    setMetric(nextMetric);
    if (changesGeography) {
      setGeographyLevel(nextLevel);
      setSelected(null);
      setPendingUrlGeoid(null);
      setSearch("");
      setSearchResults([]);
      setSearchLoading(false);
      setSearchError(null);
      setSearchExpanded(false);
      setDetailsPanelOpen(false);
      setContextAnnouncement(
        selected
          ? "Transit data is available by census tract, so the view changed to census tracts and the previous selection was cleared."
          : "Transit data is available by census tract, so the view changed to census tracts."
      );
    }
    updateDashboardUrl({ metric: nextMetric, level: nextLevel, geoid: changesGeography ? undefined : selectedGeoid });
  }

  function retryRequests() {
    setRetryKey((current) => current + 1);
  }

  useEffect(() => {
    if (!urlStateReady || hasCachedMapData) {
      return;
    }
    const controller = new AbortController();

    getMapData(metric, geographyLevel, controller.signal, requestedMapYear)
      .then((mapPayload) => {
        if (controller.signal.aborted) return;
        const catalogYears = [
          ...new Set((mapPayload.metadata.available_years ?? []).filter(isPlausibleDataYear))
        ].sort((a, b) => a - b);
        const knownYears = cmhcYearsResolvedRef.current ? availableYearsRef.current : [];
        const years = catalogYears.length ? catalogYears : knownYears;
        const payloadCmhcYear = firstPlausibleDataYear(
          mapPayload.metadata.cmhc_year,
          isCmhc ? mapPayload.metadata.year : undefined
        );
        let resolvedUrlYear: number | undefined;

        if (years.length) {
          const latestYear = years.at(-1);
          const requestedYearIsAvailable =
            pendingUrlYear !== null && years.includes(pendingUrlYear);
          const selectedYearIsAvailable =
            selectedYear !== undefined && years.includes(selectedYear);

          resolvedUrlYear =
            pendingUrlYear !== null
              ? requestedYearIsAvailable
                ? pendingUrlYear
                : latestYear
              : selectedYearIsAvailable
                ? selectedYear
                : latestYear;

          availableYearsRef.current = years;
          cmhcYearsResolvedRef.current = true;
          setAvailableYears(years);

          if (isCmhc && resolvedUrlYear !== undefined) {
            setSelectedYear(resolvedUrlYear);
          }

          if (pendingUrlYear !== null) {
            setPendingUrlYear(null);
            if (!requestedYearIsAvailable && latestYear !== undefined) {
              setContextAnnouncement(
                `CMHC data for ${pendingUrlYear} is unavailable. Showing ${latestYear}, the latest available year.`
              );
            }
          }
        } else if (isCmhc) {
          const fallbackYear = firstPlausibleDataYear(payloadCmhcYear, selectedYear);
          resolvedUrlYear = fallbackYear;

          if (fallbackYear !== undefined) {
            availableYearsRef.current = [fallbackYear];
            cmhcYearsResolvedRef.current = true;
            setAvailableYears([fallbackYear]);
            setSelectedYear(fallbackYear);
          }

          if (pendingUrlYear !== null) {
            setPendingUrlYear(null);
            setContextAnnouncement(
              fallbackYear === undefined
                ? `CMHC year options could not be loaded, so ${pendingUrlYear} could not be verified. Showing the data service's default year.`
                : fallbackYear === pendingUrlYear
                  ? `CMHC year options could not be loaded. Showing ${fallbackYear}, the year reported by the data service.`
                  : `CMHC year options could not be loaded, so ${pendingUrlYear} could not be verified. Showing ${fallbackYear}, the year reported by the data service.`
            );
          }
        }

        if (isCmhc) {
          const currentUrlState = parseDashboardUrl(window.location.search);
          commitDashboardUrl(
            {
              level: currentUrlState.level,
              metric: currentUrlState.metric,
              year: resolvedUrlYear,
              geoid: currentUrlState.geoid
            },
            "replace"
          );
        }

        setMapDataByKey((current) => {
          let next = current[activeMapKey]
            ? current
            : {
                ...current,
                [activeMapKey]: mapPayload
              };
          if (isCmhc && resolvedUrlYear !== undefined && payloadCmhcYear === resolvedUrlYear) {
            const resolvedMapKey = mapDataCacheKey(
              geographyLevel,
              metric,
              resolvedUrlYear
            );
            if (!next[resolvedMapKey]) {
              next = { ...next, [resolvedMapKey]: mapPayload };
            }
          }
          return next;
        });
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) return;
        setMapFailure({ key: mapRequestKey, error: requestError.message });
      });

    return () => controller.abort();
  }, [activeMapKey, geographyLevel, hasCachedMapData, isCmhc, mapRequestKey, metric, pendingUrlYear, requestedMapYear, selectedYear, urlStateReady]);

  useEffect(() => {
    if (!urlStateReady || (isCmhc && pendingUrlYear !== null)) {
      return;
    }
    const controller = new AbortController();

    getSummary(selectedGeoid, geographyLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((summaryPayload) => {
        if (!controller.signal.aborted) {
          setSummaryState({ key: summaryRequestKey, data: summaryPayload, error: null });
        }
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setSummaryState({ key: summaryRequestKey, data: null, error: requestError.message });
      });

    return () => controller.abort();
  }, [geographyLevel, isCmhc, pendingUrlYear, selectedGeoid, selectedYear, summaryRequestKey, urlStateReady]);

  useEffect(() => {
    if (!urlStateReady || (isCmhc && pendingUrlYear !== null)) {
      return;
    }
    const controller = new AbortController();

    getComparison(comparisonIds, geographyLevel, controller.signal, isCmhc ? selectedYear : undefined)
      .then((comparisonPayload) => {
        if (!controller.signal.aborted) {
          setComparisonState({ key: comparisonRequestKey, data: comparisonPayload, error: null });
        }
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setComparisonState({ key: comparisonRequestKey, data: null, error: requestError.message });
      });

    return () => controller.abort();
  }, [comparisonIds, comparisonRequestKey, geographyLevel, isCmhc, pendingUrlYear, selectedYear, urlStateReady]);

  const visibleMapData = useMemo(() => applyMetricToMapData(mapData, metric), [mapData, metric]);

  useEffect(() => {
    if (!urlStateReady || !pendingUrlGeoid || !visibleMapData) {
      return;
    }

    const resolutionTimer = window.setTimeout(() => {
      const matchingFeature = visibleMapData.features.find(
        (feature) => feature.properties.geoid === pendingUrlGeoid
      );
      if (matchingFeature) {
        setSelected(geographyFromFeature(matchingFeature.properties));
        setSearch(matchingFeature.properties.name);
        setPendingUrlGeoid(null);
        setDetailsPanelOpen(true);
        setContextAnnouncement((current) =>
          joinAnnouncements(
            current,
            `Loaded the shared view for ${matchingFeature.properties.name}.`
          )
        );
        return;
      }

      setPendingUrlGeoid(null);
      setContextAnnouncement((current) =>
        joinAnnouncements(
          current,
          `The geography ${pendingUrlGeoid} is not available in this view. Showing the regional overview.`
        )
      );
      const currentUrlState = parseDashboardUrl(window.location.search);
      commitDashboardUrl(
        {
          level: currentUrlState.level,
          metric: currentUrlState.metric,
          year: currentUrlState.year,
          geoid: undefined
        },
        "replace"
      );
    }, 0);

    return () => window.clearTimeout(resolutionTimer);
  }, [pendingUrlGeoid, urlStateReady, visibleMapData]);

  useEffect(() => {
    if (!searchExpanded || !search.trim() || search === selected?.name) {
      return;
    }
    const controller = new AbortController();
    const requestId = searchRequestRef.current + 1;
    searchRequestRef.current = requestId;
    const timer = window.setTimeout(() => {
      searchGeographies(search, geographyLevel, controller.signal)
        .then((payload) => {
          if (controller.signal.aborted || searchRequestRef.current !== requestId) {
            return;
          }
          setSearchResults(payload.items);
          setSearchHighlight(-1);
          setSearchLoading(false);
          setSearchError(null);
        })
        .catch((err: unknown) => {
          if (
            controller.signal.aborted ||
            searchRequestRef.current !== requestId ||
            (err instanceof DOMException && err.name === "AbortError")
          ) {
            return;
          }
          setSearchResults([]);
          setSearchLoading(false);
          setSearchError("Search is temporarily unavailable. Check the API connection and try again.");
        });
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
      if (searchRequestRef.current === requestId) {
        searchRequestRef.current += 1;
      }
    };
  }, [geographyLevel, search, searchExpanded, selected?.name]);

  useEffect(() => {
    function dismissSearchOnOutsidePointer(event: PointerEvent) {
      if (
        searchContainerRef.current &&
        event.target instanceof Node &&
        !searchContainerRef.current.contains(event.target)
      ) {
        setSearchExpanded(false);
        setSearchHighlight(-1);
      }
    }

    document.addEventListener("pointerdown", dismissSearchOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", dismissSearchOnOutsidePointer);
  }, []);

  function handleFeatureSelect(feature: MapFeature["properties"]) {
    setSelected(geographyFromFeature(feature));
    setPendingUrlGeoid(null);
    setSearch(feature.name);
    setSearchResults([]);
    setSearchExpanded(false);
    setDetailsPanelOpen(true);
    updateDashboardUrl({ geoid: feature.geoid });
  }

  function selectSearchResult(geography: Geography) {
    setSelected(geography);
    setPendingUrlGeoid(null);
    setSearch(geography.name);
    setSearchResults([]);
    setSearchHighlight(-1);
    setSearchExpanded(false);
    setDetailsPanelOpen(true);
    updateDashboardUrl({ geoid: geography.geoid });
  }

  const visibleResults = searchResults.slice(0, 8);
  const searchOpen =
    searchExpanded &&
    visibleResults.length > 0 &&
    Boolean(search.trim()) &&
    search !== selected?.name;
  const highlightedSearchGeoid =
    searchOpen && searchHighlight >= 0
      ? visibleResults[searchHighlight]?.geoid
      : undefined;

  useEffect(() => {
    if (!highlightedSearchGeoid) {
      return;
    }
    document
      .getElementById(`search-option-${highlightedSearchGeoid}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [highlightedSearchGeoid]);

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && searchExpanded) {
      event.preventDefault();
      setSearchExpanded(false);
      setSearchHighlight(-1);
      searchInputRef.current?.blur();
      return;
    }
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
    }
  }

  return (
    <main
      data-testid="dashboard-root"
      data-selected-year={selectedYear ?? ""}
      data-pending-year={pendingUrlYear ?? ""}
      className="min-h-screen bg-civic-surface"
    >
      <header className="border-b border-civic-line bg-civic-panel">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <BrandMark className="h-7 w-7 shrink-0" />
              <span className="text-xs font-semibold uppercase tracking-wider text-civic-teal">
                CivicScope
              </span>
            </div>
            <h1 className="text-xl font-semibold leading-tight text-civic-ink lg:text-2xl">
              Greater Toronto Housing Affordability Explorer
            </h1>
            <p className="text-xs text-civic-muted lg:text-sm">
              Explore rent burden, income, and CMHC housing data across 25 GTA municipalities and
              1,334 census tracts.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            <div
              ref={searchContainerRef}
              className="relative w-full sm:w-80"
              onBlurCapture={() => {
                // Safari can report a null relatedTarget while focus is moving
                // from the input to a result button. Defer the containment
                // check so the click is not unmounted before it can fire.
                window.requestAnimationFrame(() => {
                  const container = searchContainerRef.current;
                  if (container && !container.contains(document.activeElement)) {
                    setSearchExpanded(false);
                    setSearchHighlight(-1);
                  }
                });
              }}
            >
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
                  setSearchError(null);
                  if (next.trim()) {
                    setSearchResults([]);
                    setSearchLoading(true);
                    setSearchExpanded(true);
                  } else {
                    setSearchResults([]);
                    setSearchLoading(false);
                    setSearchExpanded(false);
                  }
                }}
                onFocus={() => {
                  if (search.trim() && search !== selected?.name) {
                    setSearchExpanded(true);
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
                      className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-civic-teal ${
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
              {searchExpanded &&
                !searchError &&
                searchResults.length === 0 &&
                search.trim() &&
                search !== selected?.name && (
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
              {searchExpanded && searchError && search.trim() && (
                <div
                  data-testid="search-error"
                  role="alert"
                  className="absolute right-0 z-20 mt-2 w-full rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 shadow-panel dark:border-red-800 dark:bg-red-950 dark:text-red-300"
                >
                  {searchError}
                </div>
              )}
              <div className="sr-only" aria-live="polite" aria-atomic="true">
                {searchOpen
                  ? `${visibleResults.length} result${visibleResults.length === 1 ? "" : "s"} available. Use arrow keys to navigate.`
                  : ""}
              </div>
            </div>
            <GeographyLevelSelector
              value={geographyLevel}
              onChange={handleGeographyLevelChange}
              municipalityDisabled={isTransit}
            />
            <MetricSelector value={metric} onChange={handleMetricChange} />
            <div className="flex flex-col gap-1">
              <span className="px-1 text-[11px] font-semibold uppercase tracking-wide text-civic-muted">
                {isCmhc ? "CMHC year" : "Census year"}
              </span>
              <YearSelector
                value={displayYear}
                availableYears={isCmhc ? displayedYearOptions : [2021]}
                disabled={!isCmhc || pendingUrlYear !== null}
                label={isCmhc ? "CMHC data year" : "Census data year"}
                onChange={(year) => {
                  setPendingUrlYear(null);
                  setSelectedYear(year);
                  updateDashboardUrl({ year });
                }}
              />
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {contextAnnouncement}
      </div>

      {slowConnectionKey === dataRequestKey && dataLoading && !error && !mapError ? (
        <div
          data-testid="data-service-status"
          role="status"
          className="mx-auto mt-4 max-w-[1552px] rounded-lg border border-civic-line bg-civic-panel px-4 py-3 text-sm text-civic-ink shadow-panel"
        >
          <p className="font-semibold">Still connecting to the CivicScope data service…</p>
          <p className="mt-1 text-xs text-civic-muted">
            The first visit can take longer while the service starts. Data will appear automatically.
          </p>
        </div>
      ) : null}

      {error && (
        <div
          data-testid="api-error"
          role="alert"
          className="mx-auto mt-4 flex max-w-[1552px] items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
        >
          <div>
            <div className="flex items-center gap-2 font-semibold">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              Data could not be loaded
            </div>
            <p className="mt-1 text-xs">{error}</p>
          </div>
          <button
            type="button"
            onClick={retryRequests}
            className="shrink-0 rounded-md border border-red-300 px-3 py-1.5 text-xs font-semibold hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2 focus-visible:ring-offset-red-50 dark:border-red-700 dark:hover:bg-red-900 dark:focus-visible:ring-red-300 dark:focus-visible:ring-offset-red-950"
          >
            Retry
          </button>
        </div>
      )}

      <div className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1.45fr)_430px] lg:px-6">
        <div className="order-1 xl:col-start-2 xl:row-start-1">
          <SummaryCards
            summary={summary}
            geographyLevel={geographyLevel}
            loading={summaryLoading && !summary}
          />
        </div>

        <section
          data-testid="map-panel"
          className="order-2 flex min-h-[400px] flex-col overflow-hidden rounded-lg border border-civic-line bg-civic-panel shadow-panel xl:col-start-1 xl:row-span-2 xl:row-start-1 xl:min-h-[560px]"
        >
          <div className="flex flex-col gap-2 border-b border-civic-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-civic-ink">GTA housing data map</h2>
              <p className="text-xs text-civic-muted">
                {getMetricLabel(metric)} by {geographyLabel.singular}
              </p>
              {isTransit ? (
                <TransitCoverageNotice snapshot={visibleMapData?.metadata.transit_snapshot} />
              ) : null}
              {geographyLevel === "census_tract" &&
                visibleMapData?.metadata.data_quality?.label?.includes("survey-zone") && (
                  <p className="mt-1 max-w-prose text-xs leading-5 text-teal-700 dark:text-teal-400">
                    Matched tracts show their CMHC survey zone&apos;s value. Tracts without a zone
                    match use the parent municipality and disclose that fallback in exported data.
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
                {isCmhc
                  ? `CMHC ${visibleMapData?.metadata.cmhc_year ?? displayYear}`
                  : isTransit
                    ? "Transit snapshot"
                    : `Census ${visibleMapData?.metadata.year ?? 2021}`}
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
              error={mapError}
              onRetry={retryRequests}
            />
          </div>
        </section>

        <button
          type="button"
          data-testid="details-toggle"
          onClick={() => setDetailsPanelOpen(!detailsPanelOpen)}
          className="order-3 flex min-h-11 items-center justify-center gap-2 rounded-lg border border-civic-line bg-civic-panel px-4 py-3 text-sm font-medium text-civic-ink shadow-panel transition hover:bg-civic-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 xl:hidden"
          aria-expanded={detailsPanelOpen}
          aria-controls="selected-geography-details"
        >
          <ChevronDown
            className={`h-4 w-4 transition-transform ${detailsPanelOpen ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
          {detailsPanelOpen ? "Hide" : "Show"}{" "}
          {selected ? `details for ${selected.name}` : "map guidance"}
        </button>

        <aside
          id="selected-geography-details"
          aria-label={selected ? `Details for ${selected.name}` : "Map guidance"}
          className={`${detailsPanelOpen ? "block" : "hidden xl:block"} order-3 xl:col-start-2 xl:row-start-2`}
        >
          <DetailPanel
            geography={selected}
            metric={metric}
            geographyLevel={geographyLevel}
            cmhcMetrics={selectedCmhcMetrics}
            cmhcYear={selectedCmhcYear}
            dataQualityLabel={visibleMapData?.metadata.data_quality?.label}
            metricStatus={visibleMapData?.metadata.data_quality?.metric_status}
            transitSnapshot={visibleMapData?.metadata.transit_snapshot}
            onClear={() => {
              setSelected(null);
              setPendingUrlGeoid(null);
              setSearch("");
              setSearchResults([]);
              setSearchExpanded(false);
              setDetailsPanelOpen(false);
              updateDashboardUrl({ geoid: undefined });
            }}
          />
        </aside>

        <section className="order-4 rounded-lg border border-civic-line bg-civic-panel shadow-panel xl:col-span-2 xl:row-start-3">
          <ComparisonPanel
            comparison={comparison}
            metric={metric}
            geographyLevel={geographyLevel}
            loading={comparisonLoading && !comparison}
            displayYear={isCmhc ? displayYear : undefined}
            isUserSelection={Boolean(selectedGeoid)}
            transitSnapshot={visibleMapData?.metadata.transit_snapshot}
          />
        </section>
      </div>

      <footer className="border-t border-civic-line bg-civic-panel">
        <div className="mx-auto max-w-[1600px] space-y-2 px-4 py-4 text-xs leading-5 text-civic-muted lg:px-6">
          <p>
            Boundaries and census metrics:{" "}
            <ExternalFooterLink href="https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E">
              Statistics Canada 2021 Census Profile
            </ExternalFooterLink>
            . Rental and housing-supply metrics:{" "}
            <ExternalFooterLink href="https://www03.cmhc-schl.gc.ca/hmip-pimh/en">
              CMHC Housing Market Information Portal
            </ExternalFooterLink>
            .
          </p>
          <p>
            Tract CMHC values use survey zones and published tract construction counts where
            available; inherited or allocated fallbacks are labeled per value.
          </p>
          <nav aria-label="Project documentation" className="flex flex-wrap gap-x-4 gap-y-1">
            <ExternalFooterLink href="https://github.com/FloaterW/civicscope/blob/main/docs/etl.md">
              Data methodology
            </ExternalFooterLink>
            <ExternalFooterLink href="https://github.com/FloaterW/civicscope/blob/main/docs/data-dictionary.md">
              Data dictionary
            </ExternalFooterLink>
            <ExternalFooterLink href="https://github.com/FloaterW/civicscope/issues/new">
              Report an accessibility or data issue
            </ExternalFooterLink>
          </nav>
        </div>
      </footer>
    </main>
  );
}

function ExternalFooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-civic-teal underline decoration-civic-teal/40 underline-offset-2 hover:decoration-civic-teal focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2"
    >
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

function geographyFromFeature(feature: MapFeature["properties"]): Geography {
  return {
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
  };
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

  const catalogEntry = data.metadata.metric_catalog?.[metric];
  return {
    ...data,
    metadata: {
      ...data.metadata,
      metric,
      data_quality: catalogEntry?.data_quality ?? data.metadata.data_quality,
      source: catalogEntry?.source ?? data.metadata.source,
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
