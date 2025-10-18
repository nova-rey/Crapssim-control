from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import ingest_command


def test_ingest_valid():
    q = CommandQueue()
    code, payload = ingest_command(
        {"run_id": "r1", "action": "switch_profile", "args": {"name": "Recovery"}, "source": "node-red@flow", "correlation_id": "c1"},
        q,
        active_run_id_supplier=lambda: "r1",
    )
    assert code == 202 and payload["status"] == "queued"


def test_ingest_run_id_mismatch():
    q = CommandQueue()
    code, payload = ingest_command(
        {"run_id": "r2", "action": "switch_profile", "args": {}, "source": "nr", "correlation_id": "c2"},
        q,
        active_run_id_supplier=lambda: "r1",
    )
    assert code == 400 and payload["reason"] == "run_id_mismatch"
