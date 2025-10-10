# tests/test_p4c4_switch_and_template.py
from __future__ import annotations

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED

SPEC = {
    "table": {},
    "variables": {"units": 10},
    "modes": {
        "Main": {
            "template": {
                "pass_line": 10,
            }
        },
        "Aggressive": {
            "template": {
                "pass_line": 10,
                "place_6": 12,
                "place_8": 12,
            }
        }
    },
    "rules": [
        {
            "name": "switch_then_tweak",
            "on": {"event": "point_established"},
            "when": "point in (4,5,6,8,9,10)",
            "do": [
                # P4C4: this switch MUST apply immediately, so the template rendered for this
                # same event should be for "Aggressive", not "Main".
                "switch_mode Aggressive",
                # And then this rule non-switch should come AFTER the template and last-win for place_6.
                "set place_6 24",
            ],
        }
    ],
}

def test_switch_mode_applies_immediately_affecting_template():
    c = ControlStrategy(SPEC)

    # comeout: no actions
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []

    # point established: expect order [switches] -> [template] -> [rule non-switch]
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})

    # First action should be the switch_mode (bucketed ahead of template)
    assert acts[0]["action"] == "switch_mode"
    assert (acts[0].get("notes") or "").lower() == "aggressive"

    # After applying the switch, template should be for Aggressive mode
    # That template would set pass_line, place_6 (12), place_8 (12)
    # Then the rule non-switch "set place_6 24" should last-win for place_6.
    final_by_bet = {}
    for a in acts:
        if a["action"] == "set" and a.get("bet_type"):
            final_by_bet[a["bet_type"]] = a

    assert "pass_line" in final_by_bet
    assert "place_8" in final_by_bet
    assert "place_6" in final_by_bet

    # place_6 ended at 24 due to rule overriding template
    assert final_by_bet["place_6"]["amount"] == 24.0

    # seq increasing and present
    seqs = [a["seq"] for a in acts]
    assert seqs == sorted(seqs)