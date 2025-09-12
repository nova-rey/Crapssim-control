import pytest

from bet_ledger import BetLedger


def test_place_and_resolve_and_snapshot():
    led = BetLedger()

    # Place two bets: place-8 for 12, pass line for 10
    e1 = led.place("place 8", 12, number=8)
    e2 = led.place("pass", 10)

    snap = led.snapshot()
    assert snap["open_count"] == 2
    assert snap["closed_count"] == 0
    assert snap["open_exposure"] == 22.0
    # Category exposure should reflect open bets
    by_cat = snap["by_category"]["exposure"]
    assert by_cat.get("place", 0.0) == 12.0
    assert by_cat.get("line", 0.0) == 10.0

    # Resolve place-8 as a win paying 21 back (win 9)
    eid, pnl = led.resolve("place 8", result="win", payout=21.0, number=8)
    assert eid == e1
    assert pytest.approx(pnl, rel=1e-6) == 9.0

    snap = led.snapshot()
    assert snap["open_count"] == 1
    assert snap["closed_count"] == 1
    assert snap["open_exposure"] == 10.0  # only pass line remains
    assert pytest.approx(snap["realized_pnl"], rel=1e-6) == 9.0

    # Start a point cycle, then resolve pass as a loss (-10) and ensure attribution
    led.begin_point_cycle()
    _, pnl2 = led.resolve("pass", result="lose", payout=0.0)
    assert pnl2 == -10.0

    snap = led.snapshot()
    assert snap["open_count"] == 0
    assert pytest.approx(snap["realized_pnl"], rel=1e-6) == -1.0  # 9 - 10
    assert pytest.approx(snap["realized_pnl_since_point"], rel=1e-6) == -10.0

    # End cycle resets the since-point number
    led.end_point_cycle()
    snap = led.snapshot()
    assert snap["realized_pnl_since_point"] == 0.0


def test_roll_linkage_metadata_roundtrip():
    led = BetLedger()

    # Link to roll index when opening
    led.touch_roll(roll_index=1)
    e1 = led.place("place 6", 12, number=6)

    # Link to another roll index when closing
    led.touch_roll(roll_index=2)
    led.resolve("place 6", result="win", payout=14.0, number=6)  # win 2

    # Verify metadata captured both indices
    snap = led.snapshot()
    assert snap["closed_count"] == 1
    closed = snap["closed"][0]
    assert closed["meta"].get("roll_index_opened") == 1
    assert closed["meta"].get("roll_index_closed") == 2