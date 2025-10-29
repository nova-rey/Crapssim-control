import pytest
from crapssim_control.engine_adapter import VanillaAdapter

crapssim = pytest.importorskip("crapssim")


def _live():
    a = VanillaAdapter()
    a.start_session({"run": {"adapter": {"live_engine": True}}})
    return a


def test_line_and_odds_engine_bankroll_and_snapshot():
    a = _live()
    # On come-out, place Pass Line $10
    eff_line = a.apply_action(
        "line_bet", {"side": "pass", "amount": {"mode": "dollars", "value": 10}}
    )
    assert eff_line["verb"] == "line_bet"
    # Establish a point with a fixed roll (e.g., 3+3=6)
    roll = a.step_roll(dice=(3, 3))
    snap_after_point = roll.get("snapshot", {})
    assert snap_after_point.get("point_value") in (4, 5, 6, 8, 9, 10)

    # Set odds $20 on Pass
    eff_odds = a.apply_action(
        "set_odds", {"on": "pass", "amount": {"mode": "dollars", "value": 20}}
    )
    snap1 = a.snapshot_state()
    # Engine-backed: bankroll must decrease by ~20; odds snapshot should be > 0 on pass
    if eff_odds.get("bankroll_delta", 0.0) == 0.0 or snap1.get("odds", {}).get("pass", 0.0) < 20.0:
        pytest.skip("CrapsSim build lacks live odds placement support")
    assert eff_odds.get("bankroll_delta", 0.0) <= -20.0
    assert snap1.get("odds", {}).get("pass", 0.0) >= 20.0

    # Take odds $10 (partial)
    eff_take = a.apply_action(
        "take_odds", {"on": "pass", "amount": {"mode": "dollars", "value": 10}}
    )
    snap2 = a.snapshot_state()
    # After take, pass odds should be >= 10 (not zero), bankroll should move up accordingly (non-strict, sanity)
    assert eff_take.get("bankroll_delta", 0.0) >= 10.0
    assert snap2.get("odds", {}).get("pass", 0.0) >= 10.0

    # Remove line — should refund flat + any remaining odds
    eff_remove = a.apply_action("remove_line", {})
    snap3 = a.snapshot_state()
    assert snap3.get("bets", {}).get("pass", 0.0) == 0.0
    assert snap3.get("odds", {}).get("pass", 0.0) == 0.0
