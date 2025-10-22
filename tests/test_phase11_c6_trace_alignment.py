import pytest


def test_trace_alignment_grouping(monkeypatch):
    from crapssim_control.engine_adapter import VanillaAdapter
    from crapssim_control.rule_engine import RuleEngine
    from crapssim_control.dsl_eval import compile_expr

    rules = [
        {
            "id": "r6",
            "when": "NOT point_on",
            "then": {"verb": "line_bet", "args": {"side": "pass", "amount": 10}},
        },
        {
            "id": "r68",
            "when": "point_on AND bets.6 == 0",
            "then": {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
        },
    ]
    for r in rules:
        r["_compiled"] = compile_expr(r["when"])

    a = VanillaAdapter()
    a.start_session(
        {
            "run": {
                "journal": {
                    "explain": True,
                    "explain_grouping": "first_only",
                    "dsl_trace": True,
                }
            }
        }
    )
    a.enable_dsl_trace(True)
    a.rule_engine = RuleEngine(rules)

    class StubJournal:
        def __init__(self):
            self.entries = []

        def append(self, entry):
            self.entries.append(entry)

    journal_stub = StubJournal()
    a.journal = journal_stub

    snaps = [
        {"point_on": False, "roll_in_hand": 0},
        {"point_on": True, "roll_in_hand": 1, "bets": {"6": 0}},
    ]
    it = iter(snaps)
    monkeypatch.setattr(a, "snapshot_state", lambda: next(it, snaps[-1]))

    a.transport.step = lambda dice=None, seed=None: {"rolled": True}

    a.step_roll(dice=(3, 4))
    a.step_roll(dice=(2, 2))

    events = journal_stub.entries
    traces = [e for e in events if isinstance(e, dict) and e.get("type") == "dsl_trace"]
    whys = [e.get("why", "") for e in events if isinstance(e, dict) and "why" in e]
    assert traces, "expected at least one DSL trace line"
    assert any("WHEN (" in w for w in whys)
