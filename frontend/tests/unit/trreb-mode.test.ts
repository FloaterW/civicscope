import { describe, expect, it } from "vitest";
import { getTrrebMode } from "@/lib/trreb-mode";

describe("TRREB display gates", () => {
  it.each(["development", "production", "test", undefined])("defaults off in %s", runtime => {
    expect(getTrrebMode({ runtime })).toBe("disabled");
  });
  it.each(["production", "test", undefined])("never enables local preview in %s", runtime => {
    expect(getTrrebMode({ runtime, previewEnabled: "1" })).toBe("disabled");
  });
  it("enables the local preview only in development", () => {
    expect(getTrrebMode({ runtime: "development", previewEnabled: "1" })).toBe("preview");
  });
  it.each(["development", "production"])("requires an explicit public flag in %s", runtime => {
    expect(getTrrebMode({ runtime, publicEnabled: "1", previewEnabled: "1" })).toBe("public");
    expect(getTrrebMode({ runtime, publicEnabled: "true" })).toBe("disabled");
  });
});
