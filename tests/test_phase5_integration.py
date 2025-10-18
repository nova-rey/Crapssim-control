import json
from crapssim_control.rules_engine.evaluator import evaluate_rules
from crapssim_control.rules_engine.actions import ACTIONS
from crapssim_control.rules_engine.journal import DecisionJournal

def test_internal_brain_end_to_end(tmp_path):
    rules = [
        {"id": "R1", "when": "bankroll_after < 500", "scope": "session", "cooldown": 2,
         "action": "switch_profile('Recovery')", "enabled": True},
        {"id": "R2", "when": "box_hits >= 2", "scope": "hand", "cooldown": 1,
         "action": "press_and_collect('standard')", "enabled": True}
    ]
    ctx = {"bankroll_after": 400, "box_hits": 3, "point_on": False}
    fired = evaluate_rules(rules, ctx)
    rule_lookup = {r["id"]: r for r in rules}
    journal_path = tmp_path / "dj.jsonl"
    j = DecisionJournal(journal_path)
    for f in fired:
        rule = rule_lookup.get(f.get("rule_id"))
        if not rule:
            continue
        f["action"] = rule["action"]
        verb = f["action"].split("(")[0]
        act = ACTIONS.get(verb)
        res = act.execute({}, f)
        f.update({"executed": True, "result": res})
        j.record(f)
    text = journal_path.read_text()
    assert "switch_profile" in text and "press_and_collect" in text
