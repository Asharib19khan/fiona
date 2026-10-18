import { randomBytes } from "node:crypto";
import { isSuperAdmin } from "@/lib/session";
import { supabaseServer } from "@/lib/supabase/server";

/**
 * Server-only account administration through Supabase Auth's Admin API. Accounts live in the
 * Supabase project's database (auth.users); workspace and role live in app_metadata, which
 * only this admin key can write. The key (SUPABASE_SERVICE_ROLE_KEY) never leaves the server.
 *
 * Rules: only the super admin calls these; nobody can be made super admin here (that is set
 * once, outside the app); the super admin's own account cannot be edited or disabled here.
 */

export type WorkspaceRole = "owner" | "finance";

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  tenantId: string | null;
  role: WorkspaceRole | null;
  superAdmin: boolean;
  disabled: boolean;
  createdAt: string;
  lastSignInAt: string | null;
}

export class AdminError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

const TENANT = /^ten_[a-z0-9_]{1,60}$/;
const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$/;

function adminKey(): { base: string; key: string } {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!base || !key) throw new AdminError(503, "admin_not_configured", "Account administration is not configured on this server.");
  return { base, key };
}

async function supabaseAdmin(method: string, route: string, body?: unknown): Promise<Record<string, unknown>> {
  const { base, key } = adminKey();
  const res = await fetch(`${base}/auth/v1/admin/${route}`, {
    method,
    headers: { apikey: key, Authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: body === undefined ? null : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const message = String(data.msg ?? data.message ?? data.error_description ?? "Supabase refused the request.");
    throw new AdminError(res.status === 422 ? 422 : 502, "supabase_error", message);
  }
  return data;
}

/**
 * The caller must be the super admin, checked against Supabase now (getUser), not against the
 * token alone, so a revoked flag or a disabled account takes effect at once.
 */
export async function requireSuperAdmin(): Promise<{ id: string; email: string }> {
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getUser();
  const user = data?.user;
  if (error || !user?.email) throw new AdminError(401, "not_signed_in", "Sign in first.");
  if (!isSuperAdmin((user.app_metadata ?? {}) as Record<string, unknown>, user.email)) {
    throw new AdminError(403, "super_admin_only", "Only the super admin can manage accounts.");
  }
  return { id: user.id, email: user.email };
}

function shape(raw: Record<string, unknown>): AdminUser {
  const app = (raw.app_metadata ?? {}) as Record<string, unknown>;
  const profile = (raw.user_metadata ?? {}) as Record<string, unknown>;
  const email = String(raw.email ?? "");
  const banned = typeof raw.banned_until === "string" && new Date(raw.banned_until).getTime() > Date.now();
  return {
    id: String(raw.id),
    email,
    name: typeof profile.full_name === "string" ? profile.full_name : email,
    tenantId: typeof app.tenant_id === "string" ? app.tenant_id : null,
    role: app.role === "owner" || app.role === "finance" ? app.role : null,
    superAdmin: isSuperAdmin(app, email),
    disabled: banned,
    createdAt: String(raw.created_at ?? ""),
    lastSignInAt: typeof raw.last_sign_in_at === "string" ? raw.last_sign_in_at : null,
  };
}

export async function listUsers(): Promise<AdminUser[]> {
  const data = await supabaseAdmin("GET", "users?page=1&per_page=1000");
  const users = Array.isArray(data.users) ? (data.users as Record<string, unknown>[]) : [];
  return users.map(shape).sort((a, b) => a.email.localeCompare(b.email));
}

function temporaryPassword(): string {
  return `Fiona-${randomBytes(12).toString("base64url")}`;
}

function validate(input: { tenantId?: unknown; role?: unknown; name?: unknown }) {
  if (input.tenantId !== undefined && (typeof input.tenantId !== "string" || !TENANT.test(input.tenantId))) {
    throw new AdminError(422, "invalid_workspace", "The workspace must look like ten_<name>.");
  }
  if (input.role !== undefined && input.role !== "owner" && input.role !== "finance") {
    throw new AdminError(422, "invalid_role", "The role must be owner or finance.");
  }
  if (input.name !== undefined && (typeof input.name !== "string" || input.name.trim().length < 2 || input.name.length > 80)) {
    throw new AdminError(422, "invalid_name", "The name must be 2 to 80 characters.");
  }
}

/** Creates an account and returns it with a one-time temporary password to hand over. */
export async function createUser(input: { email: string; name: string; tenantId: string; role: WorkspaceRole }): Promise<{ user: AdminUser; temporaryPassword: string }> {
  const email = input.email.trim().toLowerCase();
  if (!EMAIL.test(email)) throw new AdminError(422, "invalid_email", "Enter a valid email address.");
  if (email === process.env.SUPER_ADMIN_EMAIL?.trim().toLowerCase()) {
    throw new AdminError(403, "reserved", "That address belongs to the super admin account.");
  }
  validate(input);
  const password = temporaryPassword();
  const created = await supabaseAdmin("POST", "users", {
    email,
    password,
    email_confirm: true,
    app_metadata: { tenant_id: input.tenantId, role: input.role },
    user_metadata: { full_name: input.name.trim() },
  });
  return { user: shape(created), temporaryPassword: password };
}

async function editable(id: string): Promise<AdminUser> {
  if (!/^[0-9a-f-]{36}$/.test(id)) throw new AdminError(404, "not_found", "No such account.");
  const user = shape(await supabaseAdmin("GET", `users/${id}`));
  if (user.superAdmin) throw new AdminError(403, "protected", "The super admin account cannot be changed here.");
  return user;
}

export async function updateUser(
  id: string,
  change: { name?: string; tenantId?: string; role?: WorkspaceRole; disabled?: boolean; resetPassword?: boolean },
): Promise<{ user: AdminUser; temporaryPassword?: string }> {
  const current = await editable(id);
  validate(change);
  const body: Record<string, unknown> = {};
  if (change.tenantId !== undefined || change.role !== undefined) {
    body.app_metadata = { tenant_id: change.tenantId ?? current.tenantId, role: change.role ?? current.role, super_admin: false };
  }
  if (change.name !== undefined) body.user_metadata = { full_name: change.name.trim() };
  // Disabling bans sign-in (about 100 years); re-enabling lifts it. Existing tokens expire within the hour.
  if (change.disabled !== undefined) body.ban_duration = change.disabled ? "876000h" : "none";
  let password: string | undefined;
  if (change.resetPassword) {
    password = temporaryPassword();
    body.password = password;
  }
  const updated = await supabaseAdmin("PUT", `users/${id}`, body);
  return password ? { user: shape(updated), temporaryPassword: password } : { user: shape(updated) };
}

export async function deleteUser(id: string): Promise<void> {
  await editable(id);
  await supabaseAdmin("DELETE", `users/${id}`);
}
