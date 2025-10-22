import pytest

from crapssim_control.dsl_eval import evaluate_condition, compile_expr, ExpressionError

SNAP = {
    "bankroll": 480,
    "drawdown": 50,
    "point_on": True,
    "point_value": 4,
    "bets": {"6": 0, "8": 12},
    "odds": {"come": {"6": 0}, "dc": {"8": 25}},
    "working": {"flags": {"place": True, "odds": True}},
    "hand_id": 3,
    "roll_in_hand": 2,
}


def test_simple_comparison_true():
    assert evaluate_condition("bankroll < 500", SNAP) is True


def test_logical_combo_and():
    assert evaluate_condition("point_on AND bankroll > 100", {**SNAP, "bankroll": 1200}) is True


def test_nested_parentheses():
    expr = "((point_on AND drawdown > 40) OR bankroll < 100)"
    assert evaluate_condition(expr, SNAP) is True


def test_invalid_variable_raises():
    with pytest.raises(ExpressionError):
        evaluate_condition("badkey < 10", SNAP)


def test_dotted_snapshot_access():
    assert evaluate_condition("bets.6 == 0", SNAP) is True
    assert evaluate_condition("odds.come.6 > 0", SNAP) is False


def test_not_and_or_precedence():
    assert evaluate_condition("NOT point_on OR bankroll < 1000", SNAP) is True


def test_string_and_bool_literals():
    expr = "TRUE AND 'abc' == 'abc'"
    assert evaluate_condition(expr, SNAP) is True


def test_no_eval_injection():
    with pytest.raises(ExpressionError):
        compile_expr("__import__")
