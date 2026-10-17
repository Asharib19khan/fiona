"""Fixture-backed regression coverage for the Y10 financing matcher."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from engine.app.main import create_app
from engine.financing.business import business_figures
from engine.financing.matcher import match_financing, schedule
from engine.financing.schemas import BusinessProfile, FinancingMatchRequest
from engine.forecast._contracts import Money
from engine.forecast.ledger_source import load_fixture_snapshot

TENANT = "ten_karachi_apparel"
NOW = datetime(2026, 10, 22, 4, tzinfo=UTC)


@pytest.fixture
def snapshot():
    return load_fixture_snapshot(TENANT)


@pytest.fixture
def matching(snapshot):
    def run(**changes):
        request = FinancingMatchRequest(
            amount=Money(minor=200_000_000, currency="PKR"),
            purpose="working_capital_seasonal",
            **changes,
        )
        return match_financing(
            request,
            business_figures(snapshot),
            tenant_id=TENANT,
            as_of=snapshot.as_of,
            mode="mock",
            generated_at=NOW,
        )

    return run


def _option(result, option_id: str):
    return next(option for option in result.options if option.option_id == option_id)


def test_fixture_match_ranks_eligible_options_by_cost(matching):
    result = matching()

    ranked = [option for option in result.options if option.rank is not None]
    assert [option.rank for option in ranked] == list(range(1, len(ranked) + 1))
    assert ranked[0].option_id == "pk_supplier_credit"
    assert ranked[0].outcome == "recommended"


def test_hard_amount_rule_makes_tier_one_ineligible(matching):
    option = _option(matching(), "pk_pmybals_t1")

    assert option.eligible is False
    assert option.outcome == "ineligible"
    assert option.max_amount == Money(minor=50_000_000, currency="PKR")


def test_missing_profile_input_is_reported_with_a_readable_label(matching):
    result = matching(profile=BusinessProfile(size_tier=None))

    gap = next(gap for gap in result.insufficient_data if gap.metric_ids == ["profile.size_tier"])
    assert gap.need == "the business's size tier"


def test_null_catalogue_pricing_is_cost_unknown(matching):
    option = _option(
        matching(profile=BusinessProfile(size_tier="micro")), "pk_microfinance_bank_loan"
    )

    assert option.outcome == "cost_unknown"
    figure = next(
        figure
        for figure in option.figures
        if figure.metric_id == "financing.effective_annual_cost.mid"
    )
    assert figure.status == "insufficient_data"


def test_dscr_failure_offers_a_smaller_size(matching):
    option = _option(matching(), "pk_running_finance")

    assert option.eligible is True
    assert option.outcome == "possible_at_smaller_size"
    assert option.max_amount is not None
    assert option.max_amount.minor < 200_000_000


def test_invoice_discounting_dscr_counts_interest_without_bullet_principal():
    option = {"type": "invoice_discounting", "repayment": {"style": "bullet"}}

    result = schedule(option, amount=12_000, rate_bp=1_200, fee_bp=0, tenor=6)

    assert result.flows[6] == -12_720
    assert result.service_12m == 720


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIONA_MODE", "mock")
    return TestClient(create_app(modules=["financing"]))


def test_financing_api_uses_fixture_and_rejects_incompatible_snapshot(client):
    body = {
        "amount": {"minor": 200_000_000, "currency": "PKR"},
        "purpose": "working_capital_seasonal",
    }
    result = client.post("/v1/financing/match", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["as_of"] == "2026-10-22"
    assert result.json()["options"][0]["option_id"] == "pk_supplier_credit"

    dated = client.post(
        "/v1/financing/match", json={**body, "as_of": date(2026, 10, 21).isoformat()}
    )
    assert dated.status_code == 422
    assert dated.json()["error"]["code"] == "unsupported_as_of"

    wrong_currency = client.post(
        "/v1/financing/match",
        json={**body, "amount": {"minor": 200_000_000, "currency": "USD"}},
    )
    assert wrong_currency.status_code == 422
    assert wrong_currency.json()["error"]["code"] == "invalid_financing_request"


def test_approved_ebitda_handoff_replaces_operating_cash_proxy(snapshot):
    """When approved EBITDA is supplied from engine.analysis, figures use Origin.LEDGER instead of Origin.STUB."""
    from engine.forecast._contracts import Origin

    # 1. Default fallback uses operating cash proxy with Origin.STUB
    biz_proxy = business_figures(snapshot)
    assert biz_proxy.ebitda_source == "operating_cash_proxy"
    req = FinancingMatchRequest(
        amount=Money(minor=200_000_000, currency="PKR"),
        purpose="working_capital_seasonal",
    )
    res_proxy = match_financing(
        req, biz_proxy, tenant_id=TENANT, as_of=snapshot.as_of, mode="mock", generated_at=NOW
    )
    opt_proxy = _option(res_proxy, "pk_running_finance")
    dscr_fig_proxy = next(f for f in opt_proxy.figures if f.metric_id == "financing.dscr_after")
    ebitda_inp_proxy = next(i for i in dscr_fig_proxy.inputs if i.name == "ebitda_next_12m")
    assert ebitda_inp_proxy.origin == Origin.STUB
    assert "bank statement: operating cash flow" in (ebitda_inp_proxy.ref or "")

    # 2. Approved EBITDA from analysis handoff uses Origin.LEDGER with official statement ref
    biz_approved = business_figures(snapshot, approved_ebitda_minor=320_000_000)
    assert biz_approved.ebitda_source == "approved_ebitda"
    assert biz_approved.ebitda_next_12m_minor == 320_000_000

    res_approved = match_financing(
        req, biz_approved, tenant_id=TENANT, as_of=snapshot.as_of, mode="mock", generated_at=NOW
    )
    opt_approved = _option(res_approved, "pk_running_finance")
    dscr_fig_approved = next(
        f for f in opt_approved.figures if f.metric_id == "financing.dscr_after"
    )
    ebitda_inp_approved = next(i for i in dscr_fig_approved.inputs if i.name == "ebitda_next_12m")
    assert ebitda_inp_approved.origin == Origin.LEDGER
    assert "approved EBITDA" in (ebitda_inp_approved.ref or "")
    assert ebitda_inp_approved.money is not None
    assert ebitda_inp_approved.money.minor == 320_000_000
