import { describe, expect, it } from "vitest";

import { formatChartLabel } from "@/lib/chart-format";

describe("comparison chart labels", () => {
  it.each([undefined, null, "100", [100], Number.NaN, Number.POSITIVE_INFINITY])(
    "does not invent a numeric label for %s",
    (value) => expect(formatChartLabel("population", value, true)).toBe("")
  );

  it("keeps full values on wide charts and shortens large values on narrow charts", () => {
    expect(formatChartLabel("population", 2_794_356, false)).toBe("2,794,356");
    expect(formatChartLabel("population", 2_794_356, true)).toBe("2.8M");
    expect(formatChartLabel("population", 338_503, true)).toBe("339K");
    expect(formatChartLabel("median_income", 107_000, true)).toBe("107K");
    expect(formatChartLabel("population", 0, true)).toBe("0");
  });

  it("preserves signed percentages and small values", () => {
    expect(formatChartLabel("population_growth_pct", -20, true)).toBe("-20.0%");
    expect(formatChartLabel("rent_to_income_ratio", 0.22, true)).toBe("22%");
    expect(formatChartLabel("affordability_index", 133.7, true)).toBe("133.7");
    expect(formatChartLabel("median_rent", 900, true)).toBe("$900");
  });
});
