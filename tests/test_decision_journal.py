from crapssim_control.rules_engine.journal import DecisionJournal


def test_cooldown_blocks_refire(tmp_path):
    j = DecisionJournal(tmp_path / "dj.jsonl")
    j.cooldowns["R1"] = 2
    ok, reason = j.can_fire("R1", "roll", 2)
    assert not ok and "cooldown" in reason


def test_scope_lock_blocks_repeats(tmp_path):
    j = DecisionJournal(tmp_path / "dj.jsonl")
    j.scope_flags.add("R2")
    ok, reason = j.can_fire("R2", "hand", 3)
    assert not ok and reason == "scope_locked"


def test_record_writes_json(tmp_path):
    path = tmp_path / "dj.jsonl"
    j = DecisionJournal(path)
    j.record({"rule_id": "R3", "executed": True})
    text = path.read_text()
    assert "R3" in text and "timestamp" in text


def test_tick_reduces_cooldowns():
    j = DecisionJournal()
    j.cooldowns = {"R1": 2}
    j.tick()
    assert j.cooldowns["R1"] == 1
