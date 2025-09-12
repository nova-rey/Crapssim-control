# tests/test_tracker_batch2.py

from crapssim_control.tracker import Tracker

def test_batch2_comeout_and_pso_and_bankroll():
    tr = Tracker({"enabled": True})

    # Comeout 6 (not natural/craps), point establishes to 6
    tr.on_roll(6)
    tr.on_point_established(6)
    snap = tr.snapshot()
    assert snap["roll"]["comeout_rolls"] == 1
    assert snap["roll"]["comeout_naturals"] == 0
    assert snap["roll"]["comeout_craps"] == 0
    assert snap["point"]["point"] == 6
    assert snap["roll"]["rolls_since_point"] == 0

    # One roll after point (PSO if seven-out next)
    tr.on_roll(8)
    snap = tr.snapshot()
    assert snap["roll"]["rolls_since_point"] == 1
    assert snap["hits"][8] == 1

    # Bankroll +15 win (e.g., place 8)
    tr.on_bankroll_delta(15.0)
    snap = tr.snapshot()
    assert snap["bankroll"]["bankroll"] == 15.0
    assert snap["bankroll"]["bankroll_peak"] == 15.0
    assert snap["bankroll"]["drawdown"] == 0.0
    assert snap["bankroll"]["pnl_since_point"] == 15.0

    # Seven-out now → PSO increments, hand increments, point turns off
    tr.on_seven_out()
    snap = tr.snapshot()
    assert snap["session"]["pso"] == 1
    assert snap["session"]["seven_outs"] == 1
    assert snap["session"]["hands"] == 1
    assert snap["point"]["point"] == 0
    assert snap["roll"]["rolls_since_point"] == 0
    # PnL since point resets for next hand
    assert snap["bankroll"]["pnl_since_point"] == 0.0