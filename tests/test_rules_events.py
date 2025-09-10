from crapssim_control.rules import run_rules_for_event
from crapssim_control.varstore import VarStore

def test_rule_matching_all_keys():
    spec = {
        "variables": {"units": 10, "mode": "Aggressive"},
        "modes": {"Aggressive": {"template": {"pass": "units"}}},
        "rules": [
            {"on":{"event":"bet_resolved","bet":"pass","result":"lose"},
             "do":["units += 10","apply_template('Aggressive')"]},
            {"on":{"event":"bet_resolved","bet":"pass","result":"win"},
             "do":["units = 10","apply_template('Aggressive')"]},
        ]
    }
    vs = VarStore.from_spec(spec)
    vs.system = {"bubble": False, "table_level": 10}

    ev_lose = {"event":"bet_resolved","bet":"pass","result":"lose"}
    intents = run_rules_for_event(spec, vs, ev_lose)
    # should apply pass with units=20 after increment
    kinds = [(k, n) for (k, n, a) in intents]
    assert ("pass", None) in kinds

    ev_win = {"event":"bet_resolved","bet":"pass","result":"win"}
    intents2 = run_rules_for_event(spec, vs, ev_win)
    kinds2 = [(k, n) for (k, n, a) in intents2]
    assert ("pass", None) in kinds2