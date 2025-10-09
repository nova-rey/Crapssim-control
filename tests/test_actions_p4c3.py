import pytest

from crapssim_control.actions import (
    make_action, normalize_action, is_bet_action,
    SOURCE_TEMPLATE, SOURCE_RULE,
    ACTION_SET, ACTION_CLEAR, ACTION_PRESS, ACTION_REDUCE, ACTION_SWITCH_MODE,
)

def test_make_action_basic():
    a = make_action(ACTION_SET, bet_type="place_6", amount=12, source=SOURCE_RULE, id_="rule:#1", notes="x")
    assert a["action"] == ACTION_SET
    assert a["bet_type"] == "place_6"
    assert a["amount"] == 12.0
    assert a["source"] == SOURCE_RULE
    assert a["id"] == "rule:#1"
    assert a["notes"] == "x"

def test_normalize_action_roundtrip():
    raw = {"action": "press", "bet_type": "place_8", "amount": "6", "source": "RULE", "id": "rule:press8", "notes": "n"}
    a = normalize_action(raw)
    assert a["action"] == ACTION_PRESS
    assert a["bet_type"] == "place_8"
    assert a["amount"] == 6.0
    assert a["source"] == SOURCE_RULE
    assert a["id"] == "rule:press8"
    assert a["notes"] == "n"

def test_is_bet_action_true_for_mutations():
    for act in (ACTION_SET, ACTION_PRESS, ACTION_REDUCE, ACTION_CLEAR):
        a = make_action(act, bet_type="pass_line", amount=10)
        assert is_bet_action(a)

def test_is_bet_action_false_for_switch_mode():
    a = make_action(ACTION_SWITCH_MODE, bet_type=None, amount=None, source=SOURCE_TEMPLATE, id_="template:Main", notes="Aggressive")
    assert not is_bet_action(a)