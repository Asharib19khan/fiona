import { describe, expect, it } from "vitest";
import { minorExponent, toMajor } from "../src/index";

describe("money display uses ISO 4217 minor units, not Intl display digits", () => {
  it("treats PKR minor units as paisa (exponent 2), although Intl shows PKR with 0 decimals", () => {
    expect(new Intl.NumberFormat("en", { style: "currency", currency: "PKR" }).resolvedOptions().maximumFractionDigits).toBe(0);
    expect(minorExponent("PKR")).toBe(2);
    expect(toMajor(200_000_000, "PKR")).toBe(2_000_000); // the demo cash buffer: PKR 2 million
    expect(toMajor(-1_248_386_413, "PKR")).toBeCloseTo(-12_483_864.13, 2);
  });

  it("knows zero- and three-decimal currencies", () => {
    expect(toMajor(1_500, "JPY")).toBe(1_500);
    expect(toMajor(1_500, "KWD")).toBe(1.5);
    expect(toMajor(1_500, "CNY")).toBe(15);
  });
});
