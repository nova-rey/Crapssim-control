from crapssim_control.transport import LocalTransport
from crapssim_control.engine_adapter import VanillaAdapter


def test_local_transport_roundtrip():
    t = LocalTransport()
    t.start_session({"run": {"adapter": {"live_engine": False}}})
    res = t.apply("line_bet", {"amount": {"mode": "dollars", "value": 10}})
    assert res["status"] == "ok"
    snap = t.snapshot()
    assert "bankroll" in snap and isinstance(snap, dict)


def test_adapter_delegates_to_transport(monkeypatch):
    called = {}

    class FakeTransport(LocalTransport):
        def apply(self, verb, args):
            called["verb"] = verb
            return {"verb": verb, "ok": True}

    vt = VanillaAdapter(transport=FakeTransport())
    vt.start_session({})
    result = vt.apply_action("field_bet", {"amount": {"mode": "dollars", "value": 5}})
    assert result["verb"] == "field_bet"
    assert called["verb"] == "field_bet"


def test_capabilities_merge_stable():
    a = VanillaAdapter()
    caps = a.get_capabilities()
    assert "capabilities_schema" in caps
    assert "engine_detected" in caps
