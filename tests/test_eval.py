# tests/test_eval.py
from crapssim_control.eval import evaluate, eval_num, eval_bool, EvalError


def test_arithmetic_and_precedence():
    state = {"units": 5}
    assert eval_num("units * 2 + 3", state) == 13
    assert eval_num("(units + 1) * 2", state) == 12
    assert eval_num("-units + 10", state) == 5


def test_comparisons_and_logic():
    st = {"rolls_since_point": 3, "mode": "Aggressive"}
    ev = {"total": 6}
    assert eval_bool("rolls_since_point >= 3 and mode == 'Aggressive'", st, ev) is True
    assert eval_bool("total < 5 or total == 6", st, ev) is True
    assert eval_bool("not (total == 5)", st, ev) is True


def test_helpers_round_floor_ceil():
    st = {"x": 2.6}
    assert eval_num("round(x)", st) == 3
    assert eval_num("round(x, 1)", st) == 2.6
    assert eval_num("floor(x)", st) == 2
    assert eval_num("ceil(x)", st) == 3
    assert eval_num("max(1, min(10, 7))") == 7


def test_event_and_state_overlay():
    st = {"units": 5}
    ev = {"units": 3}  # event overlay takes precedence
    assert eval_num("units * 2", st, ev) == 6


def test_python_ternary_supported():
    st = {"bubble": True, "units": 10}
    assert eval_num("1 if bubble else ceil(units/2)", st) == 1
    st["bubble"] = False
    assert eval_num("1 if bubble else ceil(units/2)", st) == 5


def test_undefined_variable_raises():
    try:
        evaluate("foo + 1", {})
    except EvalError as e:
        assert "Unknown variable 'foo'" in str(e)
    else:
        assert False, "Expected EvalError"


def test_disallowed_syntax_rejected():
    # attribute access
    try:
        evaluate("__import__('os').system('echo nope')")
    except EvalError as e:
        assert "not allowed" in str(e).lower()
    else:
        assert False, "Expected EvalError"

    # subscripts
    try:
        evaluate("a[0]", {"a": [1, 2, 3]})
    except EvalError:
        pass
    else:
        assert False, "Expected EvalError"

    # lambdas
    try:
        evaluate("(lambda x: x)(1)")
    except EvalError:
        pass
    else:
        assert False, "Expected EvalError"


def test_type_coercions_and_booleans():
    assert eval_bool("1") is True
    assert eval_bool("0") is False
    assert eval_bool("'true'") is True
    assert eval_bool("'no'") is False