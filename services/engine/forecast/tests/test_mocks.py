"""The committed mock fixtures: in sync with their builders, valid, and free of floats."""

import json

import pytest

from engine.forecast.mocks import dump
from engine.forecast.mocks.registry import MOCKS, load


def _floats(node, path="$"):
    if isinstance(node, float):
        yield path
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _floats(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _floats(v, f"{path}[{i}]")


@pytest.mark.parametrize("name", sorted(MOCKS))
def test_fixture_matches_builder(name):
    mock = MOCKS[name]
    assert mock.path.read_text(encoding="utf-8") == dump(mock.build()), (
        f"{mock.path.name} is stale: run `python -m engine.forecast.mocks`"
    )


@pytest.mark.parametrize("name", sorted(MOCKS))
def test_fixture_has_no_floats_and_validates(name):
    data = json.loads(MOCKS[name].path.read_text(encoding="utf-8"))
    assert list(_floats(data)) == []
    assert data["api_version"] == "v1" and data["mode"] == "mock"
    load(name)


def test_cash_mock_flags_the_planted_week_7_dip():
    cash = load("cash_forecast")
    assert cash.first_week_below_buffer == 7
    for w in cash.weeks:
        assert w.closing.minor == w.opening.minor + w.inflows.minor - w.outflows.minor
        ins = sum(x.money.minor for x in w.lines if x.direction == "in")
        assert ins == w.inflows.minor
    assert cash.findings[0].type == "cash_below_buffer"
    assert cash.findings[0].money_at_stake == cash.shortfall.money


def test_launch_lab_mock_answers_the_roadmap_question():
    """Y5 done-when: the winter-shawl scenario returns a break-even month and P(break-even)."""
    run = load("launch_lab_winter_shawl")
    headline = {f.metric_id: f for f in run.headline}
    assert headline["launch.payback_month"].status == "ok"
    assert 0 <= headline["launch.p_payback_within_horizon"].value <= 10_000
    assert run.recommendation.label in {
        "LAUNCH",
        "PILOT_FIRST",
        "REVISE",
        "HOLD",
        "NOT_RECOMMENDED",
    }
    assert {s.name for s in run.scenarios} == {"low", "base", "high"}
    assert run.simulation.interpretation == "model_based_not_calibrated"


def test_findings_feed_is_ranked_by_money_at_stake():
    feed = load("findings").findings
    stakes = [f.money_at_stake.minor for f in feed]
    assert stakes == sorted(stakes, reverse=True)
    assert len({f.dedupe_key for f in feed}) == len(feed)
