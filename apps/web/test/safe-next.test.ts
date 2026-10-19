import { describe, expect, it } from "vitest";
import { safeNext } from "@/lib/safe-next";

describe("safeNext refuses encoded tricks", () => {
  it("rejects encoded slashes, backslashes and control characters", () => {
    for (const value of ["/%2f/evil.example", "/%2F%2Fevil.example", "/%5c/evil.example", "/%5C%5Cevil.example", "/%09/evil.example", "/%0a/evil.example", "/%7f/x"]) {
      expect(safeNext(value)).toBe("/");
    }
  });

  it("keeps ordinary same-site paths, including harmless encoded characters", () => {
    expect(safeNext("/proposals/prop_01ABC")).toBe("/proposals/prop_01ABC");
    expect(safeNext("/forecast?week=7")).toBe("/forecast?week=7");
    expect(safeNext("/council?q=borrow%20now")).toBe("/council?q=borrow%20now");
  });
});
