# apps/web: the Window

**Owner:** Asharib (fiona-19). Domain workbench screens under `app/(app)/<route>/` belong to the lane named in `docs/orchestrator/PLAN.md` §1.

A Next.js 16 console onto the Fiona service: it shows and asks, and the service decides. No finance logic runs in the browser.

- Import workspace code only from `@fiona/contracts` and `@fiona/ui` (R1, enforced by ESLint; see `test/boundaries.test.ts`).
- Live mode reaches services only through route handlers under `/api/fiona/*` (the BFF, D-005).
- `NEXT_PUBLIC_API_MODE=mock|live` (default `mock`) is inlined at build time.

```sh
pnpm --filter @fiona/web dev        # http://localhost:3000, health at /api/healthz
pnpm --filter @fiona/web test
```
