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
  // Browser-side protections on every response. No other site may frame Fiona (an approval
  // button can't be clickjacked), files are never type-sniffed, links don't leak paths, and
  // forms and <base> stay on this site. script-src is left to Next's defaults so nothing breaks.
  async headers() {
    const security = [
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    ];
    if (process.env.NODE_ENV === "production") {
      security.push({ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" });
    }
    return [{ source: "/:path*", headers: security }];
  },
};

export default nextConfig;
