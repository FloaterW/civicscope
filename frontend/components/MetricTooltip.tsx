"use client";

import { Info } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

const metricDefinitions: Record<string, { term: string; definition: string; source: string }> = {
  rent_burden_pct: {
    term: "Rent burden",
    definition:
      "The share of renter households spending 30% or more of before-tax income on shelter costs. Crossing this threshold means the affordability standard is not met; core housing need also considers housing adequacy or suitability and whether acceptable alternative housing is affordable.",
    source: "Statistics Canada, 2021 Census of Population, Catalogue no. 98-316-X2021001"
  },
  affordability_index: {
    term: "Affordability index",
    definition:
      "Ratio of median household income to the income required to afford the median rent (at the 30% threshold). Values above 100 indicate the median household can afford the median rent; below 100 means it cannot.",
    source: "Derived from Statistics Canada 2021 Census Profile (median income and median rent)"
  },
  median_income: {
    term: "Median household income",
    definition:
      "The amount that divides the income distribution of private households into two equal halves — half have incomes above this value and half below. Refers to total income before taxes and deductions.",
    source: "Statistics Canada, 2021 Census of Population, Table 98-10-0055-01"
  },
  median_rent: {
    term: "Median monthly rent",
    definition:
      "The amount that divides the rent distribution of tenant-occupied private households into two halves. Includes payments for electricity, heat, water, and other municipal services where applicable.",
    source: "Statistics Canada, 2021 Census of Population, Catalogue no. 98-316-X2021001"
  },
  rent_to_income_ratio: {
    term: "Rent-to-income ratio",
    definition:
      "Median monthly rent divided by median monthly household income, expressed as a percentage. Provides a simplified indicator of housing cost pressure at the area level.",
    source: "Derived from Statistics Canada 2021 Census Profile"
  },
  population: {
    term: "Population",
    definition:
      "Total population count from the 2021 Census of Population. Includes all persons who have a usual place of residence in Canada, as well as Canadians abroad.",
    source: "Statistics Canada, 2021 Census of Population, Table 98-10-0001-01"
  },
  population_growth_pct: {
    term: "Population growth",
    definition:
      "Percentage change in total population between the 2016 Census and the 2021 Census. Positive values indicate growth; negative values indicate decline.",
    source: "Statistics Canada, 2021 Census of Population"
  },
  vacancy_rate: {
    term: "Vacancy rate",
    definition:
      "The proportion of rental units in the surveyed universe that were physically unoccupied and available for immediate rental on the reference date (October). A lower rate indicates a tighter rental market.",
    source: "CMHC Rental Market Survey (RMS), Housing Market Information Portal"
  },
  average_rent_total: {
    term: "Average rent (CMHC)",
    definition:
      "The average monthly rent for all bedroom types in the private purpose-built rental apartment universe of structures with three or more units, as surveyed in October of the reference year.",
    source: "CMHC Rental Market Survey (RMS), Housing Market Information Portal"
  },
  availability_rate: {
    term: "Availability rate",
    definition:
      "The proportion of rental units that are either vacant or occupied by a tenant who has given notice to move. A broader measure of market looseness than the vacancy rate alone.",
    source: "CMHC Rental Market Survey (RMS), Housing Market Information Portal"
  },
  turnover_rate: {
    term: "Turnover rate",
    definition:
      "The proportion of rental units that were turned over to a new tenant during the 12-month period preceding the survey. Higher turnover can indicate residential instability or market churn.",
    source: "CMHC Rental Market Survey (RMS), Housing Market Information Portal"
  },
  housing_starts_total: {
    term: "Housing starts",
    definition:
      "The number of new dwelling units where construction has begun (foundation poured or equivalent) during the reference period. Includes all intended markets: ownership, rental, and condo.",
    source: "CMHC Starts and Completions Survey (SCSS)"
  },
  housing_completions: {
    term: "Housing completions",
    definition:
      "The number of new dwelling units that reached completion (ready for occupancy) during the reference period. A trailing indicator of new supply entering the market.",
    source: "CMHC Starts and Completions Survey (SCSS)"
  },
  rental_universe: {
    term: "Rental universe",
    definition:
      "The total count of private purpose-built rental units in structures with three or more units, as surveyed by CMHC. Excludes condos rented in the secondary market, social housing not captured in the survey frame, and rented single/semi-detached homes.",
    source: "CMHC Rental Market Survey (RMS), Housing Market Information Portal"
  },
  transit_score: {
    term: "Transit access score",
    definition:
      "A 0-100 index measuring transit service density near each census tract. Counts unique transit routes (bus, rail, streetcar) within 800m of the tract boundary, then normalizes across all GTA tracts using decile clamping. Higher scores indicate more transit options.",
    source: "Derived from agency-published GTFS static feeds; current agency coverage is disclosed in the API snapshot metadata"
  },
  transit_route_count: {
    term: "Transit routes nearby",
    definition:
      "The number of unique transit routes with at least one stop within 800m of the census tract boundary. Includes bus, streetcar, subway, and commuter rail routes from all GTA transit agencies.",
    source: "Derived from agency-published GTFS static feeds; current agency coverage is disclosed in the API snapshot metadata"
  }
};

export function getMetricDefinition(metricKey: string) {
  return metricDefinitions[metricKey] ?? null;
}

export function MetricTooltip({ metricKey }: { metricKey: string }) {
  const def = metricDefinitions[metricKey];
  if (!def) return null;

  return <InfoTooltip term={def.term} definition={def.definition} source={def.source} />;
}

function InfoTooltip({ term, definition, source }: { term: string; definition: string; source: string }) {
  const [open, setOpen] = useState(false);
  const [clickLocked, setClickLocked] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const tooltipId = useId();

  const close = useCallback(() => {
    setOpen(false);
    setClickLocked(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open, close]);

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => {
          if (clickLocked) {
            close();
          } else {
            setOpen(true);
            setClickLocked(true);
          }
        }}
        onMouseEnter={() => { if (!clickLocked) setOpen(true); }}
        onMouseLeave={() => { if (!clickLocked) setOpen(false); }}
        className="inline-flex items-center justify-center rounded-full text-civic-muted transition hover:text-civic-teal focus:outline-none focus:ring-2 focus:ring-civic-teal focus:ring-offset-1"
        aria-label={`What is ${term}?`}
        aria-describedby={open ? tooltipId : undefined}
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div
          id={tooltipId}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-30 mb-2 w-72 max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-lg border border-civic-line bg-civic-panel p-3 shadow-lg"
        >
          <p className="text-xs font-semibold text-civic-ink">{term}</p>
          <p className="mt-1 text-xs leading-relaxed text-civic-muted">{definition}</p>
          <p className="mt-2 text-[10px] italic text-civic-muted/70">{source}</p>
          <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-civic-line" />
        </div>
      )}
    </div>
  );
}
