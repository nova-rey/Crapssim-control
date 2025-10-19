from crapssim_control.engine_adapter import VanillaAdapter


def _mk_stub_adapter():
    a = VanillaAdapter()
    a.start_session({"run": {"adapter": {"live_engine": False}}})
    a.set_seed(13579)
    return a


def test_place_buy_lay_move_take_down_fallback():
    a = _mk_stub_adapter()
    a.apply_action("place_bet", {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}})
    a.apply_action("buy_bet", {"target": {"bet": "4"}, "amount": {"mode": "dollars", "value": 25}})
    a.apply_action("lay_bet", {"target": {"bet": "10"}, "amount": {"mode": "dollars", "value": 20}})
    a.apply_action("move_bet", {"target": {"from": "6", "to": "8"}})
    snap = a.snapshot_state()
    assert snap["bets"]["8"] >= 6.0
    assert snap["bets"]["4"] >= 25.0
    assert snap["bets"]["10"] >= 20.0
    a.apply_action("take_down", {"target": {"selector": ["4", "8", "10"]}})
    snap2 = a.snapshot_state()
    assert snap2["bets"].get("4", 0.0) == 0.0
    assert snap2["bets"].get("8", 0.0) == 0.0
    assert snap2["bets"].get("10", 0.0) == 0.0
