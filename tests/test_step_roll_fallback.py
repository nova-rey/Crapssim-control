from crapssim_control.engine_adapter import VanillaAdapter


def _stub():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": False}}})
    return adapter


def test_fallback_roll_generates_consistent_state():
    adapter = _stub()
    first = adapter.step_roll(seed=123)
    second = adapter.step_roll(seed=123)
    assert first["total"] == second["total"]
    assert "snapshot" in first
