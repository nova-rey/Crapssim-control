from crapssim_control.tracker import Tracker


def test_point_cycle_hits_and_resets():
    tr = Tracker({"enabled": True})

    # Establish point 6
    tr.on_point_established(6)
    snap = tr.snapshot()
    assert snap["point"]["point"] == 6
    assert snap["roll"]["rolls_since_point"] == 0
    assert snap["bankroll"]["pnl_since_point"] == 0.0
    assert snap["since_point"]["inside_hits"] == 0
    assert snap["since_point"]["outside_hits"] == 0
    assert snap["since_point"]["hits"] == {}

    # Two inside rolls (8, then 5), one outside roll (4)
    tr.on_roll(8)
    tr.on_roll(5)
    tr.on_roll(4)
    tr.on_bankroll_delta(15.0)  # attribute to current point cycle

    snap = tr.snapshot()
    assert snap["roll"]["rolls_since_point"] == 3
    assert snap["since_point"]["inside_hits"] == 2  # 8 and 5
    assert snap["since_point"]["outside_hits"] == 1  # 4
    assert snap["since_point"]["hits"][8] == 1
    assert snap["since_point"]["hits"][5] == 1
    assert snap["since_point"]["hits"][4] == 1
    assert snap["bankroll"]["pnl_since_point"] == 15.0

    # Make the point -> counters reset
    tr.on_point_made()
    snap = tr.snapshot()
    assert snap["point"]["point"] == 0
    assert snap["roll"]["rolls_since_point"] == 0
    assert snap["bankroll"]["pnl_since_point"] == 0.0
    assert snap["since_point"]["hits"] == {}
    assert snap["since_point"]["inside_hits"] == 0
    assert snap["since_point"]["outside_hits"] == 0

    # Establish a new point and verify seven-out also resets
    tr.on_point_established(5)
    tr.on_roll(6)
    tr.on_roll(9)
    tr.on_bankroll_delta(-10.0)
    snap = tr.snapshot()
    assert snap["roll"]["rolls_since_point"] == 2
    assert snap["bankroll"]["pnl_since_point"] == -10.0

    tr.on_seven_out()
    snap = tr.snapshot()
    assert snap["point"]["point"] == 0
    assert snap["roll"]["rolls_since_point"] == 0
    assert snap["bankroll"]["pnl_since_point"] == 0.0
    assert snap["since_point"]["hits"] == {}
