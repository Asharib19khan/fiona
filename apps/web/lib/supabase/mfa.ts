import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Two-step verification state for a signed-in session.
 * - `verified`: the session already passed a second factor (token says aal2).
 * - `not_enrolled`: the person has no verified authenticator; a password is enough.
 * - `required`: the person has an authenticator but this session has not used it yet.
 */
export type MfaState = "verified" | "not_enrolled" | "required";

/**
 * `aal` must come from a verified token (getClaims), never from the cookie's user object,
 * which the browser can edit. Whether the person has an authenticator is asked of Supabase
 * (getUser), for the same reason. Any failure counts as `required`: fail closed.
 */
export async function mfaState(supabase: { auth: Pick<SupabaseClient["auth"], "getUser"> }, aal: unknown): Promise<MfaState> {
  if (aal === "aal2") return "verified";
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return "required";
  return (data.user.factors ?? []).some((factor) => factor.status === "verified") ? "required" : "not_enrolled";
}
