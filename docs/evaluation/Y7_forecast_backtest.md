# Y7 cash-forecast evaluation

Run the synthetic backtest from the repository root:

```powershell
node scripts/engine-py.mjs engine.forecast.evaluation
```

The command forecasts from the fixture as of its recorded `as_of` date and compares the next
13 weeks with `data/fixtures/holdout/ten_karachi_apparel/cash_weekly.json`. The held-out file is
never an input to the forecast.

The baseline is seasonal-naive weekly net cash movement: the net movement in the equivalent
seven-day period one year earlier, accumulated from current cash. Both methods are evaluated on
weekly net cash movement using WAPE, plus mean absolute error in minor currency units.

The result is synthetic-only. It demonstrates a reproducible pipeline and baseline comparison;
it does not establish real-world forecast accuracy. The UCI Online Retail II comparison remains
pending because that dataset is not present in this repository or recorded in
`THIRD_PARTY_NOTICES.md`.
