import type {
  CmhcCountSource,
  CmhcMetricValues,
  CmhcRmsSource,
  GeographyLevel,
  MetricFieldStatus,
  MetricValues
} from "@/types";

export const CSV_HEADERS = ["Metric", "Value", "Period", "Source", "Method", "Status"];

type Row = [string, string, string, string, string, string];

function valueText(value: number | null | undefined): string {
  return value == null ? "" : String(value);
}

function censusStatus(status: MetricFieldStatus | undefined): string {
  return status ?? "unavailable";
}

function censusMethod(key: string, status: MetricFieldStatus | undefined): string {
  if (status === "estimated" && key === "rent_burden_pct") {
    return "Estimated from median rent and household income";
  }
  if (status === "low_confidence") {
    return "Derived from a small 2016 population base; use with caution";
  }
  if (key === "population_growth_pct") {
    return "Derived from published 2016 and 2021 population counts";
  }
  if (key === "affordability_index") {
    return "Derived from median rent and household income";
  }
  return status === "unavailable" ? "Suppressed or unavailable" : "Published value";
}

function rmsSourceLabel(source: CmhcRmsSource | undefined, zone?: string | null): string {
  if (source === "survey_zone") {
    return `CMHC Rental Market Survey — survey zone${zone ? ` (${zone})` : ""}`;
  }
  if (source === "inherited_municipality") {
    return "CMHC Rental Market Survey — parent municipality";
  }
  return "CMHC Rental Market Survey — municipality";
}

function rmsMethod(source: CmhcRmsSource | undefined): string {
  if (source === "survey_zone") return "Published at survey-zone granularity";
  if (source === "inherited_municipality") return "Inherited from parent municipality";
  return "Published or aggregated at municipality granularity";
}

function countProvenance(
  source: CmhcCountSource | undefined,
  geographyLevel: GeographyLevel
): [string, string, string] {
  if (geographyLevel === "municipality") {
    return ["CMHC Starts & Completions Survey — municipality", "Published value", "official"];
  }
  if (source === "official") {
    return ["CMHC Starts & Completions Survey — census tract", "Published tract value", "official"];
  }
  if (source === "estimated_parent") {
    return [
      "CMHC Starts & Completions Survey — parent census tract",
      "Allocated from a published parent tract after a boundary split",
      "estimated_parent"
    ];
  }
  return [
    "CMHC Starts & Completions Survey — parent municipality",
    "Allocated by renter-household share",
    "estimated"
  ];
}

export function buildGeographyExportRows(
  geographyLevel: GeographyLevel,
  metrics: MetricValues,
  cmhcMetrics?: CmhcMetricValues | null,
  cmhcYear?: number
): string[][] {
  const rows: Row[] = [];
  const quality = metrics.data_quality;
  const add = (
    label: string,
    value: number | null | undefined,
    period: string,
    source: string,
    method: string,
    status: string
  ) => rows.push([label, valueText(value), period, source, method, value == null ? "unavailable" : status]);

  const censusFields: Array<[string, keyof MetricValues]> = [
    ["Median household income", "median_income"],
    ["Median rent", "median_rent"],
    ["Rent burden", "rent_burden_pct"],
    ["Population growth", "population_growth_pct"],
    ["Population", "population"],
    ["Affordability index", "affordability_index"]
  ];
  for (const [label, key] of censusFields) {
    const status = quality?.[key as keyof typeof quality];
    add(
      label,
      metrics[key] as number | null,
      "2021 Census",
      "Statistics Canada Census Profile",
      censusMethod(key, status),
      censusStatus(status)
    );
  }

  if (cmhcMetrics) {
    const year = cmhcYear ?? cmhcMetrics.year;
    const rmsFields: Array<[string, keyof CmhcMetricValues]> = [
      ["Vacancy rate", "vacancy_rate"],
      ["Availability rate", "availability_rate"],
      ["Average rent", "average_rent_total"],
      ["Turnover rate", "turnover_rate"],
      ["Bachelor rent", "average_rent_bachelor"],
      ["1-bedroom rent", "average_rent_1br"],
      ["2-bedroom rent", "average_rent_2br"],
      ["3-bedroom+ rent", "average_rent_3br_plus"]
    ];
    for (const [label, key] of rmsFields) {
      const source =
        key === "vacancy_rate"
          ? cmhcMetrics.vacancy_rate_source
          : key === "average_rent_total"
            ? cmhcMetrics.average_rent_total_source
            : cmhcMetrics.other_rms_source;
      add(
        label,
        cmhcMetrics[key] as number | null,
        `October ${year} survey`,
        rmsSourceLabel(source, cmhcMetrics.survey_zone),
        rmsMethod(source),
        source === "inherited_municipality" ? "inherited" : "official"
      );
    }

    const universeSource = cmhcMetrics.other_rms_source;
    add(
      "Rental universe",
      cmhcMetrics.rental_universe,
      `October ${year} survey`,
      rmsSourceLabel(universeSource, cmhcMetrics.survey_zone),
      geographyLevel === "census_tract"
        ? "Allocated from the parent municipality by renter-household share"
        : rmsMethod(universeSource),
      geographyLevel === "census_tract" ? "estimated" : "official"
    );

    const supplyFields: Array<[
      string,
      keyof CmhcMetricValues,
      "annual" | "december",
      CmhcCountSource | undefined
    ]> = [
      ["Housing starts", "housing_starts_total", "annual", cmhcMetrics.starts_source],
      ["Housing completions", "housing_completions", "annual", cmhcMetrics.completions_source],
      ["Units under construction", "units_under_construction", "december", undefined],
      ["Unabsorbed units", "unabsorbed_units", "december", undefined]
    ];
    for (const [label, key, periodType, countSource] of supplyFields) {
      const provenance = countProvenance(countSource, geographyLevel);
      add(
        label,
        cmhcMetrics[key] as number | null,
        periodType === "annual" ? `Calendar year ${year}` : `December ${year}`,
        provenance[0],
        provenance[1],
        provenance[2]
      );
    }
  }

  add(
    "Transit access score",
    metrics.transit_score,
    "Current packaged GTFS snapshot",
    "Agency-published GTFS schedules",
    "Unique routes within 800m, normalized across GTA tracts",
    metrics.data_quality?.transit_score ?? "unavailable"
  );
  add(
    "Transit routes nearby",
    metrics.transit_route_count,
    "Current packaged GTFS snapshot",
    "Agency-published GTFS schedules",
    "Unique scheduled routes with a stop within 800m",
    metrics.data_quality?.transit_route_count ?? "unavailable"
  );

  return [CSV_HEADERS, ...rows];
}

export function rowsToCsv(rows: string[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          const text = String(cell);
          const spreadsheetSafe = /^[\t\r ]*[=+\-@]/.test(text) ? `'${text}` : text;
          return `"${spreadsheetSafe.replace(/"/g, '""')}"`;
        })
        .join(",")
    )
    .join("\n");
}
