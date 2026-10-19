import { cache } from "react";
import { apiMode } from "@/lib/env";
import { mfaState } from "@/lib/supabase/mfa";
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
  /** The one super admin: flagged in app_metadata AND the email named in SUPER_ADMIN_EMAIL. */
  superAdmin: boolean;
}

const TENANT = /^ten_[a-z0-9_]{1,60}$/;

/**
 * The no-sign-in stand-in exists for a developer's own machine only. A hosted deployment that
 * is missing its Supabase settings must refuse everyone, not hand out an owner session.
 */
export function localDemoAllowed(): boolean {
  if (apiMode() !== "mock") return false;
  if (process.env.VERCEL || process.env.FLY_APP_NAME || process.env.FIONA_MODE === "live") return false;
  return true;
}

function demoSession(): Session {
  const tenant = process.env.DEMO_TENANT_ID ?? "ten_karachi_apparel";
  return {
    userId: process.env.DEMO_USER_ID ?? "usr_owner_demo",
    email: null,
    name: "Local developer",
    tenantId: TENANT.test(tenant) ? tenant : null,
    role: "owner",
    demo: true,
    superAdmin: false,
  };
}

/**
 * Who is signed in, from a verified token. `getClaims()` checks the token's signature on every
 * call; the cookie alone is never trusted (it can be forged). Workspace and role come only from
 * `app_metadata`, which users cannot edit; `user_metadata` is used for the display name only.
 *
 * A person who has turned on two-step verification is not signed in until this session has
 * used their authenticator (token at aal2); until then this returns null, so every API refuses.
 *
 * Without Supabase Auth configured, local mock mode uses a labelled stand-in; live mode refuses.
 */
export const getSession = cache(async (): Promise<Session | null> => {
  if (!authConfigured()) return localDemoAllowed() ? demoSession() : null;
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (error || !claims?.sub) return null;
  if ((await mfaState(supabase, claims.aal)) === "required") return null;
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
    superAdmin: isSuperAdmin(app, email),
  };
});

/**
 * Super admin needs both: the `super_admin` flag, which only the admin key can write, and the
 * exact address in the server-only SUPER_ADMIN_EMAIL. Either alone is not enough, so a copied
 * flag or a look-alike account never qualifies.
 */
export function isSuperAdmin(app: Record<string, unknown>, email: string | null): boolean {
  const configured = process.env.SUPER_ADMIN_EMAIL?.trim().toLowerCase();
  return Boolean(configured && email && app.super_admin === true && email.toLowerCase() === configured);
}

/** A session that may act on a workspace: signed in, assigned a workspace and a role. */
export async function getWorkspaceSession(): Promise<(Session & { tenantId: string; role: Role }) | null> {
  const session = await getSession();
  return session && session.tenantId && session.role ? (session as Session & { tenantId: string; role: Role }) : null;
}

/** Where sign-in stands: signed out, password done but the authenticator code still owed, or signed in. */
export const getAuthStage = cache(async (): Promise<"signed_out" | "mfa_required" | "signed_in"> => {
  if (!authConfigured()) return localDemoAllowed() ? "signed_in" : "signed_out";
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims?.sub) return "signed_out";
  return (await mfaState(supabase, data.claims.aal)) === "required" ? "mfa_required" : "signed_in";
});
