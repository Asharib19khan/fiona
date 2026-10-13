## What and why

<!-- Task ID and one or two sentences. Title starts with the task ID, e.g. "A3: agent rail". -->

## How I verified it

<!-- Commands you ran and the key output line. "Works" means you ran it (R20). -->

## Definition of done

- [ ] Runs from a clean clone (`pnpm install`, then the task's command)
- [ ] Has a test that would fail if the feature were removed
- [ ] Lint, typecheck and tests are green; no secrets in the diff; `.env.example` is current (`pnpm gen:env`)
- [ ] Touches only my lane's folders (CODEOWNERS)
- [ ] `docs/status/<lane>.md` updated

## Contract change?

- [ ] No change to `packages/contracts`
- [ ] Additive change: fiona-19 and fiona-b7 acknowledged, and it is logged in `docs/decision-log.md`
- [ ] Breaking change: signed off by Asharib **and** Daniyal, logged, approved by fiona-b7
