# tests/test_rules_event_context.py
from typing import Any, Dict

from crapssim_control.events import canonicalize_event, COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT
from crapssim_control.rules_engine import apply_rules


def _base_state() -> Dict[str, Any]:
    # Minimal state snapshot the controller would provide to the eval sandbox.
    return {"units": 10, "rolls_since_point": 0, "on_comeout": True, "point": None, "mode": "base"}


def test_canonicalize_event_shapes():
    e1 = canonicalize_event({"type": COMEOUT})
    assert e1["type"] == COMEOUT and "on_comeout" in e1 and e1["on_comeout"] is True
    assert "point" in e1 and e1["point"] is None

    e2 = canonicalize_event({"type": POINT_ESTABLISHED, "point": 6})
    assert e2["type"] == POINT_ESTABLISHED and e2["point"] == 6 and e2["on_comeout"] is False

    e3 = canonicalize_event({"type": ROLL, "roll": 8, "point": 6, "on_comeout": False})
    assert e3["type"] == ROLL and e3["roll"] == 8 and e3["point"] == 6 and e3["on_comeout"] is False

    e4 = canonicalize_event({"type": SEVEN_OUT, "point": 6})
    assert e4["type"] == SEVEN_OUT and "point" in e4


def test_when_predicate_can_read_flat_keys_from_event_and_state():
    rules = [
        {
            "name": "fires_on_roll_ge_8_with_point_on",
            "on": {"event": "roll"},
            "when": "roll >= 8 and point in (4,5,6,8,9,10) and not on_comeout",
            "do": ["clear place_8"],
        }
    ]

    state = _base_state()
    # put table 'on': point established
    state["point"] = 6
    state["on_comeout"] = False
    ev = {"type": "roll", "roll": 8, "point": 6, "on_comeout": False}

    actions = apply_rules(rules, state, ev)
    assert len(actions) == 1
    a = actions[0]
    assert a["action"] == "clear" and a["bet_type"] == "place_8" and a["source"] == "rule"