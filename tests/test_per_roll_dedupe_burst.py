import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, ROLL


def _spec():
    return {
        "table": {"bubble": False, "level": 10},
        "modes": {"Main": {"template": {}}},
        "variables": {"units": 10},
        "run": {
            "webhooks": {"enabled": False},
            "http_commands": {"enabled": False},
            "external": {
                "limits": {
                    "rate": {"tokens": 10, "refill_seconds": 0.001},
                    "per_source_quota": 100,
                }
            },
        },
    }


def test_per_roll_dedupe_handles_burst(tmp_path):
    ctrl = ControlStrategy(_spec())
    ctrl.journal.path = str(tmp_path / "journal.jsonl")

    ctrl.handle_event({"type": COMEOUT}, current_bets={})

    base = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "dup"},
        "source": "src",
    }

    total = 5
    for idx in range(total):
        ok, reason = ctrl.command_queue.enqueue({**base, "correlation_id": f"cid-{idx}"})
        assert ok and reason == "accepted"

    ctrl.handle_event(
        {"type": ROLL, "roll": 8, "point": None, "on_comeout": True},
        current_bets={},
    )

    entries = [
        json.loads(line)
        for line in Path(ctrl.journal.path).read_text(encoding="utf-8").splitlines()
        if line
    ]
    external_entries = [
        entry for entry in entries if entry.get("origin", "").startswith("external:src")
    ]

    executed = [entry for entry in external_entries if entry.get("executed")]
    rejected = [entry for entry in external_entries if not entry.get("executed")]

    assert len(executed) == 1
    assert len(rejected) == total - 1
    assert all(entry.get("rejection_reason") == "duplicate_roll" for entry in rejected)
