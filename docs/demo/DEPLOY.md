# Deploying Fiona (Supabase + Fly + Vercel)

The database is already done: the hosted Supabase project has every migration (17 tables, RLS forced, no
`anon`/`authenticated` grants) and the full demo dataset (193 MB). This page covers the other two.

Copy secret values from `Y:\Fiona\.env.local`. Never paste them into chat, docs or `fly.toml`.

## 1. Fly: three apps, in this order

Install the CLI and sign in: `iwr https://fly.io/install.ps1 -useb | iex`, then `fly auth login`.
Run everything from the repo root (`Y:\Fiona`). Fly builds the images on its own servers, so Docker is not needed.

If an app name is taken, pick another (e.g. `fiona-engine-ak`), change `app =` in that `fly.toml`, and change
the matching `https://….fly.dev` URLs in the other two `fly.toml` files and in Vercel.

### Engine

```powershell
fly apps create fiona-engine
fly secrets set --app fiona-engine DATABASE_URL="<SUPABASE_DB_URL from .env.local>" INTERNAL_JWT_SECRET="<from .env.local>" GUARDIAN_INBOUND_TOKEN="<from .env.local>"
fly deploy --config services/engine/fly.toml --dockerfile services/engine/Dockerfile .
```

### Guardian

```powershell
fly apps create fiona-guardian
fly secrets set --app fiona-guardian INTERNAL_JWT_SECRET="<same>" GUARDIAN_INBOUND_TOKEN="<same>" ANTHROPIC_API_KEY="<Guardian key>"
fly deploy --config services/guardian/fly.toml --dockerfile services/guardian/Dockerfile .
```

### Agents

```powershell
fly apps create fiona-agents
fly secrets set --app fiona-agents INTERNAL_JWT_SECRET="<same>" ANTHROPIC_API_KEY="<agents key>" LLM_RUN_BUDGET_USD="2"
fly deploy --config services/agents/fly.toml --dockerfile services/agents/Dockerfile .
```

**Claude keys.** Locally the agents use your Claude login. On Fly they need an API key from
console.anthropic.com → **API Keys** → **Create Key**. Make two keys (one for `fiona-agents`, one for
`fiona-guardian`) so the Guardian never shares the agents' key. `LLM_RUN_BUDGET_USD` caps each run.

**Check:** each of these returns `{"status":"ok", ...}`:
`https://fiona-engine.fly.dev/healthz`, `https://fiona-guardian.fly.dev/healthz`, `https://fiona-agents.fly.dev/healthz`.

## 2. Vercel: the web app

1. vercel.com → **Add New… → Project** → import `Asharib19khan/fiona`.
2. **Root Directory:** `apps/web` (Vercel detects Next.js and pnpm). Leave build settings as they are.
3. **Environment Variables**, before the first deploy:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_MODE` | `live` |
| `NEXT_PUBLIC_SUPABASE_URL` | from `.env.local` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | from `.env.local` (the `sb_publishable_…` key) |
| `SUPABASE_SERVICE_ROLE_KEY` | from `.env.local` (secret, server only) |
| `SUPER_ADMIN_EMAIL` | from `.env.local` |
| `INTERNAL_JWT_SECRET` | from `.env.local` (same value as on Fly) |
| `ENGINE_BASE_URL` | `https://fiona-engine.fly.dev` |
| `AGENTS_BASE_URL` | `https://fiona-agents.fly.dev` |
| `FIONA_NOW` | `2026-10-22T09:00:00Z` |
| `DEMO_TENANT_ID` | `ten_karachi_apparel` |

4. **Deploy.** Note the address it gives you (e.g. `fiona-xyz.vercel.app`).
5. Add two more variables with that address and redeploy: `WEBAUTHN_RP_ID` = `fiona-xyz.vercel.app`,
   `WEBAUTHN_ORIGIN` = `https://fiona-xyz.vercel.app`.

## 3. Supabase: allow sign-in from the new address

Dashboard → **Authentication → URL Configuration**:
- **Site URL:** `https://fiona-xyz.vercel.app`
- **Redirect URLs:** add `https://fiona-xyz.vercel.app/**`

## 4. Smoke test (5 minutes)

1. Open the Vercel address, sign in as the super admin.
2. Briefing loads with figures; Bills shows 241 bills; Approvals opens.
3. Upload a bill with a fresh bill number, then "Record the bill and ask the Treasurer". The Guardian verdict appears.
4. Approve it, then "Send approved payments due today". The proposal page shows the payment, journal and audit trail.

## 5. After the demo is live

Reset the Supabase database password and create a new secret key (they appeared in a local session log),
then update `DATABASE_URL` on `fiona-engine` and `SUPABASE_SERVICE_ROLE_KEY` on Vercel.
