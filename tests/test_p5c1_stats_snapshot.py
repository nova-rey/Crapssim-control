from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT

SPEC = {
    "table": {},
    "variables": {"units": 5},
    "modes": {"Main": {"template": {}}},  # template content irrelevant here
    "run": {"csv": {"enabled": False}},
    # Ensure an action occurs at point_established
    "rules": [
        {
            "name": "kick_action_for_stats",
            "on": {"event": "point_established"},
            "do": ["set place_6 12"],
        }
    ],
}

def test_state_snapshot_includes_stats_and_memory_updates():
    c = ControlStrategy(SPEC)

    c.handle_event({"type": COMEOUT}, current_bets={})
    c.handle_event({"type": POINT_ESTABLISHED, "point": 8}, current_bets={})
    c.handle_event({"type": ROLL, "roll": 6, "point": 8}, current_bets={})
    c.handle_event({"type": SEVEN_OUT}, current_bets={})

    # Ensure in-RAM memory shows up
    c.memory["session_flag"] = True

    snap = c.state_snapshot()
    assert "stats" in snap and isinstance(snap["stats"], dict)
    stats = snap["stats"]
    assert stats.get("events_total") == 4
    assert stats.get("actions_total", 0) >= 1  # rule-driven action on point_established

    by_ev = stats.get("by_event_type") or {}
    assert by_ev.get("comeout", 0) == 1
    assert by_ev.get("point_established", 0) == 1
    assert by_ev.get("roll", 0) == 1
    assert by_ev.get("seven_out", 0) == 1

    mem = snap.get("memory") or {}
    assert mem.get("session_flag") is True