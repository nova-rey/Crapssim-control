import json

from crapssim_control.rules_engine.journal import DecisionJournal


def test_unified_journal_fields(tmp_path):
    path = tmp_path / "decision_journal.jsonl"
    journal = DecisionJournal(str(path))
    writer = journal.writer()

    writer.write(
        run_id="run-1",
        origin="rule:R1",
        action="press_and_collect",
        args={"pattern": "mid-stairs"},
        executed=True,
        extra={"hand_id": 1, "roll_in_hand": 1},
    )

    writer.write(
        run_id="run-1",
        origin="external:test",
        action="regress",
        args={"pattern": "standard"},
        executed=False,
        rejection_reason="timing:block",
        correlation_id="cid-123",
        extra={"hand_id": 1, "roll_in_hand": 2},
    )

    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 2
    first_keys = set(entries[0].keys())
    second_keys = set(entries[1].keys())
    assert first_keys == second_keys
    assert entries[0]["seq"] == 1
    assert entries[1]["seq"] == 2
    assert entries[0]["rejection_reason"] is None
    assert entries[1]["rejection_reason"] == "timing:block"
    assert entries[1]["correlation_id"] == "cid-123"
