from crapssim_control.policy_engine import PolicyEngine
from crapssim_control.risk_schema import RiskPolicy


def make_policy(**kwargs):
    policy = RiskPolicy()
    for key, value in kwargs.items():
        setattr(policy, key, value)
    return policy


def test_drawdown_limit_trigger():
    policy = make_policy(max_drawdown_pct=10)
    engine = PolicyEngine(policy)
    assert not engine.check_drawdown(850, 1000)
    assert engine.check_drawdown(950, 1000)


def test_heat_limit_trigger():
    policy = make_policy(max_heat=200)
    engine = PolicyEngine(policy)
    assert engine.check_heat(100)
    assert not engine.check_heat(250)


def test_bet_cap_trigger():
    policy = make_policy(bet_caps={"place_6": 90})
    engine = PolicyEngine(policy)
    assert engine.check_bet_cap("place_6", 60)
    assert not engine.check_bet_cap("place_6", 120)


def test_recovery_modes():
    policy = make_policy()
    policy.recovery.enabled = True
    policy.recovery.mode = "flat_recovery"
    engine = PolicyEngine(policy)
    assert engine.apply_recovery(100) == 100

    policy.recovery.mode = "step_recovery"
    engine = PolicyEngine(policy)
    assert engine.apply_recovery(100) == 150


def test_evaluate_combines_checks():
    policy = make_policy(max_heat=100, bet_caps={"place_6": 50})
    engine = PolicyEngine(policy)
    snapshot = {"bankroll": 900, "bankroll_peak": 1000, "active_bets_sum": 120}
    action = {"verb": "place_6", "args": {"amount": 60}}
    result = engine.evaluate(action, snapshot)
    assert not result["allowed"]
    assert result["reason"] in ("heat_limit", "bet_cap")
