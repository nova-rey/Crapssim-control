# tests/test_p4c3_merge.py
from __future__ import annotations

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED

SPEC = {
    "table": {},
    "variables": {"units": 10},
    "modes": {
        "Main": {
            "template": {
                # simple numeric amounts; runtime template diff will "set" these from empty
                "pass_line": 10,
                "place_6": 12,
                "place_8": 12,
            }
        }
    },
    "rules": [
        {
            "name": "boost_6_8_on_point",
            "on": {"event": "point_established"},
            "when": "point in (4,5,6,8,9,10)",
            "do": [
                # These should appear AFTER template actions and override same-bet actions
                "set place_6 18",
                "set place_8 12",  # same amount as template — still last-wins on same bet
            ],
        }
    ],
}

def test_merge_order_and_last_wins_on_point_established():
    c = ControlStrategy(SPEC)

    # comeout: no template plan, no actions
    acts = c.handle_event({"type": COMEOUT}, current_bets={})
    assert acts == []

    # point: template diff first → rules after; last-wins per bet keeps the RULE set for place_6
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})

    # Expect only ONE action per bet after merge
    by_bet = {}
    for a in acts:
        if a["action"] == "set" and a.get("bet_type"):
            by_bet[a["bet_type"]] = a

    # pass_line from template remains
    assert by_bet["pass_line"]["amount"] == 10.0
    # place_6 overridden by the rule from 12 → 18 (last-wins between template and rule)
    assert by_bet["place_6"]["amount"] == 18.0
    # place_8 stays set; even same amount, rule replaces template instance
    assert by_bet["place_8"]["amount"] == 12.0

    # seq should be present and strictly increasing
    seqs = [a["seq"] for a in acts]
    assert seqs == sorted(seqs)