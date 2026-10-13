"""The engine skeleton: health, error envelope, router auto-discovery and the 501 fallback."""

from __future__ import annotations

import sys
import types

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from engine.app.main import create_app, discover_modules


def client(modules: list[str] | None = None) -> TestClient:
    return TestClient(create_app(modules=modules))


def test_healthz_matches_the_contract_shape() -> None:
    res = client([]).get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"api_version": "v1", "status": "ok", "service": "engine"}
    assert res.headers["X-Request-Id"].startswith("req_")


def test_a_well_formed_request_id_is_echoed() -> None:
    res = client([]).get("/healthz", headers={"X-Request-Id": "req_abcdef12"})
    assert res.headers["X-Request-Id"] == "req_abcdef12"


def test_contract_path_without_a_module_answers_501_with_its_owner() -> None:
    res = client([]).get("/v1/forecast/cash?weeks=13")
    assert res.status_code == 501
    body = res.json()
    assert body["api_version"] == "v1"
    assert body["error"]["code"] == "not_implemented"
    assert body["error"]["details"] == {"module": "forecast"}
    assert body["error"]["request_id"].startswith("req_")


def test_unknown_path_answers_404_in_the_envelope() -> None:
    res = client([]).post("/v1/nowhere")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_a_module_router_is_mounted_and_wins_over_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = APIRouter()

    @router.get("/v1/stage")
    def stage() -> dict[str, str]:
        return {"api_version": "v1", "label": "Growth"}

    monkeypatch.setitem(sys.modules, "engine.fakemodule.api", types.SimpleNamespace(router=router))
    res = client(["fakemodule"]).get("/v1/stage")
    assert res.status_code == 200
    assert res.json()["label"] == "Growth"


def test_a_module_without_a_router_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "engine.badmodule.api", types.SimpleNamespace())
    with pytest.raises(TypeError, match="must expose `router`"):
        create_app(modules=["badmodule"])


def test_discovery_finds_only_folders_with_api_py(tmp_path) -> None:  # type: ignore[no-untyped-def]
    for name in ("ledger", "forecast", "app", "tests", "_private"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "api.py").write_text("")
    (tmp_path / "decisions").mkdir()  # no api.py yet
    assert discover_modules(tmp_path) == ["forecast", "ledger"]


def test_every_real_module_mounts() -> None:
    # Fails if any lane's api.py is broken, which is the point: main stays green.
    app = create_app()
    assert set(app.state.modules) == set(discover_modules())


def test_mode_must_be_mock_or_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIONA_MODE", "staging")
    with pytest.raises(RuntimeError, match="FIONA_MODE"):
        create_app(modules=[])
