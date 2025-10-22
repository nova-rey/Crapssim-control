import pytest


crapssim = pytest.importorskip("crapssim")


def _live_adapter():
    from crapssim_control.engine_adapter import VanillaAdapter

    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": True}}})
    return adapter


def test_ats_bet_flow():
    adapter = _live_adapter()
    result = adapter.apply_action("ats_small_bet", {"amount": 5})
    assert result["verb"] == "ats_small_bet"
    snapshot = adapter.snapshot_state()
    assert "ats_small" in snapshot.get("bets", {})


def test_snapshot_ats_progress():
    adapter = _live_adapter()
    adapter.apply_action("ats_all_bet", {"amount": 10})
    snapshot = adapter.snapshot_state()
    assert "ats_progress" in snapshot


def test_capabilities_truthful():
    from crapssim_control.capabilities import get_capabilities

    capabilities = get_capabilities()
    assert "bonus" in capabilities["verbs"]
    assert capabilities["supported"]["ats_all_bet"]


def test_manifest_includes_capabilities():
    from crapssim_control.manifest import build_manifest

    manifest = build_manifest("run_123", {})
    assert "capabilities" in manifest
    assert manifest["capabilities_schema_version"] == "1.0"
