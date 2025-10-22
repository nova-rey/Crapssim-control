import json

from crapssim_control.transport import HTTPTransport, TRANSPORTS


def fake_urlopen(req, timeout=5):
    class FakeResp:
        def read(self):
            endpoint = getattr(req, "full_url", req)
            return json.dumps({"ok": True, "endpoint": endpoint}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return FakeResp()


def test_http_transport_registry():
    assert "http" in TRANSPORTS
    transport = TRANSPORTS["http"]()
    assert isinstance(transport, HTTPTransport)


def test_http_transport_basic(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    transport = HTTPTransport(base_url="http://mock/api/engine")

    version = transport.version()
    assert "ok" in version

    capabilities = transport.capabilities()
    assert "endpoint" in capabilities

    transport.start_session({"run": {}})

    response = transport.apply("line_bet", {"amount": {"mode": "dollars", "value": 10}})
    assert response["ok"]

    roll = transport.step(dice=(3, 4))
    assert "ok" in roll


def test_http_transport_error(monkeypatch):
    def raise_error(*args, **kwargs):
        raise Exception("network down")

    monkeypatch.setattr("urllib.request.urlopen", raise_error)

    transport = HTTPTransport()
    result = transport.version()
    assert "error" in result
