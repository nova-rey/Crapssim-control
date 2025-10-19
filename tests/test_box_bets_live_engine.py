import pytest
from crapssim_control.engine_adapter import VanillaAdapter

crapssim = pytest.importorskip("crapssim")

def _mk_live_adapter():
    a = VanillaAdapter()
    a.start_session({"run": {"adapter": {"live_engine": True}}})
    a.set_seed(2468)
    return a

def test_place_6_and_move_to_8_live():
    a = _mk_live_adapter()
    eff1 = a.apply_action("place_bet", {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}})
    assert eff1["verb"] == "place_bet" and "+6" in eff1["bets"].get("6", "")
    eff2 = a.apply_action("move_bet", {"target": {"from": "6", "to": "8"}})
    assert eff2["verb"] == "move_bet"
    snap = a.snapshot_state()
    assert snap["bets"].get("6", 0.0) == 0.0
    assert snap["bets"].get("8", 0.0) >= 6.0

def test_buy_4_then_take_down_live():
    a = _mk_live_adapter()
    eff1 = a.apply_action("buy_bet", {"target": {"bet": "4"}, "amount": {"mode": "dollars", "value": 25}})
    assert eff1["verb"] == "buy_bet"
    eff2 = a.apply_action("take_down", {"target": {"selector": ["4"]}})
    assert eff2["verb"] == "take_down"
    snap = a.snapshot_state()
    assert snap["bets"].get("4", 0.0) == 0.0
