import json

from crapssim_control.integrations.evo_hooks import EvoBridge


def test_disabled_no_log(tmp_path):
    log_file = tmp_path / "evo_stub.log"
    bridge = EvoBridge(enabled=False, log_dir=tmp_path)
    bridge.announce_run({"run_id": "abc"})
    assert not log_file.exists()


def test_enabled_logs(tmp_path):
    bridge = EvoBridge(enabled=True, log_dir=tmp_path)
    bridge.announce_run({"run_id": "r123"})
    log_file = tmp_path / "evo_stub.log"
    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["event"] == "announce_run"
    assert entry["payload"]["run_id"] == "r123"


def test_manifest_includes_evo_block(tmp_path):
    from crapssim_control.manifest import generate_manifest

    outputs = {"journal": "j.csv", "report": "r.json", "manifest": "m.json"}
    cli_flags = {"evo_enabled": True, "trial_tag": "test_group"}
    manifest = generate_manifest("spec.json", cli_flags, outputs)
    assert "evo" in manifest
    assert manifest["evo"]["enabled"] is True
    assert manifest["evo"]["trial_tag"] == "test_group"
