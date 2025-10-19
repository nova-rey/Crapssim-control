import json
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.external.http_api import start_http_server


def _get(url: str) -> tuple[int, str]:
    with urllib_request.urlopen(url, timeout=2.0) as resp:
        return resp.getcode(), resp.read().decode("utf-8")


def test_http_server_boot_health_ok():
    queue = CommandQueue()
    handle = start_http_server(queue, lambda: "run-boot", host="127.0.0.1", port=8090)
    try:
        code, body = _get("http://127.0.0.1:8090/health")
        assert code == 200
        payload = json.loads(body)
        assert payload["status"] == "ok"
    finally:
        handle.stop()


def test_http_server_fallback_on_uvicorn_failure(monkeypatch):
    queue = CommandQueue()

    import uvicorn

    def boom(self):  # pragma: no cover - monkeypatch helper
        raise OSError("port in use")

    monkeypatch.setattr(uvicorn.Server, "serve", boom, raising=False)

    handle = start_http_server(queue, lambda: "run-fallback", host="127.0.0.1", port=8091)
    try:
        assert not handle.using_uvicorn
        code, body = _get("http://127.0.0.1:8091/health")
        assert code == 200
        payload = json.loads(body)
        assert payload["status"] == "ok"
    finally:
        handle.stop()


def test_http_server_unknown_route_returns_404():
    queue = CommandQueue()
    handle = start_http_server(queue, lambda: "run-boot", host="127.0.0.1", port=8092)
    try:
        with pytest.raises(urllib_error.HTTPError) as excinfo:
            urllib_request.urlopen("http://127.0.0.1:8092/does-not-exist", timeout=2.0)
        assert excinfo.value.code == 404
    finally:
        handle.stop()
