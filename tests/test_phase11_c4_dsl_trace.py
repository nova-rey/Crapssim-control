import pytest

from crapssim_control.rule_engine import RuleEngine
from crapssim_control.dsl_eval import compile_expr


def compiled(r):
    r["_compiled"] = compile_expr(r["when"])
    return r


def test_trace_enabled_and_disabled(monkeypatch):
    from crapssim_control.engine_adapter import VanillaAdapter

    a = VanillaAdapter()
    a.start_session({"run": {"journal": {"explain": False}}})
    rule = compiled(
        {
            "id": "r1",
            "when": "point_on",
            "then": {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
        }
    )
    a.rule_engine = RuleEngine([rule])
    monkeypatch.setattr(a, "snapshot_state", lambda: {"point_on": True, "roll_in_hand": 1})
    calls = []
    a.apply_action = lambda v, a_: calls.append((v, a_))
    a.transport.step = lambda dice=None, seed=None: {"rolled": True}
    # Tracing disabled
    a.enable_dsl_trace(False)
    out1 = a.step_roll((3, 4))
    # Tracing enabled
    a.enable_dsl_trace(True)
    out2 = a.step_roll((4, 3))
    assert out1 and out2
    assert calls and calls[0][0] == "place_bet"


def test_trace_record_format():
    rule = compiled(
        {"id": "r1", "when": "point_on", "then": {"verb": "field_bet", "args": {"amount": 5}}}
    )
    r = RuleEngine([rule])
    acts, traces = r.evaluate({"point_on": True, "roll_in_hand": 1}, trace_enabled=True)
    assert traces and traces[0]["evaluated_true"] is True
    assert "dsl_trace" in traces[0]["type"]
