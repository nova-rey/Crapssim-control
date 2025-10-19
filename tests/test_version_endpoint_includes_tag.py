from fastapi.testclient import TestClient

from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import create_app, _load_snapshot_tag


def test_version_endpoint_includes_tag_value():
    queue = CommandQueue()
    app = create_app(queue, active_run_id_supplier=lambda: "run-tag-check")
    assert app is not None

    client = TestClient(app)
    resp = client.get("/version")
    assert resp.status_code == 200
    payload = resp.json()

    assert "tag" in payload
    assert isinstance(payload["tag"], str)
    snapshot_tag = _load_snapshot_tag()
    if snapshot_tag:
        assert payload["tag"] == snapshot_tag
