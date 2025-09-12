import pytest

# Try to import the project's real Tracker; if it doesn't exist in this env, skip.
Tracker = pytest.importorskip("tracker").Tracker

from tracker_ledger_shim import wire_ledger


def test_wiring_adds_ledger_and_snapshot_section():
    tr = Tracker({"enabled": True})
    wire_ledger(tr)

    # Ledger should be present and snapshot should include it
    assert hasattr(tr, "ledger")
    snap = tr.snapshot()
    assert "ledger" in snap
    assert snap["ledger"]["open_count"] == 0


def test_point_cycle_bridging_and_bankroll_hook():
    tr = Tracker({"enabled": True})
    wire_ledger(tr)

    # Establish a point -> ledger begins cycle
    tr.on_point_established(6)
    # Place and then resolve a bet during the cycle, applying PnL to bankroll
    bid = tr.on_bet_placed("place 8", 12, number=8)
    tr.on_bet_resolved("place 8", result="win", payout=21.0, number=8, apply_to_bankroll=True)

    snap = tr.snapshot()
    # Bankroll should reflect the realized PnL (win 9)
    assert snap["bankroll"]["bankroll"] >= 9.0 - 1e-9
    # Ledger since-point should include the same PnL while cycle is active
    assert snap["ledger"]["realized_pnl_since_point"] >= 9.0 - 1e-9

    # Seven-out ends the cycle -> since-point resets to 0
    tr.on_seven_out()
    snap2 = tr.snapshot()
    assert snap2["ledger"]["realized_pnl_since_point"] == 0.0