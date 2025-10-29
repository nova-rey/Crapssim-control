# tests/test_rules_guardrails.py
from crapssim_control.spec_validation import validate_spec


def _ok_spec():
    return {
        "table": {"bubble": False, "level": 10},
        "modes": {"base": {"template": {}}},  # empty template object is allowed
        "rules": [
            {
                "name": "valid",
                "on": {"event": "roll"},
                "when": "point or on_comeout",
                "do": [
                    "clear place_6",
                    {"action": "set", "bet": "place_8", "amount": "10"},
                    {"action": "switch_mode", "mode": "Press"},
                ],
            }
        ],
    }


def test_bad_on_event_value_is_flagged():
    spec = _ok_spec()
    spec["rules"][0]["on"]["event"] = "point_set"  # invalid; should be rejected
    errs = validate_spec(spec)
    assert any("on.event must be one of" in e for e in errs)


def test_do_string_unknown_action_is_flagged():
    spec = _ok_spec()
    spec["rules"][0]["do"] = ["explode place_6 10"]  # not allowed
    errs = validate_spec(spec)
    assert any("unknown action 'explode'" in e for e in errs)


def test_do_object_missing_amount_is_flagged_for_set_press_reduce():
    spec = _ok_spec()
    spec["rules"][0]["do"] = [{"action": "set", "bet": "place_6"}]  # amount is required
    errs = validate_spec(spec)
    assert any(".amount is required for action 'set'" in e for e in errs)


def test_do_object_switch_mode_needs_no_bet_or_amount():
    spec = _ok_spec()
    spec["rules"][0]["do"] = [{"action": "switch_mode", "mode": "Conservative"}]
    errs = validate_spec(spec)
    assert errs == []  # valid
