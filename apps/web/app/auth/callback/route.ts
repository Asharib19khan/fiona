import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/safe-next";
import { supabaseServer } from "@/lib/supabase/server";

const EMAIL_TYPES = new Set<EmailOtpType>(["recovery", "email", "invite", "magiclink", "signup", "email_change"]);

/**
 * Where email links land (password reset). Supabase sends either a one-time `code` (PKCE, same
 * browser that asked) or a `token_hash` (when the email template links here directly). Either is
 * exchanged for a session, then the person goes on to `next`. A bad or used link goes back to
 * /login with a note. The session this creates is still subject to two-step verification.
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const code = params.get("code");
  const tokenHash = params.get("token_hash");
  const type = params.get("type") as EmailOtpType | null;
  const supabase = await supabaseServer();

  let ok = false;
  if (code) {
    ok = !(await supabase.auth.exchangeCodeForSession(code)).error;
  } else if (tokenHash && type && EMAIL_TYPES.has(type)) {
    ok = !(await supabase.auth.verifyOtp({ type, token_hash: tokenHash })).error;
  }

  const target = request.nextUrl.clone();
  target.search = "";
  if (ok) {
    const next = new URL(safeNext(params.get("next")), request.nextUrl.origin);
    target.pathname = next.pathname;
    target.search = next.search;
  } else {
    target.pathname = "/login";
    target.searchParams.set("error", "link");
  }
  return NextResponse.redirect(target);
}
