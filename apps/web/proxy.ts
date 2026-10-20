import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/safe-next";
import { mfaState } from "@/lib/supabase/mfa";

/**
 * Next.js 16 proxy (formerly middleware): refreshes the Supabase session on every request and
 * sends anyone who is not signed in, or who still owes their two-step code, to /login. API
 * routes answer 401 themselves, so they are not redirected. Without Supabase Auth configured (local mock mode) it does nothing.
 */
export async function proxy(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return NextResponse.next({ request });

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        for (const { name, value } of toSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of toSet) response.cookies.set(name, value, options);
      },
    },
  });

  // Verifies the token's signature and refreshes it when needed. Nothing may run between
  // creating the client and this call, or sessions can end at random.
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;
  const signedIn = Boolean(claims?.sub);
  const path = request.nextUrl.pathname;
  // Public: the sign-in page, the legal documents, email links (password reset) and APIs (they answer 401 themselves).
  const open = path === "/login" || path === "/legal" || path.startsWith("/legal/") || path.startsWith("/auth/") || path.startsWith("/api/");

  // Redirects keep any refreshed session cookies.
  const redirectTo = (pathname: string, next?: string) => {
    const target = request.nextUrl.clone();
    target.pathname = pathname;
    target.search = next && next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
    const redirect = NextResponse.redirect(target);
    for (const cookie of response.cookies.getAll()) redirect.cookies.set(cookie);
    return redirect;
  };

  if (!signedIn) return open ? response : redirectTo("/login", path);
  if (path.startsWith("/api/") || path.startsWith("/auth/")) return response;

  // Signed in with a password, but two-step verification still owed: only the code step is open.
  const mfaRequired = (await mfaState(supabase, claims?.aal)) === "required";
  if (mfaRequired) return path === "/login" ? response : redirectTo("/login", path + request.nextUrl.search);
  if (path === "/login") return redirectTo(safeNext(request.nextUrl.searchParams.get("next")));
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|manifest.webmanifest|.*\\.(?:png|jpg|jpeg|svg|webp|ico)$).*)"],
};
