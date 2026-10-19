import { describe, expect, it } from "vitest";
import { basisPointsText } from "@/lib/figure-format";

describe("basis points on screen", () => {
  it("shows rates as percentages and cover figures as multiples", () => {
    expect(basisPointsText(1551, "financing.effective_annual_cost_low")).toBe("15.51%");
    expect(basisPointsText(26_800, "engine.analysis.coverage.dscr_forward")).toBe("2.68×");
    expect(basisPointsText(15_000, "liquidity.current_ratio")).toBe("1.50×");
    expect(basisPointsText(4_838, "profit.gross_margin")).toBe("48.38%");
  });
});
