import pytest

from crapssim_control.engine_adapter import VanillaAdapter


crapssim = pytest.importorskip("crapssim")


def _live():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": True}}})
    return adapter


def test_live_step_roll_basic():
    adapter = _live()
    result = adapter.step_roll(dice=(3, 4))
    assert result["status"] == "ok"
    snap = result["snapshot"]
    assert "bankroll_after" in snap
    assert "dice" in snap
