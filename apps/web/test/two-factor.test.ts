import { describe, expect, it } from "vitest";

import { safeNext } from "@/lib/safe-next";
import { mfaState } from "@/lib/supabase/mfa";

type Factor = { status: "verified" | "unverified" };

function client(result: { factors?: Factor[]; error?: boolean }) {
  let calls = 0;
  return {
    calls: () => calls,
    auth: {
      getUser: async () => {
        calls += 1;
        return result.error
          ? { data: { user: null }, error: new Error("network") }
          : { data: { user: { factors: result.factors ?? [] } }, error: null };
      },
    },
  } as unknown as Parameters<typeof mfaState>[0] & { calls: () => number };
}

describe("two-step verification state", () => {
  it("accepts a session that already used its second factor without asking Supabase", async () => {
    const supabase = client({ factors: [{ status: "verified" }] });
    expect(await mfaState(supabase, "aal2")).toBe("verified");
    expect(supabase.calls()).toBe(0);
  });

  it("requires the code when the person has a verified authenticator but the session is aal1", async () => {
    expect(await mfaState(client({ factors: [{ status: "verified" }] }), "aal1")).toBe("required");
  });

  it("lets a password-only account through, ignoring half-finished setups", async () => {
    expect(await mfaState(client({ factors: [] }), "aal1")).toBe("not_enrolled");
    expect(await mfaState(client({ factors: [{ status: "unverified" }] }), "aal1")).toBe("not_enrolled");
  });

  it("fails closed when Supabase cannot be asked", async () => {
    expect(await mfaState(client({ error: true }), "aal1")).toBe("required");
    expect(await mfaState(client({ factors: [] }), undefined)).toBe("not_enrolled");
  });
});

describe("where to go after signing in", () => {
  it("keeps same-site paths", () => {
    expect(safeNext("/approvals")).toBe("/approvals");
    expect(safeNext("/reset-password?x=1")).toBe("/reset-password?x=1");
  });

  it("refuses other sites and odd forms", () => {
    for (const value of ["https://evil.example", "//evil.example", "/\\evil.example", "evil", "", null, undefined]) {
      expect(safeNext(value)).toBe("/");
    }
  });

  it("refuses paths a browser would turn into another site (tabs, newlines, backslashes)", () => {
    for (const value of ["/\t/evil.example", "/\n/evil.example", "/\r//evil.example", "/x\\..\\/evil.example", "/\u0000/evil.example", "/" + "a".repeat(3000)]) {
      expect(safeNext(value)).toBe("/");
    }
    // Still percent-encoded, it stays a path on this site.
    expect(new URL(safeNext("/%09/evil.example"), "https://fiona.app").host).toBe("fiona.app");
  });
});
