# Prompt 1 for Codex: the payment-timing optimiser (task Y8)

This is a small, self-contained task with pure maths and no database or AI calls; its own tests check it. Paste everything below the line into Codex.

---

You are the CODEX lane for Fiona, an AI finance copilot for small businesses. The repository is `Y:\Fiona` (Python 3.12, uv). Other agents work in the same folder, so stay strictly inside the files listed below.

## The task
Build the **payment-timing optimiser**. Given a business's open supplier bills, some of which offer an early-payment discount (for example "2/10 net 30": 2% off if paid within 10 days, otherwise due in 30), it decides for each bill whether to **pay early** to take the discount or **pay on the due date**, without letting the forecast cash balance fall below the owner's cash buffer.

## Rule zero: do not invent anything
Use only the names that already exist in the files below; open them first. If something is unclear, choose the conservative behaviour (pay on the due date) and write the question in `docs/status/codex.md`. Don't claim tests pass unless you ran them.

## Read first
1. `CLAUDE.md`, the repository rules: money is always an **integer in minor units** (PKR 1 = 100 minor), never a float; there are no AI calls in the engine.
2. `services/engine/decisions/schemas.py`: the output types `BillTiming` and `EarlyPaymentTerms`, and the rest of the file for context.
3. `services/engine/decisions/mocks.py`, the function `payment_timing()` and its helper `_annualised_discount`. This is the hand-built mock of exactly this feature. **Your job is the real computed version, producing the same shape:** rule IDs `PT-01` and `PT-02`, metric IDs `payments.annualised_discount_return` and `payments.closing_if_paid_early`, and the same `Figure`/`RuleCheck` constructors it imports from `engine.forecast.figures`.
4. `rulebook/metrics.yaml`, entry `payments.annualised_discount_return`: the formula is `(1 / (1 - d))^(365 / (N - n)) - 1`, the compounded effective rate. The worked example 2/10 net 30 gives **4459 bp** (simple form 3724 bp, which we don't use).
5. `services/engine/decisions/tests/test_tvm.py`, as an example of the test style.

## Files you may create (and nothing else)
- `services/engine/decisions/payment_timing.py`
- `services/engine/decisions/tests/test_payment_timing.py`
- `docs/status/codex.md`

Do **not** edit `api.py`, `mocks.py`, `schemas.py` or any other file; another agent wires the endpoint later.

## Specification
Write a public function:

```python
def optimise_payment_timing(
    bills: list[OpenBill],             # define OpenBill in payment_timing.py (a Pydantic model)
    weeks: list[WeekBalance],          # define WeekBalance: week (int >= 1), start (date), end (date), closing_minor (int)
    *,
    buffer_minor: int,                 # the owner's cash buffer
    cost_of_money_annual_bp: int,      # for example 2200 = 22% a year
    as_of: date,
    currency: str,
) -> list[BillTiming]:
```

`OpenBill` has `bill_id`, `supplier_id`, `supplier_name`, `amount_minor` (int, > 0), `issue_date`, `due_date` and `terms: EarlyPaymentTerms | None`. `weeks` is the **baseline** 13-week forecast, which already assumes every bill is paid on its due date.

**Rules:**
1. **Annualised return:** compute it exactly as in metrics.yaml, using `Decimal` (no float drift), and return integer basis points rounded half-up. 2/10 net 30 must give 4459.
2. **Discount amount:** `discount_minor = round_half_up(amount_minor * discount_bp / 10000)`. Paying early costs `amount_minor - discount_minor`, on the **last qualifying day**, `issue_date + within_days`.
3. **Not eligible for early payment** (action is `pay_on_due`, and `pay_on` is the due date) when: there are no terms; or the last qualifying day is on or before `as_of`; or the last qualifying day falls outside the forecast weeks; or `net_days <= within_days`.
4. **PT-01 passes** if the annualised return is strictly greater than `cost_of_money_annual_bp`.
5. **PT-02, the cash effect of paying early** compared with the baseline: every week from the week containing the early day up to, *but not including*, the week containing the due date gets `closing - (amount_minor - discount_minor)`. Every week from the due-date week onward gets `closing + discount_minor`. If the due date is beyond the forecast horizon, the reduction applies to all remaining weeks. PT-02 passes if **every** adjusted closing balance is `>= buffer_minor`.
6. **Several bills:** decide the eligible early-payment candidates in descending order of annualised return (ties broken by `bill_id`). Each accepted early payment **changes the cash path** that the next candidate is tested against, so two early payments can never jointly breach the buffer.
7. **Action:** `pay_early` (with `pay_on` = the last qualifying day) only if PT-01 and PT-02 both pass. Otherwise `pay_on_due`. Use `cannot_pay_on_due` only when the **baseline** closing balance of the due-date week is below zero. In that case also set `pay_on` = the due date and explain in the rule check.
8. Every number in `figures` is a Figure with integer money or basis points, and every `RuleCheck` says what was tested and with which threshold, mirroring `mocks.py`.
9. Return the bills in the input order.

## Tests (in `test_payment_timing.py`)
- 2/10 net 30 gives 4459 bp. For 1/10 net 45, compute the expected value independently in the test with `Decimal`.
- A worthwhile discount with ample cash: `pay_early` on the correct date, and the discount amount is exact.
- A worthwhile discount where paying early drops one week below the buffer: `pay_on_due`, with PT-02 failing.
- A discount below the cost of money: `pay_on_due`, with PT-01 failing.
- Two bills that would each fit alone but breach together: only the higher-return one is paid early.
- The discount window already passed, or no terms: `pay_on_due`.
- A baseline due-week closing balance below zero: `cannot_pay_on_due`.
- Hypothesis property tests over random bills and paths:
  - The final adjusted path never goes below the buffer in any week touched by a `pay_early` decision.
  - Every money value in the output is an `int`.
  - The output length equals the input length.

## How to run (from `Y:\Fiona\services\engine`)
- `uv run pytest decisions -q` for your tests, and `uv run pytest -q` to keep the whole suite green.
- `uv run ruff check decisions` and `uv run ruff format decisions/payment_timing.py decisions/tests/test_payment_timing.py`

These tests need no database.

## Git (a shared folder; be careful)
- Never run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`, and never push.
- When your tests pass, run:
  `git add services/engine/decisions/payment_timing.py services/engine/decisions/tests/test_payment_timing.py docs/status/codex.md`
  `git commit -m "CX-Y8: payment-timing optimiser with tests" -- services/engine/decisions/payment_timing.py services/engine/decisions/tests/test_payment_timing.py docs/status/codex.md`
  If you see `index.lock`, wait a few seconds and retry.

## Finish
In `docs/status/codex.md`, write the real pytest summary line, any questions, and anything you weren't sure about. Then stop.
