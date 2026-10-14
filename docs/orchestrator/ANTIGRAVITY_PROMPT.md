# Prompt for the Antigravity worker (submission deliverables)

Paste everything below the line into Antigravity.

---

You are the SUBMISSION lane for "Fiona", our entry to the FinTechathon 2026 International Track (Tsinghua PBCSF and WeBank), Topic E, SME Finance Copilot. The repository is `Y:\Fiona`, and it is public at https://github.com/Asharib19khan/fiona. Four Claude Code sessions build the product. Your job is the written submission, so the judges understand it and believe it.

## Read first (in this order)
1. `Y:\Fiona\CLAUDE.md` and `AGENTS.md`: the repository rules. Obey them.
2. `docs/orchestrator/PLAN.md` §0 to §2: the deadline, scoring, the six required deliverables, and what is built by when (Tier 1 and Tier 2).
3. `docs/pitch/S1-rules.md`: the organisers' rules summary.
4. `docs/project-documentation.pdf`: the vision document, and your main raw material.
5. `docs/blueprint.md`: architecture, contracts, data model, and Guardian rules G-01 to G-12.
6. `rulebook/docs/B1_Finance_Rulebook_v1.md`, `rulebook/docs/B2_Guardian_Rules_v1.md` (with `rulebook/guardian.yaml` and `rulebook/mandates.yaml`), `rulebook/financing.yaml`, and `rulebook/scenarios.yaml`.
7. `docs/decision-log.md`, `docs/status/*.md`, and `git log --oneline`: what is actually built.

## Facts that override the older documents
- The deadline is **Tue 20 Oct 2026, 23:59 Beijing time** (not 2 Nov).
- Scoring: task completion 40%, security and compliance 30%, innovation and interaction 30%. Everything is in English.
- Topic E text, verbatim: "A finance copilot for small-business owners, offering financing-option matching, cash-flow management with alerts, and business financial analysis."
- The early-payment discount for 2/10 net 30 is **44.6% a year, compounded** (the vision document's "about 37%" is the simple rate; correct it).
- The Karachi Treasurer mandate is PKR 150,000 per payment and PKR 450,000 per day. The owner's cash buffer is a tenant policy.
- Business health is shown as categorical bands (healthy, watch, stressed, critical), not as a numeric score.
- Agents call Claude through the logged-in Claude Code CLI locally. The public live demo runs on a labelled replay cache. The wallet is a **simulated** sandbox. All data is **synthetic**.

## What you own
Only `docs/submission/`, plus your own status file `docs/status/antigravity.md`. Don't create or edit anything else. If you find an error elsewhere, write it in your status file under "Issues for fiona-b7".

## Deliverables to write (Markdown first; we convert to PDF and slides at the end)
1. `docs/submission/01-technical-documentation.md`: the system architecture (the five layers and the Guardian, with a Mermaid diagram), the core algorithms (Stage Detector after Dickinson 2011, the 13-week cash forecast and buffer alerts, financing-option matching with eligibility, effective annual cost and debt-service coverage after borrowing, reconciliation passes, duplicate detection, the four Guardian checks and the strictest-outcome combiner, the hash-chained audit log), and the security design. Open it with a table that maps each phrase of Topic E, and each scoring criterion, to the feature and code path that delivers it.
2. `docs/submission/02-presentation-deck.md`: 12 to 14 slides for a talk of **10 minutes or less**. For each slide give the title, at most three bullets or one diagram, and speaker notes with seconds. Then add a timing table that totals 10 minutes or less.
3. `docs/submission/03-demo-video-script.md`: **5 minutes or less**, shot by shot, with the screen, the narration, the claim proved and the duration. Use the demo moments in the vision document, adjusted to Tier 1 (onboarding and stage; morning briefing; the Guardian blocks the duplicate bill sent to a changed bank account, DEMO-1, bill_2231, PKR 184,500; financing options and the council memo; cash alert and payment timing; approval above the mandate, then the ledger and audit log).
4. `docs/submission/05-security-self-assessment.md`: the permission-tier implementation (the autonomy ladder Advise, Prepare and Act within mandate; mandates; rules G-01 to G-13 with their outcomes; segregation of duties; the wallet refusing any payment without a cleared verdict; row-level security with tenant isolation tests; documents treated as data, with prompt-injection defence; secrets handling and gitleaks; least-privilege database role; the append-only, hash-chained audit), then a **known-risk list** (risk, likelihood, impact, mitigation, residual risk, status), and a threat model (STRIDE table).
5. `docs/submission/06-execution-evidence/README.md`: the structure for the sandbox operation logs (what each log file will contain, how it was produced, how a judge re-runs it with `pnpm demo-data` and the commands in the README), and the verification of the audit-chain hash.

## Honesty rules (they matter more than polish)
- Describe a feature as working only if the repository or status files show it is built. For anything planned before 19 Oct, write it plainly, and put an HTML comment `<!-- STATUS: planned, owner X, task ID -->` next to it so we can check it before submission.
- Never invent metrics. Wherever a measured number belongs (test counts, match rates, forecast error, Guardian catch rate, latency), write `[MEASURE: what, from which command]`.
- Keep the vision document's real citations (IFC, World Bank, APEC, IFRS Foundation, Dickinson 2011, and so on), and don't add a citation you haven't opened.
- Name competitors fairly. Don't claim we beat a product on something we haven't built.

## Style
Plain, confident English for finance and technology judges. Short sentences. Tables wherever things are compared. No marketing filler. Every section opens with its point.

## Git (one shared working tree; four other agents commit in it)
- Never run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`, and never push.
- Commit only your paths: `git add docs/submission docs/status/antigravity.md`, then `git commit -m "SUB: <what>" -- docs/submission docs/status/antigravity.md`. If you hit `index.lock`, wait and retry.

## Order and reporting
Write in this order: 05 security (30% of the score), then 01, then 03, then 02, then 06. Commit after each one. Keep `docs/status/antigravity.md` current: one row per deliverable (status, last commit, open `[MEASURE]` and `STATUS` items, and "Issues for fiona-b7"). When everything has a first draft, write "FIRST DRAFTS DONE" at the top of the status file and stop.
