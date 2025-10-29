# tests/test_histograms_basic.py
from crapssim_control.tracker import Tracker
from crapssim_control.tracker_histograms import attach_histograms


def make_tracker():
    t = Tracker()
    # ensure a known shooter id so we can detect changes
    t.shooter_id = 1
    attach_histograms(t, enabled=True)
    return t


def test_hand_and_shooter_histograms_increment_and_reset():
    t = make_tracker()

    # roll some totals (using liberal on_roll signature handling)
    t.on_roll(6)
    t.on_roll({"total": 8})
    t.on_roll(total=5)

    snap = t.snapshot()
    hist = snap["history"]
    assert hist["hand_hits"]["6"] == 1
    assert hist["hand_hits"]["8"] == 1
    assert hist["hand_hits"]["5"] == 1
    assert hist["shooter_hits"]["6"] == 1
    assert hist["session_hits"]["6"] >= 1

    # simulate seven-out -> hand reset
    if hasattr(t, "on_seven_out"):
        t.on_seven_out()
    elif hasattr(t, "on_point_seven_out"):
        t.on_point_seven_out()
    elif hasattr(t, "on_hand_end"):
        t.on_hand_end()

    snap2 = t.snapshot()
    hist2 = snap2["history"]
    assert all(
        v == 0 for v in hist2["hand_hits"].values()
    ), "hand histogram should reset on seven-out"

    # shooter change should reset shooter histogram
    t.shooter_id = 2
    t.on_roll(9)  # trigger change detection in wrapper
    snap3 = t.snapshot()
    hist3 = snap3["history"]
    assert sum(hist3["shooter_hits"].values()) == 1  # only the 9 after shooter change


def test_inside_outside_mirrors_present():
    t = make_tracker()
    t.on_roll(6)  # inside + outside by our maintained sets
    snap = t.snapshot()
    hist = snap["history"]
    assert "hand_inside_hits" in hist and "hand_outside_hits" in hist
    assert hist["hand_inside_hits"] >= 1
    assert hist["hand_outside_hits"] >= 1
