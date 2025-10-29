from crapssim_control.risk_schema import load_risk_policy, RiskPolicy


def test_risk_policy_defaults():
    p = load_risk_policy({})
    assert isinstance(p, RiskPolicy)
    assert p.version == "1.0"
    assert p.max_drawdown_pct is None
    assert p.max_heat is None
    assert p.bet_caps == {}
    assert p.recovery.enabled is False


def test_risk_policy_values_loaded():
    spec = {
        "run": {
            "risk": {
                "max_drawdown_pct": 25,
                "max_heat": 200,
                "bet_caps": {"place_6": 90, "place_8": 90},
                "recovery": {"enabled": True, "mode": "flat_recovery"},
            }
        }
    }
    p = load_risk_policy(spec)
    assert p.max_drawdown_pct == 25
    assert p.max_heat == 200
    assert p.bet_caps["place_6"] == 90
    assert p.recovery.enabled is True
    assert p.recovery.mode == "flat_recovery"


def test_invalid_values_fallback():
    spec = {"run": {"risk": {"max_drawdown_pct": -5, "max_heat": -10}}}
    p = load_risk_policy(spec)
    assert p.max_drawdown_pct is None
    assert p.max_heat is None
