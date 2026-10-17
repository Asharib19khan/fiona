ID: CX-A3
Task: Window shell and Tier 1 experience integration
Status: In progress
Due: 2026-10-18
Updated: 2026-10-16
Note: Completed local Window coverage for cash/analysis/financing, bills, reconciliation, import, audit, approvals, mandates, and council views; added safe degraded fallbacks for financing and bills, fixed JSX key/download-link lint errors, and made proposal intake validate the complete generated `ProposalDraft` contract before forwarding. Vitest uses its runner config loader on Windows; engine pytest uses an isolated ignored temp base; env coverage skips generated pytest temp folders. Verification: `pnpm test` passes all 6 Turbo tasks (380 passed, 1 skipped); web lint, typecheck, and production build pass. Root `pnpm lint`, `pnpm typecheck`, `pnpm build`, `pnpm test:boundaries`, and `pnpm check:env-coverage` passed in the prior full verification. The gitleaks self-test skips because gitleaks is not installed. Remaining Tier 1 work: persistent proposal/decision API and verified owner sessions, live BFF session routing, bill extraction and Controller/Treasurer runtime, Guardian-to-engine review integration, owner decision to guarded wallet flow, deployed live link/credentials, finance QA, and final video/submission. D4 pass-4 intake mapping and Y10's approved EBITDA input also remain open.

ID: CX-Y8
Task: Payment-timing optimiser
Status: Done
Due: 2026-10-14
Updated: 2026-10-14
Note: Implemented services/engine/decisions/payment_timing.py and tests. Verification: uv run pytest decisions/tests/test_payment_timing.py -q -> 8 passed in 0.61s; uv run pytest decisions -q -> 22 passed in 0.67s; uv run ruff check decisions -> All checks passed; uv run ruff format decisions/payment_timing.py decisions/tests/test_payment_timing.py -> clean after formatting. Earlier full-suite verification before unrelated wallet files appeared: uv run pytest -q --basetemp <temp> -> 236 passed, 1 warning in 12.46s. Current full-suite rerun: uv run pytest -q --basetemp <temp> stops during collection in untracked wallet/tests/test_audit.py with TypeError: text() got an unexpected keyword argument 'characters'. Questions: none. Note: a first full pytest run reached 100% but exited during Windows temp cleanup with PermissionError on pytest-current, so full runs used an isolated temp base.

ID: CX-Y3
Task: Inventory analytics engine
Status: Done
Due: 2026-10-19
Updated: 2026-10-15
Note: Replaced the inventory analysis mock for fixture-backed tenants with a deterministic engine. Verification: uv run pytest forecast/inventory/tests/test_inventory.py -q -> 12 passed, 1 warning; uv run pytest forecast -q --basetemp <temp> -> 110 passed, 1 warning in 26.41s; uv run pytest -q --basetemp <temp> -> 301 passed, 1 skipped, 1 warning in 254.12s; uv run ruff check forecast -> All checks passed; uv run ruff format forecast/inventory/engine.py forecast/inventory/loader.py forecast/inventory/tests/test_inventory.py -> 4 files left unchanged. Assumptions (origin=assumption): analysis_window_days=90, cover_target_days=60, fast_below_days_of_cover=21, reorder_cover_days=30, xyz_min_weeks=4, safety_stock_factor=1.2816, ABC basis=revenue. Seed tenant ten_karachi_apparel (as_of 2026-10-22), top 3 findings by cash tied up: LWN-OS-IVR, slow, PKR 4,859,733.33 (485,973,333 minor); LWN-OS-OLV, slow, PKR 4,834,133.33 (483,413,333 minor); LWN-OS-SKY, slow, PKR 4,795,733.33 (479,573,333 minor). Questions: none.
