# tests/test_tracker_core.py
from crapssim_control.tracker import Tracker

def test_tracker_roll_point_bankroll_flow():
    tr = Tracker({"enabled": True})
    # Start: comeout roll 6 → point established
    tr.on_roll(6)
    tr.on_point_established(6)

    snap = tr.snapshot()
    assert snap["roll"]["last_roll"] == 6
    assert snap["point"]["point"] == 6
    assert snap["roll"]["rolls_since_point"] == 0

    # Two more inside rolls
    tr.on_roll(8)
    tr.on_roll(5)
    snap = tr.snapshot()
    assert snap["roll"]["shooter_rolls"] == 3
    assert snap["roll"]["rolls_since_point"] == 2
    assert snap["hits"][8] == 1
    assert snap["hits"][5] == 1

    # Bankroll win +15 on that 5
    tr.on_bankroll_delta(15.0)
    snap = tr.snapshot()
    assert snap["bankroll"]["bankroll"] == 15.0
    assert snap["bankroll"]["bankroll_peak"] == 15.0
    assert snap["bankroll"]["drawdown"] == 0.0
    assert snap["bankroll"]["pnl_since_point"] == 15.0

    # Seven-out
    tr.on_seven_out()
    snap = tr.snapshot()
    assert snap["point"]["point"] == 0
    assert snap["session"]["seven_outs"] == 1
    assert snap["roll"]["rolls_since_point"] == 0
    # New shooter context should reset shooter_rolls
    assert snap["roll"]["shooter_rolls"] == 0