import { describe, expect, it, vi } from "vitest";
import { GET } from "@/app/api/healthz/route";

describe("GET /api/healthz", () => {
  it("reports ok with api_version v1 in mock mode by default", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_MODE", "");
    const res = GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ api_version: "v1", status: "ok", service: "web", mode: "mock" });
    vi.unstubAllEnvs();
  });

  it("fails loudly on an unknown API mode", () => {
    vi.stubEnv("NEXT_PUBLIC_API_MODE", "staging");
    expect(() => GET()).toThrow(/must be "mock" or "live"/);
    vi.unstubAllEnvs();
  });
});
