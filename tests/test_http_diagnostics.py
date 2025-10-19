from fastapi.testclient import TestClient

from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import create_app, _load_snapshot_tag


def test_diagnostics_endpoints_expose_version():
    q = CommandQueue()

    app = create_app(
        q,
        active_run_id_supplier=lambda: "run-xyz",
        version_supplier=lambda: "engine-1.0",
        build_hash_supplier=lambda: "abcdef",
    )

    assert app is not None, "FastAPI should be available for diagnostics test"
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    run_id = client.get("/run_id")
    assert run_id.status_code == 200
    assert run_id.json()["run_id"] == "run-xyz"

    version = client.get("/version")
    assert version.status_code == 200
    body = version.json()
    assert body["version"] == "engine-1.0"
    assert body["build_hash"] == "abcdef"
    assert "tag" in body
    assert isinstance(body["tag"], str)
    snapshot_tag = _load_snapshot_tag()
    if snapshot_tag:
        assert body["tag"] == snapshot_tag
