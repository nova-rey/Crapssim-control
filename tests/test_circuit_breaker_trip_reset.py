import json
import time
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, ROLL


def _spec(limits):
    return {
        "table": {"bubble": False, "level": 10},
        "modes": {"Main": {"template": {}}},
        "variables": {"units": 10},
        "run": {
            "webhooks": {"enabled": False},
            "http_commands": {"enabled": False},
            "external": {"limits": limits},
        },
    }


def test_circuit_breaker_trip_reset(tmp_path):
    limits = {
        "queue_max_depth": 10,
        "per_source_quota": 5,
        "rate": {"tokens": 5, "refill_seconds": 0.01},
        "circuit_breaker": {"consecutive_rejects": 3, "cool_down_seconds": 0.2},
    }
    ctrl = ControlStrategy(_spec(limits))
    ctrl.journal.path = str(tmp_path / "journal.jsonl")

    bad_cmd = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "late"},
        "source": "src",
        "correlation_id": " ",
    }

    for _ in range(3):
        ok, reason = ctrl.command_queue.enqueue(bad_cmd)
        assert not ok
        assert reason == "missing:correlation_id"

    blocked_cmd = dict(bad_cmd)
    blocked_cmd["correlation_id"] = "blocked"

    ok, reason = ctrl.command_queue.enqueue(blocked_cmd)
    assert not ok and reason == "circuit_breaker"

    time.sleep(0.25)

    good_cmd = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "reset"},
        "source": "src",
        "correlation_id": "good-1",
    }

    ok, reason = ctrl.command_queue.enqueue(good_cmd)
    assert ok and reason == "accepted"

    ctrl.handle_event({"type": COMEOUT}, current_bets={})
    ctrl.handle_event({"type": ROLL, "roll": 8, "point": None, "on_comeout": True}, current_bets={})

    entries = [
        json.loads(line)
        for line in Path(ctrl.journal.path).read_text(encoding="utf-8").splitlines()
        if line
    ]
    external_entries = [
        entry for entry in entries if entry.get("origin", "").startswith("external:src")
    ]

    assert external_entries, "expected external command entries in journal"
    last_entry = external_entries[-1]
    assert last_entry.get("executed") is True
    assert last_entry.get("circuit_breaker_reset") is True

