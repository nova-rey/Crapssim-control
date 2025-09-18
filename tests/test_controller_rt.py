# tests/test_controller_rt.py

from crapssim_control.controller import ControlStrategy

SPEC = {
    "meta": {"version": 0, "name": "RegressAfterThree"},
    "table": {"bubble": False, "level": 10, "max_odds_multiple": 3.0},
    "variables": {"units": 5, "mode": "Aggressive", "rolls_since_point": 0},
    "modes": {
        "Aggressive": {
            "template": {
                "pass": "units*2",                # $10 pass
                "place": {"6": "units*2", "8": "units*2", "5": "units"},  # raw 10s → legal 6/6 and 5
            }
        },
        "Regressed": {
            "template": {
                "pass": "units*2",                # keep line bet
                "place": {"6": "units", "8": "units"},                   # raw 5s → legal 0 on 6/8? rounds down to 0? No, 5→0; test expects set to 0 absent
            }
        },
    },
    "rules": [
        {"on": {"event": "point_established"}, "do": ["rolls_since_point = 0", "apply_template('Aggressive')"]},
        {"on": {"event": "roll"}, "do": ["rolls_since_point += 1"]},
        {"on": {"event": "roll"}, "if": "rolls_since_point >= 3", "do": ["mode = 'Regressed'", "apply_template(mode)"]},
    ],
}

def _current_bets_from_plan(plan):
    # naive materializer for testing: apply plan to a dict
    bets = {}
    for a in plan:
        if a["action"] == "set":
            bets[a["bet_type"]] = {"amount": int(a["amount"])}
        elif a["action"] == "clear":
            bets.pop(a["bet_type"], None)
    return bets


def test_end_to_end_regress_after_three_rolls():
    cs = ControlStrategy(SPEC)

    current = {}

    # comeout -> point 6
    plan = cs.handle_event({"type": "comeout"}, current)
    assert plan == []

    plan = cs.handle_event({"type": "point_established", "point": 6}, current)
    # should apply Aggressive template
    assert any(a for a in plan if a["action"] == "set" and a["bet_type"] == "pass_line" and a["amount"] == 10)
    current = _current_bets_from_plan(plan)

    # 1st roll after point
    plan = cs.handle_event({"type": "roll", "total": 8}, current)
    # likely no change until 3 rolls
    assert isinstance(plan, list)
    current = _current_bets_from_plan(plan) or current

    # 2nd roll after point
    plan = cs.handle_event({"type": "roll", "total": 5}, current)
    current = _current_bets_from_plan(plan) or current

    # 3rd roll after point => regress
    plan = cs.handle_event({"type": "roll", "total": 4}, current)

    # Expect clear-then-set for place_6 and place_8 according to deterministic policy
    clears = [a for a in plan if a["action"] == "clear"]
    sets = [a for a in plan if a["action"] == "set"]

    assert any(a for a in clears if a["bet_type"] in ("place_6", "place_8"))
    # Regressed template uses units=5 -> legal place_6/8 in $6s => 0 (absent)
    # So we should see clears for place_6 and place_8 and NOT see sets for them.
    assert not any(a for a in sets if a["bet_type"] in ("place_6", "place_8"))

    # Odds & others unaffected in this minimal test
    # Ensure state tracked rolls_since_point
    snap = cs.state_snapshot()
    assert snap["rolls_since_point"] >= 3
    assert snap["point"] == 6
    assert snap["on_comeout"] is False

def test_resets_on_seven_out():
    cs = ControlStrategy(SPEC)
    cs.handle_event({"type": "comeout"}, {})
    cs.handle_event({"type": "point_established", "point": 5}, {})
    assert cs.state_snapshot()["point"] == 5

    # rolling progresses counter
    cs.handle_event({"type": "roll", "total": 6}, {})
    assert cs.state_snapshot()["rolls_since_point"] == 1

    # seven out resets
    cs.handle_event({"type": "seven_out"}, {})
    snap = cs.state_snapshot()
    assert snap["point"] is None
    assert snap["on_comeout"] is True
    assert snap["rolls_since_point"] == 0