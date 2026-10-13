# packages/ui

**Owner:** Asharib (fiona-19).

Design tokens, primitives, domain components (MoneyText, TimeText, OutcomeBadge, FindingCard, VerdictPanel …) and the **screen kit** every lane uses for its workbench screens: page layout, table, chart, Figure-with-explain, and loading, empty, error and success states. Built in task A3.

May import `@fiona/contracts` and React. Never imports from `apps/*` or `services/*` (R1, enforced by ESLint; see `test/boundaries.test.ts`).
