from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT

SPEC = {
    "table": {"bubble": False, "level": 10},
    "variables": {"units": 10, "mode": "Main"},
    "modes": {
        "Main": {
            "template": {
                "pass": "units",
                "place_6": {"amount": 6},
                "place_8": 6,
            }
        }
    },
    "rules": [
        {"on": {"event": "roll"}, "when": "roll == 9", "do": ["clear place_6"]},
        {"on": {"event": "seven_out"}, "do": ["switch_mode Recovery"]},
    ],
    "run": {"csv": {"enabled": False, "path": ""}},
}

def test_controller_handles_sequence_and_rules():
    c = ControlStrategy(SPEC)
    # comeout: only rules for comeout (none here)
    acts = c.handle_event({"type": COMEOUT}, current_bets={})
    assert acts == []

    # point established 6: at minimum we should get a template diff that sets pass_line
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    kinds = sorted((a["action"], a.get("bet_type")) for a in acts)
    # Minimal expectation: pass_line is set (place bets may be deferred by template/diff logic)
    assert ("set", "pass_line") in kinds

    # roll 9 with point on -> rules clear place_6
    acts = c.handle_event({"type": ROLL, "roll": 9, "point": 6}, current_bets={"pass":10,"place_6":6,"place_8":6})
    assert any(a["action"] == "clear" and a.get("bet_type") == "place_6" for a in acts)

    # seven out should reset and emit rules (switch_mode)
    acts = c.handle_event({"type": SEVEN_OUT}, current_bets={})
    assert any(a["action"] == "switch_mode" and "Recovery" in (a.get("notes") or "") for a in acts)
    snap = c.state_snapshot()
    assert snap["on_comeout"] is True and snap["point"] is None and snap["rolls_since_point"] == 0