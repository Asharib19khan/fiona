"""The Python side of the contracts: full validation, Pydantic parsing and the verdict hash."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fiona_contracts import (
    ContractError,
    Figure,
    LedgerEvent,
    Mandate,
    Proposal,
    ProposalDraft,
    Verdict,
    canonical_json,
    definitions,
    validate,
    verdict_hash,
)

CONTRACTS = Path(__file__).resolve().parents[2]
EXAMPLES = CONTRACTS / "examples"
FIXTURES = CONTRACTS.parents[1] / "data" / "fixtures"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.name)
def test_every_example_validates(path: Path) -> None:
    validate(path.name.split(".")[0], load(path))


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "scenarios").glob("*.json")), ids=lambda p: p.name
)
def test_scenarios_parse_and_their_hash_recomputes(path: Path) -> None:
    data = load(path)
    validate("Proposal", data["proposal"])
    validate("Verdict", data["verdict"])
    Proposal.model_validate(data["proposal"])
    verdict = Verdict.model_validate(data["verdict"])
    assert verdict_hash(data["verdict"]) == data["verdict"]["verdict_hash"]
    # A parsed-and-dumped verdict hashes the same, so services can hash their own models.
    assert (
        verdict_hash(verdict.model_dump(mode="json", exclude_unset=True))
        == data["verdict"]["verdict_hash"]
    )


def test_changing_any_field_changes_the_hash() -> None:
    verdict = load(EXAMPLES / "scenarios" / "planted-bill-block.json")["verdict"]
    tampered = {**verdict, "outcome": "approve"}
    assert verdict_hash(tampered) != verdict["verdict_hash"]


def test_the_discriminated_union_picks_the_right_type() -> None:
    draft = ProposalDraft.model_validate(load(EXAMPLES / "ProposalDraft.payment.json"))
    assert type(draft.root).__name__ == "PaymentProposalDraft"
    assert draft.root.payload.payee_id == "sup_017"


def test_shapes_are_strict() -> None:
    with pytest.raises(ContractError):
        validate("Money", {"minor": 1.5, "currency": "PKR"})
    with pytest.raises(ContractError):
        validate(
            "Figure",
            {
                "metric_id": "x",
                "label": "x",
                "value": 1,
                "money": {"minor": 1, "currency": "PKR"},
                "unit": "minor",
            },
        )
    with pytest.raises(ContractError):
        validate(
            "Check",
            {"name": "policy", "rule": "G-01", "result": "pass", "outcome": "block", "detail": "x"},
        )
    with pytest.raises(ValueError):
        Mandate.model_validate({**load(EXAMPLES / "Mandate.treasurer.json"), "unexpected": 1})


def test_figure_model_round_trips() -> None:
    fig = Figure.model_validate(load(EXAMPLES / "Figure.dscr.json"))
    assert fig.value == 13500 and fig.unit == "bp"


def test_canonical_json_refuses_floats() -> None:
    assert canonical_json({"b": 1, "a": [True, None]}) == '{"a":[true,null],"b":1}'
    with pytest.raises(TypeError):
        canonical_json({"amount": 1.5})


def test_the_core_contracts_exist() -> None:
    core = {
        "Money",
        "Figure",
        "Finding",
        "Proposal",
        "ProposalDraft",
        "Verdict",
        "Check",
        "Mandate",
        "LedgerEvent",
    }
    assert core <= set(definitions())


@pytest.mark.parametrize(
    "events", sorted(FIXTURES.glob("*/events.jsonl")), ids=lambda p: p.parent.name
)
def test_fixture_ledger_events_match_the_contract(events: Path) -> None:
    lines = events.read_text(encoding="utf-8").splitlines()
    assert lines, "no events"
    for n, line in enumerate(lines, start=1):
        event = json.loads(line)
        try:
            validate("LedgerEvent", event)
            LedgerEvent.model_validate(event)
        except (ContractError, ValueError) as exc:  # pragma: no cover - the message is the point
            pytest.fail(f"{events.parent.name} events.jsonl line {n} ({event.get('event')}): {exc}")
