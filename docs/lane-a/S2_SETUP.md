# S2: shared accounts and secrets (checklist for Asharib)

**Done when:** all four of us can deploy and call the API without sharing keys in chat.

Claude sessions never create accounts or handle secrets (checkpoint C4). You do the clicking; the scripts check the result **without printing any value**. If a key is ever pasted into a chat, issue or PR, rotate it the same day (`docs/lane-a/KEY_ROTATION.md`).

Generate random internal secrets on your own machine, never in chat:
```sh
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

## 1. Password vault (do this first)
- [ ] Create a shared vault (Bitwarden free organisation or 1Password) named **Fiona** and invite Abdullah, Daniyal and Yahya.
- [ ] One entry per secret in the table at the bottom, each with an **owner** who rotates it.

## 2. GitHub
- [ ] Create a **private** repository `fiona` (it goes public for the submission, PLAN.md §8). Then from `Y:\Fiona`:
  `git remote add origin https://github.com/<you>/fiona.git` and `git push -u origin main`.
- [ ] Invite the three teammates as collaborators.
- [ ] Replace the placeholder handles in `.github/CODEOWNERS` (`@asharib-gh`, `@daniyal-gh`, `@yahya-gh`, `@abdullah-gh`) with real usernames.
- [ ] Settings → Branches → rule for `main`: **block force pushes** and **block deletion**. Do *not* require pull requests: we commit trunk-based from one shared working tree (PLAN.md §4), and CI runs on every push.
- [ ] Settings → Secrets and variables → Actions: add **`FLY_API_TOKEN`** only (step 5). CI needs no other secret.
- [ ] Verify: the **ci** workflow runs green on the push (Actions tab).

## 3. Supabase (free tier)
- [ ] New project `fiona`, region **Southeast Asia (Singapore)**. Keep the database password in the vault.
- [ ] Database → Extensions: enable **vector** (pgvector).
- [ ] Project Settings → API: copy the **Project URL**, the **anon / publishable key** and the **service_role / secret key** into the vault.
- [ ] Project Settings → Database → Connection string (session pooler): store it as `DATABASE_URL` in the vault (engine only).
- [ ] Verify: `pnpm smoke:keys` shows `OK  auth health  HTTP 200`.

## 4. Vercel (the Window)
- [ ] Import the GitHub repo. **Root Directory:** `apps/web`. Framework: Next.js (pnpm is detected from the lockfile).
- [ ] Settings → Git → **Ignored Build Step:** `npx turbo-ignore --fallback=HEAD^1`.
- [ ] Environment variables. **Preview:** `NEXT_PUBLIC_API_MODE=mock`. **Production:** also `mock` until A8 switches the demo build to `live`.
- [ ] Verify: open the preview URL; it shows "The Window" with a **Mock data** chip, and `/api/healthz` returns `{"api_version":"v1","status":"ok","service":"web","mode":"mock"}`.

## 5. Fly.io (engine, agents, Guardian)
- [ ] Install flyctl (`pnpm doctor` prints the command), then run `fly auth login`.
- [ ] Create the three apps: `fly apps create fiona-engine`, `fly apps create fiona-agents`, `fly apps create fiona-guardian`.
- [ ] Deploy token for CI: `fly tokens create org`, then save it in the vault and as the GitHub secret `FLY_API_TOKEN`.
- [ ] Set each app's secrets **in your own terminal** (values come from the vault; never paste them anywhere else):
  - `fly secrets set -a fiona-engine DATABASE_URL=… SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… INTERNAL_JWT_SECRET=… AGENTS_SERVICE_TOKEN=… GUARDIAN_INBOUND_TOKEN=…`
  - `fly secrets set -a fiona-agents ANTHROPIC_API_KEY=… INTERNAL_JWT_SECRET=… AGENTS_SERVICE_TOKEN=… LLM_RUN_BUDGET_USD=… LLM_DAILY_BUDGET_USD=…`
  - `fly secrets set -a fiona-guardian GUARDIAN_ANTHROPIC_API_KEY=… INTERNAL_JWT_SECRET=… GUARDIAN_INBOUND_TOKEN=… LLM_RUN_BUDGET_USD=… LLM_DAILY_BUDGET_USD=…`
- [ ] First deploy: GitHub → Actions → **deploy-services** → Run workflow (or locally: `fly deploy --config services/engine/fly.toml --dockerfile services/engine/Dockerfile .` from the repo root).
- [ ] Verify: `curl https://fiona-engine.fly.dev/healthz` returns `{"api_version":"v1","status":"ok","service":"engine"}` (G2 needs the engine deployed).

## 6. Anthropic Console (D-001: one capped workspace, two keys)
- [ ] Create a workspace **Fiona** and set a **monthly spend limit**. Suggested: $100 for the build; you decide (checkpoint C5).
- [ ] Create two API keys in that workspace: **fiona-agents** → `ANTHROPIC_API_KEY`, and **fiona-guardian** → `GUARDIAN_ANTHROPIC_API_KEY`. Both go in the vault.
- [ ] Suggested runtime ceilings (C5): `LLM_RUN_BUDGET_USD=0.50` and `LLM_DAILY_BUDGET_USD=10`.

## 7. Local machine (each teammate)
- [ ] `corepack enable`, `pnpm install`, then `cp .env.example .env.local` and fill in only what you need from the vault.
- [ ] `pnpm doctor`: a table of tools and variables, with no values printed. Live mode needs every `required: live` variable.
- [ ] `pnpm smoke:keys`: free check that each key can see its model and that Supabase answers.
- [ ] After the C5 spend cap is agreed: `pnpm smoke:keys --complete` sends one 16-token message per model.

## Where each secret lives

| Secret | Vault | Local `.env.local` | Deployed in | Owner |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✓ | agents work only | Fly `fiona-agents` | Asharib |
| `GUARDIAN_ANTHROPIC_API_KEY` | ✓ | Guardian work only | Fly `fiona-guardian` | Asharib |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | engine work only | Fly `fiona-engine` | Daniyal |
| `DATABASE_URL` (cloud) | ✓ | not needed (portable Postgres) | Fly `fiona-engine` | Daniyal |
| `INTERNAL_JWT_SECRET` | ✓ | live mode only | Vercel + all three Fly apps | Asharib |
| `AGENTS_SERVICE_TOKEN` | ✓ | live mode only | Fly `fiona-agents`, `fiona-engine` | Asharib |
| `GUARDIAN_INBOUND_TOKEN` | ✓ | live mode only | Fly `fiona-engine`, `fiona-guardian` | Asharib |
| `FLY_API_TOKEN` | ✓ | no | GitHub Actions secret | Asharib |
| `DEMO_PRESENTER_KEY` | ✓ | no | Vercel (demo only, A8) | Asharib |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✓ (public by design) | live mode | Vercel | Daniyal |
