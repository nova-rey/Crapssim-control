import json
from pathlib import Path
from crapssim_control.varstore import VarStore
from crapssim_control.rules import run_rules_for_event

def _load_spec():
    p = Path("examples/martingale.json")
    assert p.exists(), "examples/martingale.json missing"
    return json.loads(p.read_text())

def test_martingale_ladder_and_reset():
    spec = _load_spec()
    vs = VarStore.from_spec(spec)
    # system vars needed by template legalization
    vs.system = {"bubble": False, "table_level": 10}

    # initial apply on comeout
    intents = run_rules_for_event(spec, vs, {"event":"comeout"})
    # should lay pass at base_units (10) -> rounds to 10/20 depending on step
    assert any(k == "pass" for (k, _, _) in intents)

    # lose 1 → units doubles to 20
    intents = run_rules_for_event(spec, vs, {"event":"bet_resolved","bet":"pass","result":"lose"})
    assert vs.user["units"] == 20
    assert any(k == "pass" for (k, _, _) in intents)

    # lose 2 → units doubles to 40 (capped later)
    run_rules_for_event(spec, vs, {"event":"bet_resolved","bet":"pass","result":"lose"})
    assert vs.user["units"] == 40

    # lose 3 → doubles to 80 but cap = base_units * cap_mult = 10 * 4 = 40
    run_rules_for_event(spec, vs, {"event":"bet_resolved","bet":"pass","result":"lose"})
    assert vs.user["units"] == 40  # capped

    # win → reset to base
    run_rules_for_event(spec, vs, {"event":"bet_resolved","bet":"pass","result":"win"})
    assert vs.user["units"] == vs.user["base_units"] == 10