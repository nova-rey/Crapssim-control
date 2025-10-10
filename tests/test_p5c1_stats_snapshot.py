from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT

SPEC = {
    "table": {},
    "variables": {"units": 5},
    "modes": {"Main": {"template": {"pass_line": 5}}},
    "run": {"csv": {"enabled": False}},  # not needed for this test
    "rules": [],
}

def test_state_snapshot_includes_stats_and_memory_updates():
    c = ControlStrategy(SPEC)

    # Sequence of events:
    c.handle_event({"type": COMEOUT}, current_bets={})
    c.handle_event({"type": POINT_ESTABLISHED, "point": 8}, current_bets={})
    c.handle_event({"type": ROLL, "roll": 6, "point": 8}, current_bets={})
    c.handle_event({"type": SEVEN_OUT}, current_bets={})

    # Manually add to in-RAM memory and check it shows in snapshot
    c.memory["session_flag"] = True

    snap = c.state_snapshot()
    assert "stats" in snap and isinstance(snap["stats"], dict)
    stats = snap["stats"]
    # Four events processed
    assert stats.get("events_total") == 4
    # There should be at least one action across the sequence (template on point)
    assert stats.get("actions_total", 0) >= 1

    by_ev = stats.get("by_event_type") or {}
    assert by_ev.get("comeout", 0) == 1
    assert by_ev.get("point_established", 0) == 1
    assert by_ev.get("roll", 0) == 1
    assert by_ev.get("seven_out", 0) == 1

    # Memory is surfaced in the snapshot
    mem = snap.get("memory") or {}
    assert mem.get("session_flag") is True