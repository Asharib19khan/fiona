# Prompt 2 for Codex: the debt-versus-equity decision calculator (task Y4, core)

This is pure maths with no database or AI calls, and the rulebook specifies it exactly. Paste everything below the line into Codex.

---

You are the CODEX lane for Fiona (repository `Y:\Fiona`, Python 3.12, uv). You did the payment-timing optimiser well. Keep to the same discipline: other agents share this folder, so stay strictly inside the files listed below.

## The task
Build the calculator behind **"Should I fund this with a loan, an investor, my own cash, a mix, or wait?"** It takes a funding request plus the business's numbers, runs the rulebook's rules DE-00 to DE-09, and returns every option's figures, every rule result, and one recommendation, all **computed by code, never estimated.**

## Rule zero: do not invent anything
- Every rule, threshold ID, metric ID, schema field and helper function you use must exist in the files below. Open them first.
- Threshold **values** come from `rulebook/thresholds.yaml`, looked up by ID. Never hardcode them.
- If an input a rule needs is missing, that rule reports `insufficient_data` / unknown (the rulebook's `on_unknown` text says how). Never guess a value.
- Put any question in `docs/status/codex.md`. Don't claim tests pass unless you ran them.

## Read first
1. `CLAUDE.md`: money is always an **integer in minor units**, ratios are integer **basis points** (1.35x = 13500 bp), and there are no floats in any output.
2. `rulebook/finance_rules.yaml`, lines about 379 to 520: `decision_id: DEC-DE`, its options A_debt, B_equity, C_internal, D_mixed and E_defer, the **rules DE-00 to DE-09** (logic, conditions, outcomes, explanation templates, validation_tests), `recommendation_logic` (in order: the first match wins) and `confidence`. **This is your specification.**
3. `rulebook/thresholds.yaml`: the entries T-SOL-DSCR-01, T-SOL-DSCR-02, T-DEC-DOWN-01 (including its country rate shocks), T-DEC-DIL-01, T-DEC-HURDLE-01, T-DEC-AFF-01 and T-DEC-DATA-01. Also look at how `services/engine/analysis/rulebook.py` loads the rulebook, and reuse that loader if it fits.
4. `rulebook/metrics.yaml`: the metric IDs you will emit (`solvency.dscr_forward`, `solvency.dscr_forward_downside`, `solvency.debt_service_forward`, `decision.max_debt_at_min_dscr`, `decision.max_debt_downside`, `decision.dilution`, `decision.after_tax_cost_of_debt`, and so on). Use only IDs that exist there. If one is missing, list it as a question.
5. `services/engine/analysis/coverage.py`: `dscr`, `dscr_forward`, `max_principal_at_dscr` and `ratio_bp`. **These are the only DSCR implementation in the project. Call them and never re-implement them.**
6. `services/engine/decisions/tvm.py`: the amortisation, annuity payment, NPV and IRR helpers. Call them for loan schedules.
7. `services/engine/decisions/schemas.py`: `DebtEquityRequest`, `DebtTerms`, `EquityTerms`, `DecisionResponse`, `DecisionOption`, `DecisionRecommendation`, `AmortisationRow` and `CashPathPoint`. Your output **is** a `DecisionResponse` with `decision="debt_equity"`.
8. `services/engine/decisions/mocks.py`, the function behind the `decision_debt_equity` mock: the exact shape and style of the figures and rule checks. Your real output must look like it.
9. `services/engine/decisions/payment_timing.py`: your own earlier file, for the Figure and RuleCheck helpers you already used.

## Files you may create (and nothing else)
- `services/engine/decisions/debt_equity.py`
- `services/engine/decisions/tests/test_debt_equity.py`
- `docs/status/codex.md` (append a new section; keep the CX-Y8 section)

Do not edit `api.py`, `mocks.py`, `schemas.py`, the rulebook or any other file. Another agent wires the endpoint and the ledger later.

## Design
Write one public pure function. It reads no database and no ledger; every business fact is an argument:

```python
def decide_debt_equity(
    request: DebtEquityRequest,
    facts: DebtEquityFacts,       # define this Pydantic model in debt_equity.py
    *,
    as_of: date,
    run_id: str,
) -> DecisionResponse:
```

`DebtEquityFacts` holds exactly what DE-00 to DE-09 need, with integer money and basis points:
- the weekly forecast closing cash (week start dates and closing_minor) and the cash buffer
- EBITDA for the next 12 months (and, if missing, TTM EBITDA plus a flag that it is a fallback)
- the existing scheduled debt service for the next 12 months
- the stage classification
- whether the operating cash flow is negative
- the purpose category (one of the five in DE-01)
- the 3-month operating outflows
- the project IRR, in bp or None
- the tax rate in bp
- the cost of equity in bp or None
- the pre-money valuation (with its source string) or None
- the current ownership share of the owner in bp
- the unencumbered assets in minor units, or None
- the country (for DE-09 rate shocks)
- whether the facility is floating-rate
- the liquidity health band (`healthy`, `watch`, `stressed`, `critical`)

Anything optional and missing makes the dependent rule report unknown, as `on_unknown` says. It is never a guess.

**Computations:**
- **Option A, debt.** The terms come from `request.debt`. If `request.debt` is None, the outcome for A is `insufficient_data`, with the need "loan terms or the financing matcher's top option" (the matcher is another agent's work; do not call it). Build the amortisation schedule with tvm. Then compute:
  - the forward debt service = existing + new over the first 12 months
  - `dscr_forward` via coverage.py
  - the max principal at T-SOL-DSCR-01 via `max_principal_at_dscr`
  - the downside: EBITDA changed by T-DEC-DOWN-01 `revenue_change_bp` (apply the rulebook's definition exactly), with the rate raised by `rate_change_bp`, giving `dscr_forward_downside` and `max_debt_downside`
  - DE-09: the floating-rate shock for the country
  - DE-08: collateral against unencumbered assets, if both are known
- **Option B, equity.** If `request.equity` and a sourced valuation exist, dilution = amount / (pre_money + amount) in bp (DE-06), plus the escalation flag above T-DEC-DIL-01.
- **Option C, internal funds.** DE-02 exactly: internal_capacity = max(0, the minimum of (closing − buffer) over the weeks from the funding date), giving feasible, partial or infeasible.
- **Option D, a mix.** Debt equals `max_debt_downside`, with the remainder from C (up to internal_capacity) and then B.
- **Option E, defer.** It is always available, with the reason codes from the rules that fired.
- **DE-05 and DE-07** are applied exactly as written.
- **The recommendation** walks `recommendation_logic` **in order**, and the first matching branch wins. Record every branch tested in `rule_trace`, with passed or failed, so a reviewer sees why. Set `confidence` per the rulebook's `confidence` section.
- All rounding is half-up to integer minor units or basis points, using `Decimal` wherever a division happens.

## Tests (in `test_debt_equity.py`)
1. **The rulebook's own validation tests, exactly:**
   - DE-00-T1: no debt schedule gives `insufficient_data`, naming "existing debt schedule".
   - DE-02-T1: with a minimum closing balance of 258,000,000, a buffer of 200,000,000 and an amount of 100,000,000, the result is partial with capacity 58,000,000.
   - DE-03-T1: with EBITDA of 710,000,000, existing service of 261,612,000 and new service of 361,284,000, dscr_forward is **11398 bp** and A is `not_recommended_at_requested_size`.
2. One test per `recommendation_logic` branch, each a small hand-built `facts`, asserting the recommended option and the reason.
3. Edge cases:
   - funding operating losses (DE-01)
   - critical liquidity forces E
   - an equity request with no valuation makes B unknown, never a guessed dilution
   - floating rate with a PK shock
   - collateral exceeding the assets makes A `infeasible_collateral`
4. Hypothesis property tests:
   - Every money and basis-point value in the response is an `int`.
   - `max_debt_at_min_dscr`, borrowed on the same terms, gives a DSCR of at least the threshold (within 1 bp).
   - Increasing EBITDA never lowers dscr_forward.
   - The output validates as `DecisionResponse`.

## How to run (from `Y:\Fiona\services\engine`)
- `uv run pytest decisions -q`
- `uv run ruff check decisions` and `uv run ruff format decisions/debt_equity.py decisions/tests/test_debt_equity.py`
- Note: if the full suite (`uv run pytest -q`) errors in `wallet/` or `guardian_checks/`, that is another agent's unfinished work. Report it and don't fix it.

## Git (a shared folder)
- Never run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`, and never push.
- When green, run:
  `git add services/engine/decisions/debt_equity.py services/engine/decisions/tests/test_debt_equity.py docs/status/codex.md`
  `git commit -m "CX-Y4: debt-versus-equity calculator (DE-00..DE-09) with tests" -- services/engine/decisions/debt_equity.py services/engine/decisions/tests/test_debt_equity.py docs/status/codex.md`
  If you see `index.lock`, wait and retry.

## Finish
In `docs/status/codex.md`, add a CX-Y4 section with the real pytest summary line, the list of questions, and the list of any `on_unknown` interpretations you made. Then stop.
