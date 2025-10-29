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
                "set place_8 12",  # even if same amount, last-wins replaces template’s instance
            ],
        }
    ],
}


def _by_bet(actions):
    out = {}
    for a in actions:
        bt = a.get("bet_type")
        if a.get("action") == "set" and isinstance(bt, str) and bt:
            out[bt] = a
    return out


def _get_first_bet(actions, names):
    for n in names:
        for a in actions:
            if a.get("bet_type") == n and a.get("action") == "set":
                return a
    return None


def test_merge_order_and_last_wins_on_point_established():
    c = ControlStrategy(SPEC)

    # comeout: no template plan, no actions
    acts = c.handle_event({"type": COMEOUT}, current_bets={})
    assert acts == []

    # point: template diff first → rules after; last-wins per bet keeps the RULE set for place_6
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})

    # Expect exactly one final action per bet after merge (no duplicates)
    seen = {}
    for a in acts:
        bt = a.get("bet_type")
        if bt and a.get("action") in {"set", "clear", "press", "reduce"}:
            assert bt not in seen, f"Duplicate final action for bet {bt}"
            seen[bt] = a

    # place_6 must be last-won by the rule at 18
    place6 = _get_first_bet(acts, ["place_6"])
    assert place6 is not None
    assert place6["amount"] == 18.0

    # Optional: pass bet can be 'pass' or 'pass_line' depending on templates/diff
    pass_bet = _get_first_bet(acts, ["pass_line", "pass"])
    if pass_bet is not None:
        assert pass_bet["amount"] == 10.0

    # seq should be present and strictly increasing
    seqs = [a["seq"] for a in acts]
    assert seqs == sorted(seqs)
