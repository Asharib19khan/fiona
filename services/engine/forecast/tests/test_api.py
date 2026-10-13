"""Yahya-lane routers mounted in the real engine app."""

import pytest
from fastapi.testclient import TestClient

from engine.app.main import create_app

MODULES = ["decisions", "financing", "forecast"]
T = "ten_karachi_apparel"
PKR = {"currency": "PKR"}

GETS = [
    "/v1/forecast/cash?weeks=13",
    "/v1/forecast/findings",
    "/v1/inventory/analysis",
]
POSTS = [
    (
        "/v1/launch-lab/simulate",
        {
            "currency": "PKR",
            "product": {"name": "Winter shawl", "category": "shawl"},
            "unit_cost": {"minor": 240000, **PKR},
            "price": {"minor": 450000, **PKR},
        },
    ),
    (
        "/v1/decisions/debt-equity",
        {"amount": {"minor": 200000000, **PKR}, "purpose": "winter stock"},
    ),
    ("/v1/decisions/dividend", {"proposed_dividend": {"minor": 150000000, **PKR}}),
    ("/v1/decisions/payment-timing", {}),
    (
        "/v1/financing/match",
        {
            "amount": {"minor": 200000000, **PKR},
            "purpose": "working_capital_seasonal",
        },
    ),
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIONA_MODE", "mock")
    return TestClient(create_app(modules=MODULES))


@pytest.mark.parametrize("path", GETS)
def test_get_endpoints_serve_mocks(client, path):
    res = client.get(path)
    assert res.status_code == 200, res.text
    assert res.json()["api_version"] == "v1"


@pytest.mark.parametrize(("path", "body"), POSTS)
def test_post_endpoints_serve_mocks(client, path, body):
    res = client.post(path, json=body)
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "mock"


def test_unknown_tenant_is_404(client):
    res = client.get("/v1/forecast/cash", headers={"X-Fiona-Tenant": "ten_nobody"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_live_mode_fails_closed_without_a_verified_tenant(monkeypatch):
    monkeypatch.setenv("FIONA_MODE", "live")
    res = TestClient(create_app(modules=MODULES)).get("/v1/forecast/cash")
    assert res.status_code == 401


def test_tenant_never_comes_from_the_query_string(client):
    res = client.get("/v1/forecast/cash", params={"tenant_id": "ten_nobody"})
    assert res.status_code == 200
    assert res.json()["tenant_id"] == T


@pytest.mark.parametrize(
    "bad",
    [
        {"price": {"minor": 450000, "currency": "USD"}},  # mixed currencies
        {"price": {"minor": 4500.5, **PKR}},  # float money
        {"duty_rate_bp": 12000},  # rate above 100%
        {"payment_fee_rate_bp": 6000, "marketplace_fee_rate_bp": 5000},  # fees eat the price
    ],
)
def test_launch_lab_rejects_invalid_requests(client, bad):
    body = {**POSTS[0][1], **bad}
    assert client.post("/v1/launch-lab/simulate", json=body).status_code == 422
