from fastapi.testclient import TestClient

from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import create_app


def test_post_commands_accept_and_reject(monkeypatch):
    q = CommandQueue()
    app = create_app(q, active_run_id_supplier=lambda: "r1")
    client = TestClient(app)

    # unknown action
    resp = client.post(
        "/commands",
        json={
            "run_id": "r1",
            "action": "explode",
            "args": {},
            "source": "nr",
            "correlation_id": "x",
        },
    )
    assert resp.status_code == 400

    # happy path
    resp = client.post(
        "/commands",
        json={
            "run_id": "r1",
            "action": "switch_profile",
            "args": {"name": "Recovery"},
            "source": "nr",
            "correlation_id": "y",
        },
    )
    assert resp.status_code == 202
