# tests/test_regression_rule_override.py
from __future__ import annotations

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL

SPEC = {
    "table": {},
    "variables": {"units": 10},
    "modes": {
        "Main": {
            "template": {
                "pass_line": 10,
                "place_6": 12,
                "place_8": 12,
            }
        }
    },
    "rules": [
        # On the 3rd roll after point is set, controller emits template-origin "clear place_6/place_8".
        # This rule sets place_6 again in the SAME event, which should override the clear (last-wins).
        {
            "name": "reassert_place6_on_roll",
            "on": {"event": "roll"},
            "when": "rolls_since_point == 3",
            "do": ["set place_6 15"],
        }
    ],
}

def test_regression_clear_can_be_overridden_by_rule_in_same_event():
    c = ControlStrategy(SPEC)
    current_bets = {}

    # comeout → no actions
    c.handle_event({"type": COMEOUT}, current_bets=current_bets)

    # point set → template applies
    c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets=current_bets)

    # first two rolls: nothing interesting for this test
    c.handle_event({"type": ROLL, "roll": 5, "point": 6}, current_bets=current_bets)
    c.handle_event({"type": ROLL, "roll": 8, "point": 6}, current_bets=current_bets)

    # 3rd roll since point: controller adds template-origin clear(6,8), rule sets place_6 to 15
    acts = c.handle_event({"type": ROLL, "roll": 4, "point": 6}, current_bets=current_bets)

    # For place_6, rule should last-win (override the clear)
    # Keep only the final action for place_6 (if present)
    final_place6 = None
    for a in acts:
        if a.get("bet_type") == "place_6":
            final_place6 = a

    assert final_place6 is not None
    assert final_place6["action"] == "set"
    assert float(final_place6["amount"]) == 15.0