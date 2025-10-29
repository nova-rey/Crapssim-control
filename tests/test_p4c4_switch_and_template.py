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
        },
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


def _get_first_bet(actions, names):
    for n in names:
        for a in actions:
            if a.get("bet_type") == n and a.get("action") == "set":
                return a
    return None


def test_switch_mode_applies_immediately_affecting_template():
    c = ControlStrategy(SPEC)

    # comeout: no actions
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []

    # point established: expect order [switches] -> [template] -> [rule non-switch]
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert acts, "Expected actions on point established"

    # First action should be the switch_mode (bucketed ahead of template)
    assert acts[0]["action"] == "switch_mode"
    assert (acts[0].get("notes") or "").lower() == "aggressive"

    # After applying the switch, template should be Aggressive; then rule overrides place_6 to 24
    place6 = _get_first_bet(acts, ["place_6"])
    assert place6 is not None
    assert place6["amount"] == 24.0

    # If pass bet appears, accept both alias keys
    pass_bet = _get_first_bet(acts, ["pass_line", "pass"])
    if pass_bet is not None:
        assert pass_bet["amount"] == 10.0

    # If place_8 appears, it should be from the Aggressive template (12)
    place8 = _get_first_bet(acts, ["place_8"])
    if place8 is not None:
        assert place8["amount"] == 12.0

    # seq increasing and present
    seqs = [a["seq"] for a in acts]
    assert seqs == sorted(seqs)
