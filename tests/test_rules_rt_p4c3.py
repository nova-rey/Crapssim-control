import pytest

from crapssim_control.rules_engine import apply_rules
from crapssim_control.actions import ACTION_SET, ACTION_CLEAR, ACTION_PRESS, ACTION_REDUCE, ACTION_SWITCH_MODE

STATE = {"units": 10, "mode": "Main", "on_comeout": True, "point": None}

def _roll_event(total=6, point=None):
    return {"type": "roll", "roll": total, "point": point}

def test_string_steps_basic():
    rules = [
        {"on": {"event": "roll"}, "do": ["set place_6 12", "press place_6 6", "reduce place_6 6", "clear place_6"]},
    ]
    out = apply_rules(rules, STATE, _roll_event(6))
    acts = [a["action"] for a in out]
    assert acts == [ACTION_SET, ACTION_PRESS, ACTION_REDUCE, ACTION_CLEAR]
    assert out[0]["bet_type"] == "place_6" and out[0]["amount"] == 12.0

def test_switch_mode_string_and_object():
    rules = [
        {"on": {"event": "roll"}, "do": ["switch_mode Aggressive"]},
        {"on": {"event": "roll"}, "do": [{"action": "switch_mode", "mode": "Main"}]},
    ]
    out = apply_rules(rules, STATE, _roll_event(8))
    assert len(out) == 2
    assert out[0]["action"] == ACTION_SWITCH_MODE and out[0]["notes"] == "Aggressive"
    assert out[1]["action"] == ACTION_SWITCH_MODE and out[1]["notes"] == "Main"

def test_object_steps_with_eval_amounts():
    rules = [
        {"on": {"event": "roll"}, "when": "roll in (6,8)", "do": [
            {"action": "set", "bet_type": "place_8", "amount": "units - 4"},
            {"action": "press", "bet": "place_8", "amount": "min(6, units/2)"},
        ]},
    ]
    out = apply_rules(rules, dict(STATE), _roll_event(8))
    assert [a["action"] for a in out] == [ACTION_SET, ACTION_PRESS]
    assert out[0]["amount"] == 6.0  # 10 - 4
    assert out[1]["amount"] == 5.0  # min(6, 5)

def test_event_gate_filters():
    rules = [
        {"on": {"event": "comeout"}, "do": ["set pass_line 10"]},
        {"on": {"event": "roll"}, "do": ["set place_6 12"]},
    ]
    out = apply_rules(rules, STATE, {"type": "comeout"})
    assert len(out) == 1 and out[0]["bet_type"] == "pass_line"

def test_bad_rules_fail_open():
    rules = [
        "not a dict",
        {"on": {"event": "roll"}, "do": ["unknown verb 123"]},
        {"on": {"event": "roll"}, "do": [{"action": "set"}]},  # missing bet+amount
    ]
    out = apply_rules(rules, STATE, _roll_event(5))
    assert out == []  # nothing valid emitted