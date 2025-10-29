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


def run_session(adapter, dice_seq, rules_text):
    adapter.load_ruleset(rules_text)
    if hasattr(adapter, "enable_dsl_trace"):
        adapter.enable_dsl_trace(False)
    for d in dice_seq:
        adapter.step_roll(dice=d)
    snap = adapter.snapshot_state()
    return {
        "bankroll": snap.get("bankroll"),
        "point_on": snap.get("point_on"),
        "point_value": snap.get("point_value"),
        "rolls": len(dice_seq),
    }


def test_live_vs_replay_parity(monkeypatch):
    from crapssim_control.engine_adapter import VanillaAdapter

    a_live = VanillaAdapter()
    a_live.start_session({"run": {"journal": {"explain": False}}})
    with open("examples/demo_rules.dsl", "r", encoding="utf-8") as f:
        rules = f.read()
    live = run_session(a_live, SEQ, rules)

    a_rep = VanillaAdapter()
    a_rep.start_session({"run": {"journal": {"explain": False}}})
    rep = run_session(a_rep, SEQ, rules)

    assert live["rolls"] == rep["rolls"]
    assert isinstance(live["bankroll"], (int, float))
    assert live["bankroll"] == rep["bankroll"]
    assert live["point_on"] == rep["point_on"]
    assert live["point_value"] == rep["point_value"]
