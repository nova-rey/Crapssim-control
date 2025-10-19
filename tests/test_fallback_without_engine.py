import pytest

import crapssim_control.engine_adapter as engine_adapter


@pytest.fixture(autouse=True)
def _restore_resolve_engine_adapter(monkeypatch):
    original = engine_adapter.resolve_engine_adapter
    yield
    monkeypatch.setattr(engine_adapter, "resolve_engine_adapter", original)


def test_live_engine_falls_back_when_crapssim_missing(monkeypatch):
    def _no_engine():
        return None, "engine_missing"

    monkeypatch.setattr(engine_adapter, "resolve_engine_adapter", _no_engine)

    adapter = engine_adapter.VanillaAdapter()
    spec = {"run": {"adapter": {"enabled": True, "impl": "vanilla", "live_engine": True}}}
    adapter.start_session(spec)

    assert adapter.live_engine is False
    assert getattr(adapter, "_engine_adapter", None) is None

    effect = adapter.apply_action(
        "press",
        {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
    )

    assert effect["bets"]["6"] == "+6"
    snapshot = adapter.snapshot_state()
    assert pytest.approx(snapshot["bets"]["6"], rel=0, abs=0.001) == 6.0
    assert pytest.approx(snapshot["bankroll"], rel=0, abs=0.001) == 994.0
