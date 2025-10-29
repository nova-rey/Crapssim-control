# tests/test_rules_mvp.py

from typing import Any, Dict, List

from crapssim_control.rules_engine import apply_rules
from crapssim_control.actions import (
    SOURCE_RULE,
    ACTION_SET,
    ACTION_CLEAR,
    ACTION_PRESS,
    ACTION_REDUCE,
    ACTION_SWITCH_MODE,
)


def _all_have_envelope_shape(actions: List[Dict[str, Any]]) -> bool:
    required = {"source", "id", "action", "bet_type", "amount", "notes"}
    return all(required.issubset(a.keys()) for a in actions)


def _find(actions: List[Dict[str, Any]], action: str, bet_type: str | None = None):
    for a in actions:
        if a.get("action") != action:
            continue
        if bet_type is not None and a.get("bet_type") != bet_type:
            continue
        return a
    return None


def test_event_gating_only_fires_on_matching_event():
    rules = [
        {"name": "r1", "on": {"event": "roll"}, "do": ["clear place_6"]},
    ]
    st = {"units": 5}
    ev_roll = {"type": "roll"}
    ev_comeout = {"type": "comeout"}

    a1 = apply_rules(rules, st, ev_roll)
    a2 = apply_rules(rules, st, ev_comeout)

    assert len(a1) == 1
    assert a1[0]["action"] == ACTION_CLEAR and a1[0]["bet_type"] == "place_6"
    assert a2 == []


def test_when_predicate_true_false_paths():
    rules = [
        {
            "name": "gate_after_two",
            "on": {"event": "roll"},
            "when": "rolls_since_point >= 2 and point in (6, 8)",
            "do": ["press place_6 6"],
        }
    ]
    st = {"rolls_since_point": 1, "point": 6}
    ev = {"type": "roll"}

    # False when
    a_false = apply_rules(rules, st, ev)
    assert a_false == []

    # True when
    st["rolls_since_point"] = 3
    a_true = apply_rules(rules, st, ev)
    assert len(a_true) == 1
    assert a_true[0]["action"] == ACTION_PRESS and a_true[0]["bet_type"] == "place_6"
    assert _all_have_envelope_shape(a_true)
    assert a_true[0]["source"] == SOURCE_RULE
    assert a_true[0]["id"] == "rule:gate_after_two"


def test_basic_string_steps_and_amount_expressions():
    rules = [
        {
            # unnamed → index-based id
            "on": {"event": "point_established"},
            "when": "units > 0",
            "do": [
                "set pass_line units*2",  # expression amount
                "clear place_6",
                "press place_8 6",
                "reduce place_5 5",
            ],
        }
    ]
    st = {"units": 5}
    ev = {"type": "point_established"}

    acts = apply_rules(rules, st, ev)
    ids = {a["id"] for a in acts}
    assert "rule:#1" in ids  # 1-based index

    # set pass_line 10
    a_set = _find(acts, ACTION_SET, "pass_line")
    assert a_set and isinstance(a_set["amount"], float) and abs(a_set["amount"] - 10.0) < 1e-9

    # clear place_6
    a_clear = _find(acts, ACTION_CLEAR, "place_6")
    assert a_clear and a_clear["amount"] is None

    # press place_8 6
    a_press = _find(acts, ACTION_PRESS, "place_8")
    assert a_press and a_press["amount"] == 6.0

    # reduce place_5 5
    a_reduce = _find(acts, ACTION_REDUCE, "place_5")
    assert a_reduce and a_reduce["amount"] == 5.0

    # envelope shape
    assert _all_have_envelope_shape(acts)
    assert all(a["source"] == SOURCE_RULE for a in acts)


def test_switch_mode_emits_envelope_with_notes_mode_and_no_bet_or_amount():
    rules = [
        {
            "name": "mode_switch",
            "on": {"event": "roll"},
            "do": ["switch_mode Recovery"],
        }
    ]
    st = {}
    ev = {"type": "roll"}

    acts = apply_rules(rules, st, ev)
    assert len(acts) == 1
    a = acts[0]
    assert a["action"] == ACTION_SWITCH_MODE
    assert a["bet_type"] is None and a["amount"] is None
    assert a["notes"] == "Recovery"
    assert a["id"] == "rule:mode_switch"


def test_dict_form_steps_supported_and_unknown_steps_ignored():
    rules = [
        {
            "on": {"event": "roll"},
            "do": [
                {"action": "set", "bet_type": "field", "amount": 5},
                {"action": "press", "bet_type": "place_6", "amount": "3+3"},  # expression
                {"action": "unknown", "bet_type": "place_5", "amount": 5},  # ignored
                "set place_8 not_a_number",  # invalid amount → ignored
            ],
        }
    ]
    st = {}
    ev = {"type": "roll"}

    acts = apply_rules(rules, st, ev)

    # set field 5
    a1 = _find(acts, ACTION_SET, "field")
    assert a1 and a1["amount"] == 5.0

    # press place_6 6
    a2 = _find(acts, ACTION_PRESS, "place_6")
    assert a2 and a2["amount"] == 6.0

    # invalid/unknown steps should be ignored; total should be exactly 2
    assert len(acts) == 2


def test_bad_inputs_are_permissive():
    # Non-list rules
    assert apply_rules(None, {}, {"type": "roll"}) == []
    assert apply_rules({}, {}, {"type": "roll"}) == []  # type: ignore[arg-type]

    # Missing on/event → skip
    rules = [{"do": ["clear place_6"]}]
    assert apply_rules(rules, {}, {"type": "roll"}) == []

    # when expression error → treated as False (skip)
    rules_err = [{"on": {"event": "roll"}, "when": "unknown_var > 0", "do": ["clear place_6"]}]
    assert apply_rules(rules_err, {}, {"type": "roll"}) == []
