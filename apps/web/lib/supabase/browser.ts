"use client";

import { createBrowserClient } from "@supabase/ssr";

/** Supabase client for the sign-in form and sign-out. Only the public (publishable) key is used. */
export function supabaseBrowser() {
  return createBrowserClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!);
}
