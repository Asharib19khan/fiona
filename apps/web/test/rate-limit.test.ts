import { beforeEach, describe, expect, it } from "vitest";
import { allow, clientKey, resetRateLimits } from "@/lib/rate-limit";

describe("rate limit", () => {
  beforeEach(() => resetRateLimits());

  it("allows up to the limit in the window, then refuses until it slides", () => {
    for (let i = 0; i < 3; i += 1) expect(allow("k", 3, 60_000, 1_000)).toBe(true);
    expect(allow("k", 3, 60_000, 1_000)).toBe(false);
    expect(allow("other", 3, 60_000, 1_000)).toBe(true);
    expect(allow("k", 3, 60_000, 61_001)).toBe(true);
  });

  it("keys callers by the first forwarded address", () => {
    const request = new Request("https://fiona.app/api/admin/users", { headers: { "x-forwarded-for": "203.0.113.7, 10.0.0.1" } });
    expect(clientKey(request)).toBe("203.0.113.7");
  });
});
