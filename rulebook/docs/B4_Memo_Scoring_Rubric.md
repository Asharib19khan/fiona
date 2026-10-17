# B4 Memo Scoring Rubric

This document describes how Fiona scores a CFO Strategist decision memo against an approved gold
memo. The executable rubric is [`evals/memo_rubric.yaml`](../../evals/memo_rubric.yaml) and the
deterministic scorer is [`evals/score_memo.py`](../../evals/score_memo.py).

The pass mark is **8.0 out of 10**. A score does not authorise an action: borrowing, raising
equity, signing a contract and paying a dividend remain owner decisions.

| Criterion | Weight | What earns full credit |
| --- | ---: | --- |
| Correct financial figures | 2.00 | Each figure matches the engine output. Money must match in minor units after display rounding; ratios must match within display rounding. |
| Direction of recommendation | 2.00 | The recommended option and its conditions match the gold memo, or use an approved alternative when its condition is met. |
| Liquidity and risk first | 1.50 | States the cash buffer, lowest forecast cash and first breach, tests every option against liquidity, and covers a downside case. |
| Alternatives compared | 1.00 | Compares every realistic option on the same measures and explains the trade-offs. |
| Assumptions and limitations | 1.00 | Labels every material assumption by source class and states synthetic, stub or data limitations. |
| Evidence and traceability | 1.00 | Every numeric claim resolves to a Figure, and external facts have a dated source. |
| Downside and sensitivity | 0.75 | Covers base, downside and severe cases and says what would change the recommendation. |
| Actionable recommendation | 0.75 | Gives staged steps, owners, dates, required approvals, monitoring triggers and a pause-or-reverse condition. |

The scorer checks figures, recommendation direction, citations and critical failures without a
model. A reviewer assigns `full`, `partial` or `none` for the four judgement criteria. The
reviewer must retain the supporting memo excerpts in the score sheet.

## Critical failures

| Failure | Result |
| --- | --- |
| A key figure is materially wrong or has the wrong sign | Score capped at 4.0 |
| A factual or numeric claim has no Figure or cited source | Score capped at 5.0 |
| An imminent buffer breach is ignored while recommending an outflow | Score capped at 3.0 |
| The memo claims Fiona can borrow, raise equity, pay a dividend or execute a restricted action | Invalid, score 0 |
| The memo invents a probability the engine did not return | Score capped at 5.0 |
| A council memo omits a dissent | Deduct 1.0 |

## Required memo shape

Memos follow [`evals/memo_schema.yaml`](../../evals/memo_schema.yaml). Each number appears as a
Figure once and sections refer to it by `metric_id`. A memo includes its evidence, assumptions,
options, downside cases, implementation steps, risk triggers and any council dissent.

Gold memos are stored under `evals/gold/`. They are written from the approved engine figures for
the seeded generator scenario and identify synthetic or stub inputs in their header.
