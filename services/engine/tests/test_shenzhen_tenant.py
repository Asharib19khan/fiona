"""Tests for multi-tenant switching between Karachi and Shenzhen personas."""

from fastapi.testclient import TestClient

from engine.app.main import app

client = TestClient(app)


def test_tenant_switch_whoami():
    """Test switching between Karachi and Shenzhen tenant personas via HTTP header."""
    res_pk = client.get("/v1/whoami", headers={"X-Fiona-Tenant": "ten_karachi_apparel"})
    assert res_pk.status_code == 200
    assert res_pk.json()["tenant_id"] == "ten_karachi_apparel"

    res_sz = client.get("/v1/whoami", headers={"X-Fiona-Tenant": "ten_shenzhen_electronics"})
    assert res_sz.status_code == 200
    assert res_sz.json()["tenant_id"] == "ten_shenzhen_electronics"
