import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// D-011: one local env file for the whole repo. Load the root .env.local before Next reads its own.
loadEnvConfig(path.resolve(process.cwd(), "../.."), process.env.NODE_ENV !== "production");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Workspace packages ship TypeScript source; Next compiles them.
  transpilePackages: ["@fiona/contracts", "@fiona/ui"],
};

export default nextConfig;
