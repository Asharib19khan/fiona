"""Every Yahya-lane mock: its builder, response model and fixture file."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from engine.decisions import mocks as decision_mocks
from engine.decisions.schemas import DecisionResponse, PaymentTimingResponse
from engine.financing import mocks as financing_mocks
from engine.financing.schemas import FinancingMatchResponse
from engine.forecast.cash.schemas import CashForecastResponse
from engine.forecast.feed.rank import rank_findings
from engine.forecast.feed.schemas import FindingsResponse, SourceStatus
from engine.forecast.inventory.schemas import InventoryAnalysisResponse
from engine.forecast.launch_lab.schemas import LaunchLabResponse
from engine.forecast.mocks import GENERATED_AT, dump, envelope
from engine.forecast.mocks import cash as cash_mock
from engine.forecast.mocks import inventory as inventory_mock
from engine.forecast.mocks import launch_lab as launch_mock

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Mock:
    name: str
    model: type[BaseModel]
    build: Callable[[], BaseModel]

    @property
    def path(self) -> Path:
        return DATA_DIR / f"{self.name}.json"


def _feed() -> FindingsResponse:
    cash = cash_mock.build()
    inventory = inventory_mock.build()
    launch = launch_mock.build()
    return FindingsResponse(
        **envelope(),
        findings=rank_findings([*cash.findings, *inventory.findings, *launch.findings]),
        sources=[
            SourceStatus(
                source="forecast", status="ok", run_id=cash.run_id, generated_at=GENERATED_AT
            ),
            SourceStatus(
                source="inventory", status="ok", run_id=inventory.run_id, generated_at=GENERATED_AT
            ),
            SourceStatus(
                source="launch_lab", status="ok", run_id=launch.run_id, generated_at=GENERATED_AT
            ),
            SourceStatus(
                source="financing",
                status="unavailable",
                note="Y10 publishes findings from Fri 16 Oct.",
            ),
        ],
    )


MOCKS: dict[str, Mock] = {
    m.name: m
    for m in (
        Mock("cash_forecast", CashForecastResponse, cash_mock.build),
        Mock("inventory_analysis", InventoryAnalysisResponse, inventory_mock.build),
        Mock("launch_lab_winter_shawl", LaunchLabResponse, launch_mock.build),
        Mock("findings", FindingsResponse, _feed),
        Mock("decision_debt_equity", DecisionResponse, decision_mocks.debt_equity),
        Mock("decision_dividend", DecisionResponse, decision_mocks.dividend),
        Mock("payment_timing", PaymentTimingResponse, decision_mocks.payment_timing),
        Mock("financing_match", FinancingMatchResponse, financing_mocks.build),
    )
}


@cache
def load(name: str) -> BaseModel:
    """The committed fixture, validated against its response model."""
    mock = MOCKS[name]
    return mock.model.model_validate_json(mock.path.read_text(encoding="utf-8"))


def write_everything() -> list[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for mock in MOCKS.values():
        mock.path.write_text(dump(mock.build()), encoding="utf-8", newline="\n")
        written.append(mock.path)
    return written
