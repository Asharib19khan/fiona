import { afterEach, describe, expect, it } from "vitest";
import { sameOrigin } from "@/lib/same-origin";
import { localDemoAllowed } from "@/lib/session";

function post(headers: Record<string, string>) {
  return new Request("https://fiona.app/api/fiona/proposals", { method: "POST", headers: { host: "fiona.app", ...headers } });
}

describe("cross-site writes", () => {
  it("allows Fiona's own pages and non-browser callers", () => {
    expect(sameOrigin(post({ origin: "https://fiona.app", "sec-fetch-site": "same-origin" }))).toBe(true);
    expect(sameOrigin(post({}))).toBe(true);
  });

  it("refuses another site's page", () => {
    expect(sameOrigin(post({ origin: "https://evil.example" }))).toBe(false);
    expect(sameOrigin(post({ "sec-fetch-site": "cross-site" }))).toBe(false);
    expect(sameOrigin(post({ "sec-fetch-site": "same-site", origin: "https://sub.fiona.app" }))).toBe(false);
    expect(sameOrigin(post({ origin: "null" }))).toBe(false);
  });
});

describe("no-sign-in stand-in", () => {
  const env = { ...process.env };
  afterEach(() => { process.env = { ...env }; });

  it("exists only on a developer's machine in mock mode", () => {
    process.env.NEXT_PUBLIC_API_MODE = "mock";
    delete process.env.VERCEL; delete process.env.FLY_APP_NAME; delete process.env.FIONA_MODE;
    expect(localDemoAllowed()).toBe(true);
    process.env.VERCEL = "1";
    expect(localDemoAllowed()).toBe(false);
    delete process.env.VERCEL;
    process.env.FIONA_MODE = "live";
    expect(localDemoAllowed()).toBe(false);
    delete process.env.FIONA_MODE;
    process.env.NEXT_PUBLIC_API_MODE = "live";
    expect(localDemoAllowed()).toBe(false);
  });
});
