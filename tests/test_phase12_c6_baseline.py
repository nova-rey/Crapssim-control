import json
from pathlib import Path


def test_phase12_baseline_files_exist():
    base = Path("baselines/phase12")
    for filename in ["phase12_digest.md"]:
        assert (base / filename).exists(), f"{filename} missing"

    live_manifest = json.load(open(base / "live_run" / "manifest.json"))
    replay_manifest = json.load(open(base / "replay_run" / "manifest.json"))

    for key in ["terminated_early", "termination_reason", "rolls_completed", "rolls_requested"]:
        assert key in live_manifest and key in replay_manifest
        assert live_manifest[key] == replay_manifest[key]
