import { describe, expect, it } from "vitest";

import { mapAnimationDuration } from "@/lib/map-motion";

describe("map motion preferences", () => {
  it("uses the requested duration for ordinary animated fits", () => {
    expect(mapAnimationDuration(true, false, 450)).toBe(450);
  });

  it("removes animation when the user prefers reduced motion", () => {
    expect(mapAnimationDuration(true, true, 450)).toBe(0);
  });

  it("keeps non-animated initial fits instantaneous", () => {
    expect(mapAnimationDuration(false, false, 650)).toBe(0);
  });
});
