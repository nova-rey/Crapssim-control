import json

from crapssim_control.rules_engine.evaluator import evaluate_rules


def test_bankroll_rule_true():
    rules = [
        {
            "id": "R1",
            "when": "bankroll_after < 500",
            "action": "switch_profile('Recovery')",
            "enabled": True,
        }
    ]
    ctx = {"bankroll_after": 400, "drawdown_after": 100, "point_on": False}
    res = evaluate_rules(rules, ctx)
    assert res[0]["fired"]


def test_guard_blocks_fire():
    rules = [
        {
            "id": "R2",
            "when": "bankroll_after < 500",
            "guard": "point_on == True",
            "action": "regress",
            "enabled": True,
        }
    ]
    ctx = {"bankroll_after": 400, "point_on": False}
    res = evaluate_rules(rules, ctx)
    assert not res[0]["fired"]


def test_disabled_rule_skips():
    rules = [
        {
            "id": "R3",
            "when": "bankroll_after < 500",
            "action": "regress",
            "enabled": False,
        }
    ]
    ctx = {"bankroll_after": 100}
    res = evaluate_rules(rules, ctx)
    assert res[0]["reason"] == "disabled"
