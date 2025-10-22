from crapssim_control.engine_adapter import VanillaAdapter


class DummyTransport:
    def version(self):
        return {"engine": "crapssim", "version": "9.9.9"}

    def capabilities(self):
        return {"supported": {"buy_bet": True, "lay_bet": True}}

    def start_session(self, spec):
        return None


def test_handshake_and_merge():
    adapter = VanillaAdapter(transport=DummyTransport())
    adapter.perform_handshake()
    info = adapter.get_engine_info()
    assert info["engine"] == "crapssim"
    assert info["version"] == "9.9.9"
    merged = adapter.get_capabilities()
    assert merged["source"] == "merged"
    assert "engine_detected" in merged


def test_manifest_includes_engine_info():
    from crapssim_control import manifest

    adapter = VanillaAdapter(transport=DummyTransport())
    adapter.perform_handshake()
    manifest_data = manifest.build_manifest("demo", {}, adapter=adapter)
    assert manifest_data["engine_info"]["engine"] == "crapssim"
    assert manifest_data["capabilities_schema_version"] == "1.1"
    assert manifest_data["capabilities"]["source"] == "merged"
