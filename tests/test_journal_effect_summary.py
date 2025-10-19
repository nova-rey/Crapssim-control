from crapssim_control.rules_engine.journal import DecisionJournal
from crapssim_control.engine_adapter import VanillaAdapter


def test_journal_includes_effect_summary(tmp_path):
    adapter = VanillaAdapter()
    adapter.apply_action("press", {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}})
    journal = DecisionJournal(tmp_path / "journal.jsonl")
    record = {
        "rule_id": "r1",
        "action": "press",
        "timestamp": 0,
        "effect_summary": adapter.last_effect,
    }
    saved = journal.record(record)
    assert saved["effect_summary"] == adapter.last_effect
    assert journal.entries[-1]["effect_summary"] == adapter.last_effect
