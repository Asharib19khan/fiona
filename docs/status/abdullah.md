# Abdullah lane status (fiona-fa)

> **HANDOFF (paused Wed 14 Oct at b73a4b8, per pause order)**
> 1. Done: S1, B1, B2, B14, B3 (designed), Y2 core (stage, ratios, health bands, API on labelled stub; 31 tests), B4 rubric + memo schema + deterministic scorer (`evals/`, 6 tests).
> 2. Half-done: B4. Gold memos (financing choice, debt vs equity) are not written: they need Daniyal's generator v1 numbers (one source of numbers). The rubric's readable doc `rulebook/docs/B4_Memo_Scoring_Rubric.md` is also not written yet.
> 3. Exact next step: when D3 lands, write `services/engine/analysis/ledger_adapter.py` (postings by neutral_class -> `statements.Window`), switch the GET /v1/stage, ratios and health endpoints from stub to ledger, then write the 2 gold memos in `evals/gold/*.json` + `rulebook/docs/B4_Gold_Memos.md` from generator numbers.
> 4. Files: `rulebook/*.yaml`, `rulebook/docs/`, `services/engine/analysis/`, `evals/`.
> 5. Open questions: fiona-19 to remap CONTRACT_OWNERS "/v1/stage" -> analysis; Daniyal: is `clearing` cash or a receivable, and the FY CFO must be < -2% of revenue for the shake-out demo; memo schema (`evals/memo_schema.yaml`) not yet accepted by fiona-19.

Re-planned for the 20 Oct deadline (PLAN.md §4).

| ID | Task | Status | Due | Updated | Note |
| --- | --- | --- | --- | --- | --- |
| S1 | Organisers' rules, eligibility, cut-off | done | Wed 14 | Tue 13 | `docs/pitch/S1-rules.md`. Deadline 20 Oct 23:59 Beijing (20:59 PKT); eligible |
| B1 | Rulebook v1: stage rules, five decisions, priorities, health bands, thresholds, metrics, PK pack, `launch_lab.yaml` | done | Wed 14 | Tue 13 | `rulebook/*.yaml`, `rulebook/docs/B1_Finance_Rulebook_v1.md`; validator passes. Awaiting Abdullah's human review |
| B2 | Guardian rules G-01..G-12 (+G-13..15 proposed), default mandates, Mandate shape | done | Wed 14 | Tue 13 | `rulebook/guardian.yaml`, `mandates.yaml`, `docs/B2_Guardian_Rules_v1.md`; shape sent to fiona-19 |
| B14 | Financing catalogue `rulebook/financing.yaml` (PK and CN, sourced) | done | Thu 15 | Tue 13 | 13 PK + 7 CN options; SBP schemes primary-sourced; spreads labelled assumption; schema agreed with fiona-79 |
| B3 | Planted-issue scenarios with Daniyal | done (designed) | Thu 15 | Tue 13 | `rulebook/scenarios.yaml` is authoritative: DEMO-1, S-01..S-13, S-05b, S-08a/b/c, controls C-01..C-04; not yet executed (D5/A6) |
| Y2 | Stage Detector, ratio library, health bands, `metrics.yaml` complete | done (core) | Fri 16 | Wed 14 | 8b7c66d; serves labelled stub until the D3 ledger adapter |
| B4 | Gold memos (financing choice, debt versus equity) and rubric | doing | Sat 17 | Wed 14 | Rubric, schema, scorer done (b73a4b8); memos wait for generator v1 |
| — | Analysis screen | todo | Sun 18 | Tue 13 | `apps/web/app/(app)/analysis/` |
| D-01..06 | Submission deliverables, first drafts | moved | Sun 18 | Wed 14 | Moved to the Antigravity worker; Abdullah keeps finance QA of them (B6) |
| B6 | Finance QA sign-off | todo | Mon 19 | Tue 13 | Independent recalc against fixtures and ledger |
| D-final | Deliverables final, video recorded | todo | Mon 19 18:00 | Tue 13 | |
| B5, B10–B13 | Rulepacks, XBRL, consolidation, credit pack, Expo | Tier 3 | after 20 Oct | Tue 13 | |
