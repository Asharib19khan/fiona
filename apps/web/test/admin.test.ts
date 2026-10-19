import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isSuperAdmin } from "@/lib/session";
import { AdminError, createUser, requireSuperAdmin, updateUser } from "@/lib/admin";
import { supabaseServer } from "@/lib/supabase/server";
import { GET as listRoute } from "@/app/api/admin/users/route";

vi.mock("@/lib/supabase/server", () => ({ supabaseServer: vi.fn(), authConfigured: () => true }));

const USER_ID = "11111111-1111-1111-1111-111111111111";

function signedInAs(
  user: { email: string; app_metadata: Record<string, unknown>; factors?: Array<{ status: string }> } | null,
  aal: "aal1" | "aal2" = "aal1",
) {
  vi.mocked(supabaseServer).mockResolvedValue({
    auth: {
      getUser: async () => ({ data: { user: user && { id: USER_ID, ...user } }, error: null }),
      getClaims: async () => ({ data: user ? { claims: { sub: USER_ID, aal } } : null, error: null }),
    },
  } as never);
}

describe("super admin", () => {
  const env = { ...process.env };
  beforeEach(() => {
    process.env.SUPER_ADMIN_EMAIL = "Boss@Example.com";
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "sb_secret_test";
  });
  afterEach(() => {
    process.env = { ...env };
    vi.restoreAllMocks();
  });

  it("needs both the flag and the configured address", () => {
    expect(isSuperAdmin({ super_admin: true }, "boss@example.com")).toBe(true);
    expect(isSuperAdmin({ super_admin: true }, "someone@example.com")).toBe(false);
    expect(isSuperAdmin({}, "boss@example.com")).toBe(false);
    expect(isSuperAdmin({ super_admin: "true" }, "boss@example.com")).toBe(false);
    delete process.env.SUPER_ADMIN_EMAIL;
    expect(isSuperAdmin({ super_admin: true }, "boss@example.com")).toBe(false);
  });

  it("refuses everyone else, checked against Supabase rather than the token", async () => {
    signedInAs({ email: "owner@example.com", app_metadata: { role: "owner", super_admin: true } });
    await expect(requireSuperAdmin()).rejects.toMatchObject({ status: 403 });
    signedInAs(null);
    await expect(requireSuperAdmin()).rejects.toMatchObject({ status: 401 });
    signedInAs({ email: "boss@example.com", app_metadata: { super_admin: true }, factors: [{ status: "verified" }] }, "aal2");
    await expect(requireSuperAdmin()).resolves.toMatchObject({ email: "boss@example.com" });
  });

  it("refuses a super admin who never set up two-step verification: it is mandatory", async () => {
    signedInAs({ email: "boss@example.com", app_metadata: { super_admin: true } }, "aal1");
    await expect(requireSuperAdmin()).rejects.toMatchObject({ status: 403, code: "mfa_setup_required" });
    const res = await listRoute();
    expect(res.status).toBe(403);
    expect((await res.json()).error.code).toBe("mfa_setup_required");
  });

  it("refuses when the verified token belongs to someone else", async () => {
    vi.mocked(supabaseServer).mockResolvedValue({
      auth: {
        getUser: async () => ({ data: { user: { id: USER_ID, email: "boss@example.com", app_metadata: { super_admin: true }, factors: [{ status: "verified" }] } }, error: null }),
        getClaims: async () => ({ data: { claims: { sub: "99999999-9999-9999-9999-999999999999", aal: "aal2" } }, error: null }),
      },
    } as never);
    await expect(requireSuperAdmin()).rejects.toMatchObject({ code: "mfa_required" });
  });

  it("asks a super admin with an authenticator for the two-step code before any admin call", async () => {
    const boss = { email: "boss@example.com", app_metadata: { super_admin: true }, factors: [{ status: "verified" }] };
    signedInAs(boss, "aal1");
    await expect(requireSuperAdmin()).rejects.toMatchObject({ status: 401, code: "mfa_required" });
    const res = await listRoute();
    expect(res.status).toBe(401);
    expect((await res.json()).error.code).toBe("mfa_required");
    signedInAs(boss, "aal2");
    await expect(requireSuperAdmin()).resolves.toMatchObject({ email: "boss@example.com" });
  });

  it("the admin API answers 403 to a signed-in owner who is not the super admin", async () => {
    signedInAs({ email: "owner@example.com", app_metadata: { role: "owner", tenant_id: "ten_karachi_apparel" } });
    const res = await listRoute();
    expect(res.status).toBe(403);
    expect((await res.json()).error.code).toBe("super_admin_only");
  });

  it("never creates a second account for the super admin address and validates input", async () => {
    await expect(createUser({ email: "BOSS@example.com", name: "Copy", tenantId: "ten_karachi_apparel", role: "owner" })).rejects.toMatchObject({ code: "reserved" });
    await expect(createUser({ email: "new@example.com", name: "New Person", tenantId: "karachi", role: "owner" })).rejects.toMatchObject({ code: "invalid_workspace" });
    await expect(createUser({ email: "not-an-email", name: "New Person", tenantId: "ten_karachi_apparel", role: "owner" })).rejects.toBeInstanceOf(AdminError);
  });

  it("creates accounts with workspace and role in app_metadata, and protects the super admin", async () => {
    const calls: Array<{ method: string; url: string; body: unknown }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method: String(init?.method), url: String(url), body });
      const record = url.toString().endsWith("/users")
        ? { id: "22222222-2222-2222-2222-222222222222", email: body.email, app_metadata: body.app_metadata, user_metadata: body.user_metadata, created_at: "2026-10-18T00:00:00Z" }
        : { id: "33333333-3333-3333-3333-333333333333", email: "boss@example.com", app_metadata: { super_admin: true }, created_at: "2026-10-18T00:00:00Z" };
      return new Response(JSON.stringify(record), { status: 200 });
    });
    const { user, temporaryPassword } = await createUser({ email: "Finance@Example.com", name: "Sara", tenantId: "ten_karachi_apparel", role: "finance" });
    expect(user).toMatchObject({ email: "finance@example.com", tenantId: "ten_karachi_apparel", role: "finance", superAdmin: false });
    expect(temporaryPassword.length).toBeGreaterThanOrEqual(16);
    expect(calls[0]!.body).toMatchObject({ email_confirm: true, app_metadata: { tenant_id: "ten_karachi_apparel", role: "finance" } });
    expect(JSON.stringify(calls[0]!.body)).not.toContain("super_admin");

    await expect(updateUser("33333333-3333-3333-3333-333333333333", { disabled: true })).rejects.toMatchObject({ code: "protected" });
  });
});
