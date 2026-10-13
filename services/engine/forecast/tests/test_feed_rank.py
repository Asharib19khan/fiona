from datetime import UTC, datetime

from engine.forecast._contracts import Finding, Money
from engine.forecast.feed.rank import rank_findings


def _f(key, minor, severity="medium", hour=0):
    return Finding(
        id=f"fnd_{key}_{hour}",
        source="forecast",
        severity=severity,
        title=key,
        money_at_stake=Money(minor=minor, currency="PKR"),
        evidence=[],
        actions=[],
        type=key,
        created_at=datetime(2026, 10, 22, hour, tzinfo=UTC),
        dedupe_key=key,
    )


def test_ranked_by_money_then_severity():
    ranked = rank_findings([_f("a", 100), _f("b", 500), _f("c", 100, "high")])
    assert [f.dedupe_key for f in ranked] == ["b", "c", "a"]


def test_duplicates_keep_the_newest():
    ranked = rank_findings([_f("a", 100, hour=1), _f("a", 900, hour=3), _f("a", 50, hour=2)])
    assert len(ranked) == 1 and ranked[0].money_at_stake.minor == 900
