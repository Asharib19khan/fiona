import { describe, expect, it } from "vitest";

import { getMockBriefing, screenPreviews } from "@/lib/mock-api";

describe("mock workspace data", () => {
  it("keeps the default briefing and every domain preview available", () => {
    expect(getMockBriefing("default")?.cards.length).toBeGreaterThan(0);
    expect(Object.keys(screenPreviews)).toEqual([
      "forecast",
      "financing",
      "inventory",
      "audit",
      "import",
      "launch-lab",
      "council",
    ]);
  });

  it("labels every preview as synthetic and non-executing", () => {
    for (const preview of Object.values(screenPreviews)) {
      expect(preview.note).toMatch(/preview|fixture|illustrative/i);
    }
  });
});
