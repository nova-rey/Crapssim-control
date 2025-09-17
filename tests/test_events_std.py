# tests/test_events_std.py

from crapssim_control.events_std import EventStream


def _ev_types(seq):
    return [e["type"] for e in seq]


def test_basic_hand_flow_with_point_and_seven_out():
    es = EventStream()
    es.new_shooter(1)

    # Comeout roll establishes a point (6)
    es.roll(6, (3, 3))
    out = list(es.flush())
    assert _ev_types(out) == ["shooter_change", "comeout", "roll", "point_established"]
    assert out[-1]["point"] == 6

    # A couple of inside rolls while point is on
    es.roll(8, (4, 4))
    es.roll(5, (2, 3))
    out = list(es.flush())
    assert _ev_types(out) == ["roll", "roll"]

    # Seven out ends the hand, next roll should be on comeout
    es.roll(7, (3, 4))
    out = list(es.flush())
    assert _ev_types(out) == ["roll", "seven_out"]

    # Next roll triggers a comeout event before roll
    es.roll(11, (5, 6))
    out = list(es.flush())
    assert _ev_types(out) == ["comeout", "roll"]


def test_bet_resolved_passthrough_and_roll_indexing():
    es = EventStream()
    es.new_shooter(42)
    es.roll(4, (1, 3))   # comeout -> point 4
    _ = list(es.flush())

    # simulate a resolved place_6 win after a few rolls
    es.roll(8, (5, 3))
    es.resolve("place_6", "win", payout=14.0, reason="hit 6 earlier in series")
    out = list(es.flush())

    # Expect: roll, then bet_resolved (in that order, with current roll_index)
    assert _ev_types(out) == ["roll", "bet_resolved"]
    br = out[-1]
    assert br["bet_type"] == "place_6"
    assert br["result"] == "win"
    assert br["payout"] == 14.0
    assert isinstance(br["roll_index"], int) and br["roll_index"] >= 2