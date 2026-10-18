import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/** True when this deployment signs people in with Supabase Auth. */
export function authConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

/**
 * Supabase client for Server Components, route handlers and server actions, bound to the
 * request's cookies. Server Components cannot write cookies; the proxy refreshes the session
 * there, so a failed write here is safe to ignore.
 */
export async function supabaseServer() {
  const store = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (toSet) => {
        try {
          for (const { name, value, options } of toSet) store.set(name, value, options);
        } catch {
          // Called from a Server Component: the proxy keeps the session fresh instead.
        }
      },
    },
  });
}
