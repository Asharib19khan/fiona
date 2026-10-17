"""Y7 cash-forecast backtest against the generator's held-out 13 weeks.

The held-out file is read only.  It is never fed into ``forecast_cash``: the forecast sees
only the fixture through its ``as_of`` date.  The baseline is a seasonal-naive weekly cash
movement: the same seven-day movement one year earlier, rolled forward from today's cash.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from engine.forecast.cash.engine import forecast_cash
from engine.forecast.ledger_source import FIXTURES_ROOT, LedgerSnapshot, load_fixture_snapshot


@dataclass(frozen=True)
class ErrorSummary:
    wape_bp: int
    mae_minor: int


@dataclass(frozen=True)
class WeekResult:
    week: int
    start: str
    actual_net_minor: int
    forecast_net_minor: int
    naive_net_minor: int
    actual_closing_minor: int
    forecast_closing_minor: int
    naive_closing_minor: int


@dataclass(frozen=True)
class BacktestReport:
    method_version: str
    tenant_id: str
    currency: str
    as_of: str
    holdout_weeks: int
    target: str
    forecast: ErrorSummary
    seasonal_naive: ErrorSummary
    forecast_beats_baseline: bool
    data_limit: str
    weeks: list[WeekResult]


def _wape_bp(actual: list[int], predicted: list[int]) -> int:
    denominator = sum(abs(value) for value in actual)
    if denominator == 0:
        raise ValueError("cannot calculate WAPE where all actual movements are zero")
    return round(
        sum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) * 10_000 / denominator
    )


def _mae(actual: list[int], predicted: list[int]) -> int:
    return round(sum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) / len(actual))


def _holdout_weeks(tenant_id: str, root: Path) -> list[dict]:
    path = root / "holdout" / tenant_id / "cash_weekly.json"
    if not path.is_file():
        raise FileNotFoundError(f"No held-out cash truth at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("notice", "").startswith("HELD OUT") is False:
        raise ValueError(f"{path} is not marked as held-out truth")
    return payload["weeks"]


def _seasonal_naive_net(snap: LedgerSnapshot, start: date) -> int:
    prior_start = start - timedelta(days=364)
    prior_end = prior_start + timedelta(days=6)
    return sum(
        line.amount_minor for line in snap.bank_lines if prior_start <= line.posted_on <= prior_end
    )


def backtest_cash(snap: LedgerSnapshot, *, root: Path = FIXTURES_ROOT) -> BacktestReport:
    """Score the production cash forecast without exposing the held-out outcome to it."""
    forecast = forecast_cash(snap, weeks=13)
    actual_rows = _holdout_weeks(snap.tenant_id, root)
    if len(actual_rows) != len(forecast.weeks):
        raise ValueError("holdout and forecast horizons differ")

    naive_closing = forecast.opening_balance.money.minor
    results: list[WeekResult] = []
    for prediction, actual in zip(forecast.weeks, actual_rows, strict=True):
        start = date.fromisoformat(actual["start"])
        if prediction.start != start:
            raise ValueError("holdout week dates do not align with the forecast")
        naive_net = _seasonal_naive_net(snap, start)
        naive_closing += naive_net
        results.append(
            WeekResult(
                week=prediction.week,
                start=actual["start"],
                actual_net_minor=actual["inflows_minor"] - actual["outflows_minor"],
                forecast_net_minor=prediction.net.minor,
                naive_net_minor=naive_net,
                actual_closing_minor=actual["closing_minor"],
                forecast_closing_minor=prediction.closing.minor,
                naive_closing_minor=naive_closing,
            )
        )
    actual_net = [row.actual_net_minor for row in results]
    forecast_net = [row.forecast_net_minor for row in results]
    naive_net = [row.naive_net_minor for row in results]
    forecast_error = ErrorSummary(
        _wape_bp(actual_net, forecast_net), _mae(actual_net, forecast_net)
    )
    naive_error = ErrorSummary(_wape_bp(actual_net, naive_net), _mae(actual_net, naive_net))
    return BacktestReport(
        method_version="cash-backtest/0.1.0",
        tenant_id=snap.tenant_id,
        currency=snap.currency,
        as_of=snap.as_of.isoformat(),
        holdout_weeks=len(results),
        target="weekly net cash movement; WAPE is sum(abs(error)) / sum(abs(actual))",
        forecast=forecast_error,
        seasonal_naive=naive_error,
        forecast_beats_baseline=forecast_error.wape_bp < naive_error.wape_bp,
        data_limit="Synthetic generator holdout only. This evaluates pipeline behaviour, not real-world forecast accuracy.",
        weeks=results,
    )


def main() -> int:
    report = backtest_cash(load_fixture_snapshot("ten_karachi_apparel"))
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
