#!/usr/bin/env node
// One-time setup for a fresh clone: writes .env.local for the real (live) product.
// Usage: node scripts/setup-live.mjs <supabase-publishable-key>
// The publishable (anon) key is public by design; copy it from Supabase > Settings > API Keys.
// Internal secrets are generated fresh on this machine; nothing secret lives in the repo.
import { randomBytes } from "node:crypto";
import { existsSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const target = resolve(import.meta.dirname, "..", ".env.local");
const anonKey = process.argv[2];

if (!anonKey) {
  console.error("Usage: node scripts/setup-live.mjs <supabase-publishable-key>");
  console.error("Find it in Supabase > Settings > API Keys (publishable / anon key).");
  process.exit(1);
}
if (existsSync(target) && !process.argv.includes("--force")) {
  console.error(".env.local already exists. Re-run with --force to replace it.");
  process.exit(1);
}

const secret = () => randomBytes(32).toString("base64url");

const env = `# Written by scripts/setup-live.mjs. Never commit this file.
NEXT_PUBLIC_API_MODE=live
FIONA_MODE=live
# The demo business's data runs to 22 Oct 2026; pin the engine clock to it.
FIONA_NOW=2026-10-22T09:00:00Z
FIONA_LLM_PROVIDER=claude_cli
DEMO_TENANT_ID=ten_karachi_apparel
LLM_RUN_BUDGET_USD=2
NEXT_PUBLIC_SUPABASE_URL=https://aiyzwlzbmzzxsvpifvoi.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=${anonKey}
INTERNAL_JWT_SECRET=${secret()}
GUARDIAN_INBOUND_TOKEN=${secret()}
SETTINGS_ENCRYPTION_KEY=${secret()}
# Optional, only for the admin portal (creating accounts). Paste the Supabase secret key here.
SUPABASE_SERVICE_ROLE_KEY=
SUPER_ADMIN_EMAIL=
`;

writeFileSync(target, env);
console.log("Wrote .env.local (live mode).");
console.log("Next: pnpm install, pnpm db:reset, pnpm demo-data, then pnpm dev and open http://localhost:3000");
