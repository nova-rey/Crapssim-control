import types
import importlib


def test_ats_tolerant_resolution(monkeypatch):
    # Simulate crapssim.bet exposing plain All/Small/Tall only
    fake_bet = types.SimpleNamespace(
        All=type("All", (object,), {"__init__": lambda self, *a, **k: None}),
        Small=type("Small", (object,), {"__init__": lambda self, *a, **k: None}),
        Tall=type("Tall", (object,), {"__init__": lambda self, *a, **k: None}),
        # No ATSAll/ATSSmall/ATSTall present
    )
    from crapssim_control import engine_adapter

    monkeypatch.setattr(engine_adapter, "cs_bet", fake_bet, raising=False)
    monkeypatch.setitem(importlib.sys.modules, "crapssim.bet", fake_bet)

    adapter = engine_adapter.VanillaAdapter()
    adapter.start_session(
        {"run": {"adapter": {"live_engine": False}}}
    )  # stub mode ok for resolution test
    # Just ensure the handler does not raise on class lookup (placement may no-op in stub path)
    res = adapter.apply_action("ats_all_bet", {"amount": {"mode": "dollars", "value": 10}})
    assert isinstance(res, dict) and ("rejected" in res or "result" in res)
