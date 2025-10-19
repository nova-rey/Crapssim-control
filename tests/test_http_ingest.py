import json

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import ROLL
from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import ingest_command


def _spec() -> dict:
    return {
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [],
        "run": {"http_commands": {"enabled": False}},
    }


def test_ingest_run_id_mismatch():
    q = CommandQueue()
    code, payload = ingest_command(
        {
            "run_id": "r2",
            "action": "switch_profile",
            "args": {},
            "source": "nr",
            "correlation_id": "c2",
        },
        q,
        active_run_id_supplier=lambda: "r1",
    )
    assert code == 400
    assert payload["reason"] == "run_id_mismatch"
    assert payload["status"] == "rejected"


def test_ingest_valid_records_journal(tmp_path):
    ctrl = ControlStrategy(_spec())
    journal_path = tmp_path / "journal.jsonl"
    ctrl.journal.path = str(journal_path)
    ctrl._journal_writer = ctrl.journal.writer()

    queue = ctrl.command_queue
    command = {
        "run_id": ctrl.run_id,
        "action": "switch_profile",
        "args": {"target": "Recovery"},
        "source": "node-red@flow",
        "correlation_id": "cid-1",
    }
    code, payload = ingest_command(command, queue, active_run_id_supplier=lambda: ctrl.run_id)
    assert code == 202
    assert payload == {"status": "queued"}

    ctrl.handle_event({"type": ROLL}, {})

    assert journal_path.exists(), "journal file should be created"
    contents = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert contents, "journal should contain at least one entry"
    entries = [json.loads(line) for line in contents]
    entry = next(item for item in entries if item.get("origin", "").startswith("external:"))
    assert entry["origin"].startswith("external:")
    assert entry["correlation_id"] == "cid-1"
    assert entry["executed"] is True
    assert entry["rejection_reason"] is None

    stats = ctrl.command_queue.stats
    assert stats["executed"] >= 1

    ctrl.stop()
