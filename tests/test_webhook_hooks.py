def test_flag_off_no_emit(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=2.0):
        calls.append(("url", req.full_url, timeout))
        class R:
            status = 200
        return R()

    # Even if patched, without flags enabled nothing should be emitted.
    from crapssim_control.integrations.hooks import Outbound
    ob = Outbound(enabled=False, url=None)
    assert ob.emit("run.started", {"a": 1}) is False
    assert calls == []


def test_emit_success(monkeypatch):
    def fake_urlopen(req, timeout=2.0):
        class R:
            status = 200
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False
        return R()

    monkeypatch.setattr("crapssim_control.integrations.hooks.urlopen", fake_urlopen)
    from crapssim_control.integrations.hooks import Outbound
    ob = Outbound(enabled=True, url="http://example.local/hook")
    ok = ob.emit("run.started", {"x": 1})
    assert ok is True


def test_emit_failure_is_safe(monkeypatch):
    def fake_urlopen(req, timeout=2.0):
        raise OSError("boom")

    monkeypatch.setattr("crapssim_control.integrations.hooks.urlopen", fake_urlopen)
    from crapssim_control.integrations.hooks import Outbound
    ob = Outbound(enabled=True, url="http://example.local/hook")
    ok = ob.emit("run.finished", {"y": 2})
    assert ok is False
