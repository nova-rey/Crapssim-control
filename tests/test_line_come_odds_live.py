import pytest

from crapssim_control.engine_adapter import VanillaAdapter

crapssim = pytest.importorskip("crapssim")


def _live():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": True}}})
    adapter.set_seed(8086)
    return adapter


def test_pass_line_then_odds_live_fixed_flow():
    adapter = _live()
    eff1 = adapter.apply_action(
        "line_bet",
        {"side": "pass", "amount": {"mode": "dollars", "value": 10}},
    )
    assert eff1["bets"].get("pass") == "+10"
    eff2 = adapter.apply_action(
        "set_odds",
        {"on": "pass", "amount": {"mode": "dollars", "value": 20}},
    )
    assert "odds_pass" in eff2["bets"]
    snap = adapter.snapshot_state()
    assert snap["bets"].get("pass", 0.0) >= 10.0


def test_come_then_set_odds_on_point_live():
    adapter = _live()
    adapter.apply_action("come_bet", {"amount": {"mode": "dollars", "value": 10}})
    eff = adapter.apply_action(
        "set_odds",
        {"on": "come", "point": 6, "amount": {"mode": "dollars", "value": 10}},
    )
    assert "+10" in eff["bets"].get("odds_come_6", "")
