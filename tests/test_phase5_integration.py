from crapssim_control.engine_adapter import VanillaAdapter
from crapssim_control.rules_engine.actions import ACTIONS
from crapssim_control.rules_engine.evaluator import evaluate_rules
from crapssim_control.rules_engine.journal import DecisionJournal


def test_internal_brain_end_to_end(tmp_path):
    rules = [
        {
            "id": "R1",
            "when": "bankroll_after < 500",
            "scope": "session",
            "cooldown": 2,
            "action": "switch_profile('Recovery')",
            "enabled": True,
        },
        {
            "id": "R2",
            "when": "box_hits >= 2",
            "scope": "hand",
            "cooldown": 1,
            "action": "apply_policy('martingale_v1')",
            "enabled": True,
        },
    ]
    ctx = {"bankroll_after": 400, "box_hits": 3, "point_on": False}
    fired = evaluate_rules(rules, ctx)
    rule_lookup = {r["id"]: r for r in rules}
    journal_path = tmp_path / "dj.jsonl"
    journal = DecisionJournal(journal_path)
    adapter = VanillaAdapter()
    controller = type("Controller", (), {"adapter": adapter})()

    for result in fired:
        rule = rule_lookup.get(result.get("rule_id"))
        if not rule:
            continue
        result["action"] = rule["action"]
        verb = result["action"].split("(")[0]
        action = ACTIONS.get(verb)
        if action is None:
            continue
        args = {}
        if verb == "switch_profile":
            args = {"details": {"profile": "Recovery"}}
        elif verb == "apply_policy":
            args = {
                "policy": {
                    "name": "martingale_v1",
                    "args": {"step_key": "6", "delta": 6, "max_level": 3},
                }
            }
        executed = action.execute({"adapter": adapter}, {"args": args})
        result.update({"executed": True, "result": executed})
        journal.record(result, controller=controller)

    text = journal_path.read_text()
    assert "switch_profile" in text and "apply_policy" in text
