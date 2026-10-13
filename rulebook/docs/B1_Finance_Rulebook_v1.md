# Finance Rulebook v1 (B1)

Owner: Abdullah lane (fiona-fa). Version 1.0.0, effective 14 October 2026 (G1).
Machine-readable rules: [finance_rules.yaml](../finance_rules.yaml), [thresholds.yaml](../thresholds.yaml), [metrics.yaml](../metrics.yaml), [launch_lab.yaml](../launch_lab.yaml), [country_packs/PK.yaml](../country_packs/PK.yaml). Check them with `python rulebook/tools/validate_rulebook.py`.

**Who this is for.** Yahya and the Analysis lane implement it (Y2 Stage Detector and ratios, Y4 decisions, Y10 financing matcher), Asharib's CFO Strategist prompt cites it, and finance reviewers check it. Every rule has inputs, conditions, outcomes and a test in the YAML; this document explains the reasoning.

**What is evidence and what is judgement.** Formulas and the Dickinson sign patterns are established method. Most numeric thresholds are **expert judgement, marked `provisional` in the register**, with a validation plan. None of them is a legal requirement unless the register says so, and none decides a material question alone.

## One-page summary

| Area | What Fiona does | Rule IDs | Key thresholds (class) |
| --- | --- | --- | --- |
| Lifecycle stage | Classifies the last 12 months of operating, investing and financing cash flows by sign (Dickinson 2011), checks the prior year, tests against revenue growth and margins, and explains any disagreement with the owner's view | STG-00 to STG-07 | 12 months minimum (hard); near-zero band 2% of revenue (provisional) |
| Health | Bands each of liquidity, profitability, solvency, efficiency and cash generation as healthy, watch, stressed or critical. **No composite score in v1.** | health.* | Forecast cash < 0 = critical; any week below buffer = stressed; ICR, DSCR, net debt/EBITDA bands (advisory, provisional) |
| Stage priorities | Sets what the CFO Strategist investigates first; a stressed health dimension always outranks the stage | stage_priorities | — |
| Debt or equity | Compares debt, equity, internal funds, a mix and deferral: affordability, coverage after borrowing (base and downside), return versus cost, dilution, collateral, floating-rate risk | DE-00 to DE-09 | DSCR ≥ 1.25x base (advisory), ≥ 1.0x downside (risk indicator); dilution 25% (risk indicator) |
| Dividend or reinvest | Liquidity gate first, then legal distributability (Companies Act 2017 s.240–241 for Pakistan), covenants, then return comparison; gives a range only when every input exists | DIV-00 to DIV-06 | Buffer (owner policy); payout guidance by stage (advisory) |
| Asset investment | NPV, IRR, payback, peak funding need, downside, lease versus buy, staging | CAP-00 to CAP-06 | Hurdle = WACC + premium (provisional); payback 36 months (owner policy default) |
| Liability reduction | Pay-down order by after-tax effective cost then risk; never below the buffer; working-capital release; early-payment discounts | LIA-00 to LIA-06 | Prepayment spread 2 points (advisory) |
| Innovation and technology | 3-year total cost of ownership, a budget from free cash flow, measurable outcomes required, pilot first when uncertain | INN-00 to INN-06 | Budget share by stage (advisory); pilot triggers (advisory) |
| Launch Lab | Contribution margin, probability of breaking even within the horizon, loss probability, cash check | launch_lab.yaml | Margin 20%, P(break-even) 70%, P(loss) 30% (provisional); cost of capital 22% for PK |

## Conventions

- **Units.** Money is integer minor units plus a currency. Rates, shares and ratios are integer basis points (a coverage of 1.25x is 12,500 bp). No floats anywhere in the rulebook; the validator fails on one.
- **Null, not zero.** A metric that cannot be computed is null with a reason. A condition on a null metric is "unknown", and each rule says what happens then.
- **Rounding.** Compute unrounded; round once at the boundary, half away from zero (the same as a spreadsheet's ROUND, so QA can recompute by hand).
- **Conditions** use one small grammar (`all`, `any`, `not`, predicates on a metric or input against a value, a threshold or another metric), described at the top of `finance_rules.yaml`.

## 1. Lifecycle stage

The cash-flow pattern is evidence of where the money comes from and goes, which is harder to dress up than revenue or the owner's description.

| Pattern | Operating | Investing | Financing | Stage |
| --- | --- | --- | --- | --- |
| P1 | out | out | in | Introduction |
| P2 | in | out | in | Growth |
| P3 | in | out | out | Mature |
| P4 | out | out | out | Shake-out |
| P5 | in | in | in | Shake-out |
| P6 | in | in | out | Shake-out |
| P7 | out | in | in | Decline |
| P8 | out | in | out | Decline |

Shake-out is the stage assigned to every pattern that is not one of the other four, as the project documentation and Dickinson (2011) describe. The P-numbers are ours; the paper's own numbering is not reproduced here.

**How ambiguity is handled.**

- **Near-zero flows.** A component within 2% of revenue counts as "near zero", because a rounding-sized flow should not flip the stage. Fiona tries both signs. If they give the same stage, there is no ambiguity. If not, it reports the more likely stage, names the alternative, and confidence is low.
- **Two windows.** The latest 12 months decide the stage; the prior 12 months show whether it is stable or in transition.
- **Distortions.** An acquisition, a one-off loan or equity injection above 10% of revenue, a one-off asset sale, a missing month, or an owner-declared event (fire, flood, closure) is flagged. Fiona shows the stage with and without the item and lowers confidence one step for each.
- **Seasonality.** Never classify a quarter. Seasonal businesses are classified only on full 12-month windows.

**When the owner disagrees.** Fiona never silently picks one view. It states the owner's view, the cash-flow evidence, which component contradicts the owner's stage, and what would have to be true for the owner to be right. Demo moment 1 is exactly this: "the owner described a growth business but the cash flows say shake-out, and shows why".

## 2. Health assessment

Each dimension gets a band from transparent rules (see the YAML). The overall status is a rule, not a weighted score: **critical** if liquidity or solvency is critical; **stressed** if either is stressed or operating cash flow has been negative two years running; **watch** if any dimension is watch or worse; otherwise **healthy**.

Why no composite score: a single number needs weights calibrated against real outcomes (defaults, distress), and we have none. A fake-precise score would be an unsupported claim. If the product needs a headline, it shows the overall band and the worst dimension.

Two explanations are built in because owners meet them constantly:

- **Profitable but cash-negative (HLT-DIV-01).** Profit is positive and operating cash flow negative. Fiona shows the working-capital bridge: how much went into stock and receivables and how much suppliers funded.
- **Cash-rich but unprofitable (HLT-DIV-02).** Cash sits above the buffer while operations lose money. Fiona shows how many months the surplus lasts: the cash buys time, not a fix.

## 3. Stage priorities

| Stage | First priority | Financing to evaluate | Dividend policy | Defer when risk is high |
| --- | --- | --- | --- | --- |
| Introduction | Runway | Equity, grants, founder funds; debt only if asset- or receivable-backed | None | Fixed costs, long leases, debt-funded capex |
| Growth | Working capital as sales grow | Mix sized to downside coverage | Low or none | Several sites at once |
| Mature | ROIC against the cost of capital | Internal funds, cheaper debt | Regular, covered by FCF | Special distributions, diversification |
| Shake-out | Margins and cost structure | No new long-term debt without a costed turnaround | None until 12 months of positive CFO | Expansion, dividends, large IT programmes |
| Decline | Liquidity and survival | Asset-backed or restructuring finance only | None (unless winding down lawfully) | Everything discretionary |

The full matrix (liquidity policy, investment, debt management, technology approach and warning signals) is in `finance_rules.yaml`. These are priorities for investigation, not commands: a stressed health dimension always comes first.

## 4. The five decisions

Every decision returns a status (`recommended`, `insufficient_data` or `refused_out_of_scope`), ranked options with their figures, a recommendation with conditions, a confidence level, the thresholds used and **the evidence that would change the answer**. If a mandatory input is missing, the answer is "Fiona needs X", never a guess (T-DEC-DATA-01).

### 4.1 Debt or equity (Tier 1, scored as "financing-option matching")

The options are A debt, B equity, C internal funds, D a mix, and E defer or reduce. The order of tests reflects the principle that liquidity and survival come first.

1. **Data** (DE-00): purpose, amount, timing, 12 months of statements or ledger, the debt schedule, the 13-week forecast and the buffer. Indicative terms are needed for a loan, a cap table and terms for equity.
2. **Purpose** (DE-01): borrowing to fund operating losses is flagged; it adds a fixed repayment to a business already short of cash.
3. **Internal capacity** (DE-02): the lowest forecast cash minus the buffer is the most the business can spend itself.
4. **Coverage after borrowing** (DE-03, DE-04): next-12-months EBITDA over existing plus new debt service. At least 1.25x in the base case (a common lender range is 1.20–1.50x; this is judgement, replaced by the actual covenant when a term sheet exists) and 1.0x in the downside. If either fails, Fiona computes the largest loan that passes, and the rest must come from another source.
5. **Return versus cost** (DE-05): if the project earns less than the after-tax cost of the cheapest source, deferral wins. Equity is not free (investors require a higher return than lenders, and dilution takes a share of every future profit); debt is not automatically worse (it is cheaper after tax but its repayments are fixed).
6. **Dilution and control** (DE-06): valuation must come from investor terms or a stated method shown as a range. Above 25%, the memo must discuss board seats and vetoes, and the owner decides.
7. **Stage fit, collateral, floating rates** (DE-07 to DE-09): the rate shock for Pakistan is +300 bp downside and +600 bp severe, because 6-month KIBOR (12.42% on 12 October 2026) already sits above the 11.5% policy rate.

**Worked example (hand-made, not persona data).** Forecast EBITDA PKR 7.10m; existing debt service PKR 2.62m; a new loan adds PKR 3.61m of service. Coverage = 7.10 / (2.62 + 3.61) = **1.14x**, below 1.25x, so the full loan is not recommended. In the downside the business could service only a small fraction of it, so Fiona recommends a mix or deferral and shows the maximum debt at each threshold.

### 4.2 Dividend or reinvest

The liquidity gate comes first and is a hard control: the most that can be paid is the lowest forecast cash minus the buffer from the pay date onwards. Then come the legal tests. In Pakistan, dividends only out of profits (Companies Act 2017 s.241), and none out of profits on disposals of capital assets or unrealised investment-property gains (s.240(2)). Fiona never certifies distributability; it asks for the accountant's confirmation. Then covenants, and only then the comparison of returns: retain when a positive-NPV use needs the cash within 12 months or working capital is bloated; distribute when ROIC is below the hurdle and no good use exists. Accounting profit, cash, retained earnings and distributable reserves are kept separate throughout.

### 4.3 Asset investment (including lease versus buy)

Fiona builds incremental after-tax cash flows and tests NPV at the hurdle, IRR (only when the cash flows change sign once), payback and peak funding need. Affordability is a hard gate: **a positive NPV does not help if the business cannot get through the first months.** The downside and severe cases must keep the buffer. Lease versus buy is decided on cash, discounted at the after-tax cost of secured debt; the different accounting under IFRS 16, IFRS for SMEs Section 20 and ASC 842 changes reported EBITDA and leverage, not the decision (see B5).

### 4.4 Liability reduction

Facilities are ranked by after-tax effective annual cost including fees; ties within 1 point are broken by risk (floating rate, maturity, covenant headroom, personal guarantees). A facility facing a downside covenant breach goes first whatever its rate. Prepayment requires the buffer to hold in every forecast week and a spread of at least 2 points over the return on surplus cash. Fiona also shows cash that working capital can release, and takes an early-payment discount when its implied annual return beats the cost of funds (2/10 net 30 is 44.6% a year compounded, or 37.2% in the simple form). Fiona never recommends paying suppliers late.

### 4.5 Innovation and technology

Fiona computes a 3-year total cost of ownership including staff time, security and exit costs. The budget is a stage-based share of free cash flow after maintenance capex, capped by cash above the buffer. At least one measurable outcome with a baseline is required. Fiona pilots first when cost exceeds the budget, payback exceeds 24 months, an outcome is missing, or readiness is unproven, and adopts rather than builds unless nothing on the market fits.

## 5. Market inputs (Pakistan, read 13 October 2026)

| Input | Value | Describes | Source | Verification |
| --- | --- | --- | --- | --- |
| SBP policy rate | 11.50% | MPC decision of 14 Sep 2026 (hold) | SBP press release | Primary |
| 6-month KIBOR, offer | 12.42% | 12 Oct 2026 | SBP KIBOR sheet | Primary |
| CPI inflation | 10.3% YoY | September 2026 (published 1 Oct) | PBS, via Business Recorder | Secondary |
| USD/PKR (M2M) | 276.96 | 13 Oct 2026 | SBP website | Primary |
| Corporate tax rate | 29% | Companies other than banks and small companies | PwC tax summaries | Secondary |

These affect decisions directly. Borrowing costs about 15.4% before tax (KIBOR plus an assumed 3% spread). With inflation at 10.3%, nominal revenue growth below that is a real decline. Rate shocks are sized wider for Pakistan. Fiona does not forecast rates or exchange rates; it stress-tests them. Each value has a staleness limit in the country pack.

## 6. What is not settled (open questions)

1. **Concept mapping.** Does the `clearing` account class (card and wallet settlements in transit) count as cash? v1 says no, which is conservative. Needs Daniyal.
2. **Forward EBITDA.** Is there a 12-month EBITDA projection (Y4) or only the 13-week cash forecast? DE-03 falls back to trailing EBITDA with lower confidence.
3. **Industry packs.** Apparel overrides exist for the current ratio, quick ratio and Launch Lab; others come with B1b.
4. **Provisional thresholds.** The validation plan in `thresholds.yaml` lists how each one gets tested before G4.
5. **Health score.** PLAN.md lists a "health score" for Y2. v1 delivers bands, not a number, for the reason above; a calibrated score is Tier 3.

## Sources

- Dickinson, V. (2011). Cash Flow Patterns as a Proxy for Firm Life Cycle. *The Accounting Review*, 86(6), 1969–1994. The sign-to-stage mapping is as summarised in the project documentation and reproduced in a [2017 Brazilian Business Review study](https://scielo.br/j/bbr/a/TCZG85pSFrYcMMZrHJYQCGd/?lang=en) (Table 2; shake-out "by exclusion of others").
- State Bank of Pakistan: [MPC decision, 14 Sep 2026](http://www.sbp.org.pk/assets/documents/press-release/Pr-14-Sep-2026.pdf); [KIBOR, 12 Oct 2026](https://www.sbp.org.pk/assets/document/kibor-rates-12-october-2026.pdf).
- [Business Recorder, "Sept CPI inflation up 10.3pc YoY"](https://www.brecorder.com/news/40442263/sept-cpi-inflation-up-103pc-yoy) (PBS data, 1 Oct 2026).
- Companies Act 2017 (Pakistan), ss. 240–243, Gazette text of 31 May 2017 ([copy on psx.com.pk](https://www.psx.com.pk/psx/themes/psx/documents/legal-framework/SECP/act/companies-act-2017/companiesAct2017.pdf)); later amendments not checked.
- [PwC worldwide tax summaries, Pakistan](https://taxsummaries.pwc.com/pakistan/corporate/significant-developments) (corporate rate; secondary).
