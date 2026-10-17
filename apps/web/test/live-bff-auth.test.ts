import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mintInternalJwt, hasInternalJwtSecret } from "@/lib/server-auth";
import { GET, POST } from "@/app/api/fiona/[...path]/route";

describe("Live BFF session and token authentication (Task C)", () => {
  const originalEnv = { ...process.env };
  const testSecret = "0123456789abcdef0123456789abcdef"; // 32 bytes

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = { ...originalEnv };
    vi.restoreAllMocks();
  });

  it("mints a valid HS256 JWT when INTERNAL_JWT_SECRET is configured", () => {
    process.env.INTERNAL_JWT_SECRET = testSecret;
    expect(hasInternalJwtSecret()).toBe(true);

    const token = mintInternalJwt({
      userId: "usr_owner_01",
      tenantId: "ten_karachi_apparel",
      role: "owner",
      aud: "fiona-engine",
    });

    expect(token).toBeTruthy();
    const parts = token!.split(".");
    expect(parts).toHaveLength(3);

    const [p0 = "", p1 = ""] = parts;
    const header = JSON.parse(Buffer.from(p0, "base64url").toString("utf-8"));
    const payload = JSON.parse(Buffer.from(p1, "base64url").toString("utf-8"));

    expect(header).toEqual({ alg: "HS256", typ: "JWT" });
    expect(payload.sub).toBe("usr_owner_01");
    expect(payload.tenant_id).toBe("ten_karachi_apparel");
    expect(payload.role).toBe("owner");
    expect(payload.aud).toBe("fiona-engine");
    expect(payload.exp - payload.iat).toBeLessThanOrEqual(60);
  });

  it("returns null if INTERNAL_JWT_SECRET is missing or too short", () => {
    delete process.env.INTERNAL_JWT_SECRET;
    expect(hasInternalJwtSecret()).toBe(false);
    expect(mintInternalJwt()).toBeNull();

    process.env.INTERNAL_JWT_SECRET = "short-secret";
    expect(hasInternalJwtSecret()).toBe(false);
    expect(mintInternalJwt()).toBeNull();
  });

  it("fails closed with 501 in live mode when internal authentication is not configured", async () => {
    delete process.env.INTERNAL_JWT_SECRET;
    process.env.NEXT_PUBLIC_API_MODE = "live";
    process.env.FIONA_MODE = "live";

    const request = new Request("http://localhost/api/fiona/forecast/cash");
    const response = await GET(request, { params: Promise.resolve({ path: ["forecast", "cash"] }) });

    expect(response.status).toBe(501);
    const body = await response.json();
    expect(body.error.code).toBe("live_bff_not_configured");
  });

  it("handles decision submissions in live mode when authenticated", async () => {
    process.env.INTERNAL_JWT_SECRET = testSecret;
    process.env.NEXT_PUBLIC_API_MODE = "live";
    process.env.FIONA_MODE = "live";
    process.env.ENGINE_BASE_URL = "http://127.0.0.1:8000";

    // Mock fetch for engine POST /v1/proposals/prp_001/decision
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ api_version: "v1", status: "executed" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );

    const req = new Request("http://localhost/api/fiona/proposals/prp_001/decision", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision: "approve", decided_by: "usr_owner_01" }),
    });

    const res = await POST(req, { params: Promise.resolve({ path: ["proposals", "prp_001", "decision"] }) });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe("executed");

    // Verify token was forwarded in Authorization header
    expect(fetchSpy).toHaveBeenCalled();
    const firstCall = fetchSpy.mock.calls[0];
    expect(firstCall).toBeDefined();
    const calledHeaders = (firstCall?.[1]?.headers ?? {}) as Record<string, string>;
    expect(calledHeaders.Authorization).toMatch(/^Bearer ey/);
    expect(calledHeaders["X-Fiona-Tenant"]).toBe("ten_karachi_apparel");
  });
});
