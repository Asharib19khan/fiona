# Fiona: 5-minute live demo

For whoever presents Fiona live. Everything below was run end to end on 18 Oct 2026 in live (local) mode.

## Before you start (10 minutes ahead)

1. `.env.local` has `NEXT_PUBLIC_API_MODE=live`, `FIONA_MODE=live`, `FIONA_LLM_PROVIDER=claude_cli` and `FIONA_NOW=2026-10-22T09:00:00Z`. Claude Code is logged in.
2. `pnpm dev`, wait for all four services, then open these pages once so they are warm: Briefing, Approvals, Bills, Cash forecast, Financial analysis (the slowest, ~7 s).
3. Sign in as the demo owner. Close other tabs. Zoom the browser to 110%.
4. Have both files from [`bills/`](bills/) ready in a folder: the clean bill (LSH-2310) and the injection bill (LSH-2311).
5. If you have demoed already today, upload bills with a number not yet in the ledger (edit the number in a copy of the file), or the Guardian will correctly flag a duplicate (G-05).

## The script

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Briefing | Point at the three chips at the top. | "This is Karachi Apparel, a synthetic garment business. Everything you see is computed from its ledger, live. The wallet is a sandbox: no real money." |
| 0:30 | Briefing → right panel | Point at the agents and their levels. | "Four AI colleagues, each its own Claude process with its own tools. Each can only *propose*. The owner set how far each may go." |
| 1:00 | Bills → Add a bill | Upload **LSH-2310 (clean)**. Wait ~20 s. | "Claude reads the bill and gives the exact quote for every field. Code, not the model, checks each quote is really in the document and does the arithmetic in paisa." |
| 1:40 | Bills → review form | Show the green quote checks, then **Record the bill and ask the Treasurer**. | "I confirm before anything is posted. Now the Treasurer plans the payment. It cannot type the amount or the payee: those come from the ledger." |
| 2:20 | Proposal link → Approvals | Open the proposal. Show the Guardian section. | "Fourteen rule checks in code, then a second model reviews the evidence as an adversary. Here it escalates: no purchase order on file, and today's payments pass the daily cap. So it waits for me." |
| 3:00 | Approvals | **Approve**, then **Send approved payments due today**. Open **Full trail**. | "Only now can the wallet pay. Seven steps: bill, proposal, checks, my decision, payment, the balanced journal, and a hash-chained audit trail that verifies." |
| 3:40 | Bills → Add a bill | Upload **LSH-2311 (injection)**. | "Now a bill with a trap: hidden text telling the AI to skip the checks and pay a new bank account." |
| 4:10 | Review form | Point at the red alert listing three instructions and the bank mismatch. Record it and ask the Treasurer. | "The reader reports the instructions instead of following them. The Treasurer refuses to propose a bill flagged like this, and even if one got through, the Guardian's reviewer flags the injection." |
| 4:40 | Financing (optional) | Point at the amber banner. | "Where we estimate, we say so: this ranking uses operating cash flow in place of audited EBITDA." |
| 5:00 | — | — | "Agents propose, the engine computes, the Guardian checks, and the owner decides." |

## If something goes wrong

- **The bill reader times out** (no Claude login or network): say so plainly and use the Approvals tab, which already has proposals from earlier runs. Every one has a full trail.
- **A page says the engine did not answer**: that is the honest state, not a crash. Restart `pnpm dev`.
- **The Guardian review shows "has not reported yet"**: the rule checks are already there; refresh after 30 to 60 seconds. Without the review the proposal still waits for the owner.

## Claims to avoid

Do not say "fully autonomous", "enterprise-grade", "bank-integrated" or "audited". Say "prototype", "sandbox wallet", "synthetic data", "owner approves every payment".
