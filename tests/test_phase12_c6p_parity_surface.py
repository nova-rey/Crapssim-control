import pytest

SEQ = [
    (3, 4),
    (2, 2),
    (6, 1),
    (5, 3),
    (6, 2),
    (4, 2),
    (3, 3),
    (6, 6),
    (5, 2),
    (2, 3),
    (4, 3),
    (1, 1),
    (5, 1),
    (6, 5),
    (4, 4),
    (2, 5),
    (3, 2),
    (6, 4),
    (5, 5),
    (1, 6),
]

RULES = """
WHEN NOT point_on THEN line_bet(side=pass, amount=10)
WHEN point_on AND bets.6 == 0 THEN place_bet(number=6, amount=12)
WHEN point_on AND bets.8 == 0 THEN place_bet(number=8, amount=12)
"""


def drive(adapter, seq, trace=False, explain=False):
    adapter.start_session(
        {
            "run": {
                "policy": {"enforce": True},
                "risk": {"max_drawdown_pct": 50, "max_heat": 300},
                "stop_on_bankrupt": True,
                "stop_on_unactionable": True,
                "journal": {"explain": explain},
            }
        }
    )
    adapter.load_ruleset(RULES)
    if hasattr(adapter, "enable_dsl_trace"):
        adapter.enable_dsl_trace(trace)
    for d in seq:
        out = adapter.step_roll(dice=d)
        if isinstance(out, dict) and out.get("status") == "terminated":
            break
    return adapter.snapshot_state(), {
        "terminated_early": getattr(adapter, "_terminated_early", False),
        "termination_reason": getattr(adapter, "_termination_reason", None),
        "rolls_completed": getattr(adapter, "_rolls_completed", 0),
        "violations": getattr(adapter, "_policy_violations", 0),
        "applied": getattr(adapter, "_policy_applied", 0),
    }


def test_surface_parity_with_and_without_trace(monkeypatch):
    from crapssim_control.engine_adapter import VanillaAdapter

    a1 = VanillaAdapter()
    s1, m1 = drive(a1, SEQ, trace=False, explain=False)

    a2 = VanillaAdapter()
    s2, m2 = drive(a2, SEQ, trace=True, explain=True)

    # Numeric parity on core fields
    assert s1.get("bankroll") == s2.get("bankroll")
    assert m1["terminated_early"] == m2["terminated_early"]
    assert m1["termination_reason"] == m2["termination_reason"]
    assert m1["rolls_completed"] == m2["rolls_completed"]
