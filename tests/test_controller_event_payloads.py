# tests/test_controller_event_payloads.py
from typing import Any, Dict

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT


def _spec_with_simple_rule() -> Dict[str, Any]:
    # Minimal viable spec: one mode with empty template + a simple rule that fires on comeout.
    return {
        "table": {"bubble": False, "level": 10},
        "modes": {"base": {"template": {}}},
        "variables": {"units": 10},
        "rules": [
            {
                "name": "hello_comeout",
                "on": {"event": "comeout"},
                "do": ["clear place_6"],
            }
        ],
        # Minimal CSV config omitted; journaling remains disabled by default in tests
    }


def test_controller_canonicalizes_and_handles_core_events():
    spec = _spec_with_simple_rule()
    ctrl = ControlStrategy(spec)

    # COMEOUT → should update state and fire the comeout rule (clear place_6)
    a1 = ctrl.handle_event({"type": COMEOUT}, current_bets={})
    assert isinstance(a1, list)
    assert any(a.get("action") == "clear" and a.get("bet_type") == "place_6" for a in a1)

    # POINT_ESTABLISHED → sets point and applies template diff + rules
    a2 = ctrl.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert isinstance(a2, list)
    # we don't assert exact envelopes here; just ensure no crash and list returned
    assert ctrl.point == 6 and ctrl.on_comeout is False and ctrl.rolls_since_point == 0

    # ROLL while point is on → increments rolls_since_point; rule on 'roll' not present, so may be empty
    a3 = ctrl.handle_event(
        {"type": ROLL, "roll": 8, "point": 6, "on_comeout": False}, current_bets={}
    )
    assert isinstance(a3, list)
    assert ctrl.rolls_since_point == 1

    # SEVEN_OUT → resets state and still allows rules to run
    a4 = ctrl.handle_event({"type": SEVEN_OUT, "point": 6}, current_bets={})
    assert isinstance(a4, list)
    assert ctrl.point is None and ctrl.on_comeout is True and ctrl.rolls_since_point == 0


def test_controller_handles_partial_events_via_canonicalization():
    spec = _spec_with_simple_rule()
    ctrl = ControlStrategy(spec)

    # Missing fields are fine; canonicalizer fills defaults
    actions = ctrl.handle_event({"type": "comeout"}, current_bets={})
    assert isinstance(actions, list)
