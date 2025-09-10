from crapssim_control.rules import run_rules_for_event
from crapssim_control.varstore import VarStore

def _kinds(intents):
    ks = []
    for it in intents:
        if len(it) == 3:
            k, n, a = it
        else:
            k, n, a, _ = it
        ks.append((k, n))
    return ks

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
    kinds = _kinds(intents)
    assert ("pass", None) in kinds
    assert vs.user["units"] >= 20  # increment happened

    ev_win = {"event":"bet_resolved","bet":"pass","result":"win"}
    intents2 = run_rules_for_event(spec, vs, ev_win)
    kinds2 = _kinds(intents2)
    assert ("pass", None) in kinds2
    assert vs.user["units"] == 10