# -*- coding: utf-8 -*-
import math
from crapssim_control.tracker import Tracker

def test_bankroll_extras_flag_off_is_noop():
    tr = Tracker({"enabled": True, "bankroll_extras_enabled": False})
    tr.on_bankroll_delta(25.0)
    tr.on_bankroll_delta(-10.0)
    tr.on_seven_out()  # would log a hand if extras were on

    snap = tr.snapshot()
    # Base fields exist…
    assert "bankroll" in snap and "session" in snap

    # …but extras do not appear when flag is off
    assert "max_drawdown" not in snap["bankroll"]
    assert "recovery_factor" not in snap["bankroll"]
    assert "pnl_log" not in snap["bankroll"]


def test_bankroll_extras_basic_flow_and_logging():
    tr = Tracker({"enabled": True, "bankroll_extras_enabled": True})

    # Hand starts implicitly; win, then pullback; then seven-out
    tr.on_bankroll_delta(50.0)   # bankroll=50, peak=50, drawdown=0
    tr.on_bankroll_delta(-20.0)  # bankroll=30, peak=50, drawdown=20 (max_dd=20)
    tr.on_seven_out()            # hand ends, pnl_log should capture +30

    snap = tr.snapshot()
    b = snap["bankroll"]
    assert math.isclose(b["bankroll"], 30.0)
    assert math.isclose(b["bankroll_peak"], 50.0)
    assert math.isclose(b["drawdown"], 20.0)
    assert math.isclose(b["max_drawdown"], 20.0)

    # recovery_factor = net_profit / max_drawdown = 30 / 20 = 1.5
    assert math.isclose(b["recovery_factor"], 1.5, rel_tol=1e-9)
    assert b["pnl_log"] == [30.0]

    # Start second hand: a drawdown that grows, then partial recovery
    tr.on_bankroll_delta(-10.0)  # 20, peak=50, drawdown=30 (max_dd grows to 30)
    tr.on_bankroll_delta(5.0)    # 25, drawdown=25, max_dd stays 30
    tr.on_seven_out()

    snap2 = tr.snapshot()
    b2 = snap2["bankroll"]
    assert math.isclose(b2["bankroll"], 25.0)
    assert math.isclose(b2["max_drawdown"], 30.0)
    # recovery_factor = 25 / 30 ≈ 0.8333333
    assert math.isclose(b2["recovery_factor"], 25.0/30.0, rel_tol=1e-9)
    # second hand PnL = -5
    assert b2["pnl_log"] == [30.0, -5.0]


def test_bankroll_extras_respect_point_cycle_pnl_since_point():
    tr = Tracker({"enabled": True, "bankroll_extras_enabled": True})
    # Point on
    tr.on_point_established(6)
    tr.on_roll(8)  # non-comeout, since-point counters accrue
    tr.on_bankroll_delta(15.0)
    snap = tr.snapshot()
    # Base since-point still works with extras enabled
    assert snap["bankroll"]["pnl_since_point"] == 15.0
    # Extras present
    assert "max_drawdown" in snap["bankroll"]
    assert "recovery_factor" in snap["bankroll"]
    assert "pnl_log" in snap["bankroll"]