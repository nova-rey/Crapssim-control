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
            "external": {},
        },
    }


def test_journal_rejection_reasons(tmp_path):
    ctrl = ControlStrategy(_spec())
    ctrl.journal.path = str(tmp_path / "journal.jsonl")

    ctrl.memory["point_on"] = True
    ctrl.memory["roll_in_hand"] = 1

    timing_cmd = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "timing"},
        "source": "src",
        "correlation_id": "timing-1",
    }

    ok, reason = ctrl.command_queue.enqueue(timing_cmd)
    assert ok and reason == "accepted"

    ctrl.handle_event(
        {"type": ROLL, "roll": 9, "point": 6, "on_comeout": False},
        current_bets={},
    )

    ctrl.memory.pop("point_on", None)
    ctrl.memory.pop("roll_in_hand", None)

    ctrl.handle_event({"type": COMEOUT}, current_bets={})

    dup_base = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "dup"},
        "source": "src",
    }

    for idx in range(2):
        ok, reason = ctrl.command_queue.enqueue({**dup_base, "correlation_id": f"dup-{idx}"})
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

    reasons = [
        entry.get("rejection_reason") for entry in external_entries if entry.get("rejection_reason")
    ]

    allowed = {
        "queue_full",
        "per_source_quota",
        "rate_limited",
        "duplicate_roll",
        "circuit_breaker",
        "unknown_action",
        "run_id_mismatch",
    }

    for reason in reasons:
        assert reason in allowed or reason.startswith("timing:") or reason.startswith("missing:")
