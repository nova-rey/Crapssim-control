from crapssim_control.tracker import Tracker
from crapssim_control.bet_attrib import attach_bet_attrib


def _approx(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def test_bet_attrib_tallies_when_enabled():
    # Use explicit override because Tracker may not retain unknown config keys.
    tr = Tracker({"enabled": True})
    attach_bet_attrib(tr, enabled=True)

    # Simulate several independent bet resolutions
    # Pass line win +10
    tr.on_bet_resolved({"bet_type": "pass_line", "pnl": 10.0, "outcome": "win"})

    # Place 6 win +7, then later a loss -12
    tr.on_bet_resolved({"bet_type": "place_6", "pnl": 7.0, "outcome": "win"})
    tr.on_bet_resolved({"bet_type": "place_6", "pnl": -12.0, "outcome": "loss"})

    # Field loss (no pnl provided; infer -5 from stake)
    tr.on_bet_resolved({"bet_type": "field", "outcome": "loss", "stake": 5})

    snap = tr.snapshot()
    assert "bet_attrib" in snap
    by_type = snap["bet_attrib"]["by_bet_type"]

    # Pass line
    assert by_type["pass_line"]["wins"] == 1
    assert by_type["pass_line"]["losses"] == 0
    assert _approx(by_type["pass_line"]["pnl"], 10.0)

    # Place 6
    assert by_type["place_6"]["wins"] == 1
    assert by_type["place_6"]["losses"] == 1
    assert _approx(by_type["place_6"]["pnl"], -5.0)  # +7 - 12

    # Field
    assert by_type["field"]["wins"] == 0
    assert by_type["field"]["losses"] == 1
    assert _approx(by_type["field"]["pnl"], -5.0)


def test_bet_attrib_absent_when_disabled():
    tr = Tracker({"enabled": True})
    attach_bet_attrib(tr, enabled=False)

    # Even if we send events, attribution is disabled → no side effects in snapshot
    tr.on_bet_resolved({"bet_type": "pass_line", "pnl": 10.0, "outcome": "win"})
    tr.on_bet_resolved({"bet_type": "field", "outcome": "loss", "stake": 5})

    snap = tr.snapshot()
    assert "bet_attrib" not in snap
