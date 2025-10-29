from crapssim_control.rule_engine import RuleEngine
from crapssim_control.dsl_eval import compile_expr


def compiled(rule):
    r = dict(rule)
    r["_compiled"] = compile_expr(r["when"])
    return r


SNAP = {"bankroll": 500, "point_on": True, "hand_id": 1, "roll_in_hand": 2, "bets": {"6": 0}}


def test_rule_triggers_and_action_order():
    rules = [
        compiled(
            {
                "id": "r1",
                "when": "point_on",
                "then": {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
                "scope": "roll",
                "cooldown": 0,
                "once": False,
            }
        ),
        compiled(
            {
                "id": "r2",
                "when": "point_on",
                "then": {"verb": "field_bet", "args": {"amount": 5}},
                "scope": "roll",
                "cooldown": 0,
                "once": False,
            }
        ),
    ]
    eng = RuleEngine(rules)
    acts, _ = eng.evaluate(SNAP)
    assert [a["verb"] for a in acts] == ["place_bet", "field_bet"]


def test_cooldown_and_once():
    rules = [
        compiled(
            {
                "id": "r3",
                "when": "point_on",
                "then": {"verb": "field_bet", "args": {"amount": 5}},
                "scope": "roll",
                "cooldown": 1,
                "once": False,
            }
        ),
        compiled(
            {
                "id": "r4",
                "when": "point_on",
                "then": {"verb": "field_bet", "args": {"amount": 5}},
                "scope": "roll",
                "cooldown": 0,
                "once": True,
            }
        ),
    ]
    eng = RuleEngine(rules)
    a1, _ = eng.evaluate(SNAP)
    assert len(a1) == 2
    a2, _ = eng.evaluate(SNAP)
    assert len(a2) == 0


def test_step_roll_integration(monkeypatch):
    from crapssim_control.engine_adapter import VanillaAdapter

    a = VanillaAdapter()
    a.start_session({"run": {"journal": {"explain": False}}})
    a.rule_engine = RuleEngine(
        [
            compiled(
                {
                    "id": "r1",
                    "when": "point_on",
                    "then": {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
                    "scope": "roll",
                    "cooldown": 0,
                    "once": False,
                }
            )
        ]
    )
    monkeypatch.setattr(
        a,
        "snapshot_state",
        lambda: {"point_on": True, "hand_id": 0, "roll_in_hand": 0, "bets": {}},
    )
    calls = []

    def fake_apply(verb, args):
        calls.append((verb, args))
        return {"ok": True}

    a.apply_action = fake_apply

    def fake_step(dice=None, seed=None):
        return {"rolled": True}

    a.transport.step = fake_step
    out = a.step_roll(dice=(3, 4))
    assert calls and calls[0][0] == "place_bet"
    assert out.get("status") == "ok"
