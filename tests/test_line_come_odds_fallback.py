from crapssim_control.engine_adapter import VanillaAdapter


def _stub():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": False}}})
    return adapter


def test_line_and_odds_fallback():
    adapter = _stub()
    adapter.apply_action("line_bet", {"side": "pass", "amount": {"mode": "dollars", "value": 10}})
    adapter.apply_action("set_odds", {"on": "pass", "amount": {"mode": "dollars", "value": 20}})
    snap = adapter.snapshot_state()
    assert snap["bets"].get("pass", 0.0) >= 10.0


def test_dc_remove_fallback():
    adapter = _stub()
    adapter.apply_action("dont_come_bet", {"amount": {"mode": "dollars", "value": 5}})
    adapter.apply_action("remove_dont_come", {})
    snap = adapter.snapshot_state()
    assert snap["bankroll"] >= 0.0
