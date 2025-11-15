"""Tests for the CrapsSim HTTP engine adapter."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
fastapi_testclient = pytest.importorskip("fastapi.testclient")
crapssim_http = pytest.importorskip("crapssim_api.http")

from crapssim_control.engine.http_api_adapter import HttpEngineAdapter
from crapssim_control.manifest import build_manifest

FastAPI = fastapi.FastAPI
TestClient = fastapi_testclient.TestClient
router = getattr(crapssim_http, "router", None)

if router is None:  # pragma: no cover - fastapi extras missing
    pytest.skip("crapssim_api router unavailable", allow_module_level=True)


def _make_adapter(seed: int = 314159) -> tuple[HttpEngineAdapter, TestClient]:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    adapter = HttpEngineAdapter(base_url=str(client.base_url), client=client)
    adapter.start_session({"run": {}}, seed=seed)
    return adapter, client


def test_http_adapter_can_start_and_step_session():
    adapter, _client = _make_adapter()
    snapshot = adapter.snapshot_state()
    assert snapshot["session_id"]
    assert snapshot["bankroll"] is not None
    result = adapter.step_roll(dice=(3, 3))
    assert "dice" in result
    assert result["dice"] == (3, 3)


def test_http_adapter_can_apply_simple_action():
    adapter, _client = _make_adapter()
    response = adapter.apply_action("pass_line", {"amount": 10})
    effect = response["effect_summary"]
    assert effect["verb"] == "pass_line"
    assert effect.get("applied") in {None, True}
    snapshot = response["snapshot"]
    assert any(bet for bet in snapshot["bets_raw"] if bet.get("type") == "PassLine")


def test_http_adapter_populates_engine_info_in_manifest():
    adapter, _client = _make_adapter()
    manifest = build_manifest("run-test", {}, adapter=adapter)
    engine_info = manifest.get("engine_info", {})
    assert engine_info.get("engine_type") == "http_api"
    assert "base_url" in engine_info
