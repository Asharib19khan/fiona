# Key rotation runbook

**Rule:** if a secret leaks (pasted into chat, committed, shown in a screenshot or recording, or seen in a log), rotate it **the same day**, before anything else. Then tell fiona-b7 and add a line to the log at the bottom.

Never paste the new value anywhere except the vault and the target's own secret store. After rotating, run `pnpm doctor` and `pnpm smoke:keys` locally and check `/healthz` on each deployed service.

| Secret | Rotate at | Then update | Commands |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console → Fiona workspace → API keys: create the new key, **then delete the leaked one** | vault; Fly `fiona-agents`; your `.env.local` | `fly secrets set -a fiona-agents ANTHROPIC_API_KEY=…` |
| `GUARDIAN_ANTHROPIC_API_KEY` | same, key "fiona-guardian" | vault; Fly `fiona-guardian` | `fly secrets set -a fiona-guardian GUARDIAN_ANTHROPIC_API_KEY=…` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → roll the secret / service_role key | vault; Fly `fiona-engine` | `fly secrets set -a fiona-engine SUPABASE_SERVICE_ROLE_KEY=…` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → API keys → roll (public, so only on abuse) | vault; Vercel (then **redeploy**: the value is inlined at build time) | `vercel env rm NEXT_PUBLIC_SUPABASE_ANON_KEY production` then `vercel env add …`, or the dashboard |
| Database password / `DATABASE_URL` | Supabase → Database → reset password | vault; Fly `fiona-engine` | `fly secrets set -a fiona-engine DATABASE_URL=…` |
| `INTERNAL_JWT_SECRET` | generate a new one (`node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`) | vault; Vercel; all three Fly apps, **together** (tokens signed with the old secret stop working) | `fly secrets set -a <app> INTERNAL_JWT_SECRET=…` ×3; Vercel env + redeploy |
| `AGENTS_SERVICE_TOKEN` | generate | vault; Fly `fiona-agents` and `fiona-engine` together | `fly secrets set -a fiona-agents …` and `-a fiona-engine …` |
| `GUARDIAN_INBOUND_TOKEN` | generate | vault; Fly `fiona-engine` and `fiona-guardian` together | `fly secrets set -a fiona-engine …` and `-a fiona-guardian …` |
| `FLY_API_TOKEN` | `fly tokens list`, then `fly tokens revoke <id>`, then `fly tokens create org` | vault; GitHub Actions secret | GitHub → Settings → Secrets → Actions |
| `DEMO_PRESENTER_KEY` | generate | vault; Vercel | Vercel env + redeploy |

`fly secrets set` restarts the app's machines, so the new value is live within about a minute.

## If a secret was committed
1. Rotate it first (table above). Rewriting history does not un-leak a pushed secret.
2. Remove it from the working tree and commit the removal (`<TaskID>: remove leaked value`).
3. Do **not** rewrite shared history on your own (checkpoint C8/C9). Ask Asharib.
4. Make sure the pre-commit hook is active: `git config core.hooksPath` should print `.githooks`, and `gitleaks version` should run.

## Log
| Date | Secret | Why | Rotated by |
|---|---|---|---|
