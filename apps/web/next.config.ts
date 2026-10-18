import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// D-011: one local env file for the whole repo. Load the root .env.local before Next reads its own.
// forceReload: Next has already loaded (and cached) this app folder's env files by now, so a
// plain call would return that cache and never read the root file.
loadEnvConfig(path.resolve(process.cwd(), "../.."), process.env.NODE_ENV !== "production", console, true);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Workspace packages ship TypeScript source; Next compiles them.
  transpilePackages: ["@fiona/contracts", "@fiona/ui"],
  // The proxy bundle does not see the root .env.local loaded above, so the two public Supabase
  // values are inlined explicitly (both are public by design; no secret goes here).
  env: {
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  },
};

export default nextConfig;
