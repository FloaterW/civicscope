import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DataStatus } from "../../components/DataStatus";

describe("source-check disclosure", () => {
  it("does not imply a CMHC check covers the separately maintained zone snapshot", () => {
    const html = renderToStaticMarkup(createElement(DataStatus));
    expect(html).toContain("CMHC checks cover municipality and tract files");
    expect(html).toContain("not the separately maintained survey-zone snapshot");
    expect(html).toContain("Update status is currently unavailable");
  });
});
