import { cache } from "react";
import { apiMode } from "@/lib/env";
import { authConfigured, supabaseServer } from "@/lib/supabase/server";

export type Role = "owner" | "finance";

export interface Session {
  /** The engine's user ID: `usr_` + the Supabase user ID without dashes. */
  userId: string;
  email: string | null;
  name: string;
  /** The workspace this person belongs to; null until an admin assigns one. */
  tenantId: string | null;
  role: Role | null;
  /** True for the local development stand-in used when Supabase Auth is not configured. */
  demo: boolean;
}

const TENANT = /^ten_[a-z0-9_]{1,60}$/;

function demoSession(): Session {
  const tenant = process.env.DEMO_TENANT_ID ?? "ten_karachi_apparel";
  return {
    userId: process.env.DEMO_USER_ID ?? "usr_owner_demo",
    email: null,
    name: "Local developer",
    tenantId: TENANT.test(tenant) ? tenant : null,
    role: "owner",
    demo: true,
  };
}

/**
 * Who is signed in, from a verified token. `getClaims()` checks the token's signature on every
 * call; the cookie alone is never trusted (it can be forged). Workspace and role come only from
 * `app_metadata`, which users cannot edit; `user_metadata` is used for the display name only.
 *
 * Without Supabase Auth configured, local mock mode uses a labelled stand-in; live mode refuses.
 */
export const getSession = cache(async (): Promise<Session | null> => {
  if (!authConfigured()) return apiMode() === "mock" ? demoSession() : null;
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (error || !claims?.sub) return null;
  const app = (claims.app_metadata ?? {}) as Record<string, unknown>;
  const profile = (claims.user_metadata ?? {}) as Record<string, unknown>;
  const tenant = typeof app.tenant_id === "string" && TENANT.test(app.tenant_id) ? app.tenant_id : null;
  const role = app.role === "owner" || app.role === "finance" ? app.role : null;
  const email = typeof claims.email === "string" ? claims.email : null;
  const name = typeof profile.full_name === "string" && profile.full_name.trim() ? profile.full_name.trim() : (email ?? "Signed-in user");
  return {
    userId: `usr_${claims.sub.replaceAll("-", "")}`,
    email,
    name: name.slice(0, 80),
    tenantId: tenant,
    role,
    demo: false,
  };
});

/** A session that may act on a workspace: signed in, assigned a workspace and a role. */
export async function getWorkspaceSession(): Promise<(Session & { tenantId: string; role: Role }) | null> {
  const session = await getSession();
  return session && session.tenantId && session.role ? (session as Session & { tenantId: string; role: Role }) : null;
}
