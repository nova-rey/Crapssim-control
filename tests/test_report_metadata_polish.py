import json
import shutil
from pathlib import Path

import pytest

from crapssim_control.cli_flags import CLIFlags
from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED
from crapssim_control.integrations.hooks import Outbound


def _build_spec(csv_path: Path) -> dict:
    return {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass": 10}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]},
        ],
        "run": {
            "demo_fallbacks": True,
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "TRACE-RUN",
                "seed": 4242,
            },
        },
    }


def _execute_run(monkeypatch: pytest.MonkeyPatch | None = None):
    export_dir = Path("export")
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    calls: list[tuple[str, dict]] = []
    if monkeypatch is not None:

        def fake_emit(self, event: str, payload: dict):
            calls.append((event, payload))
            return True

        monkeypatch.setattr(Outbound, "emit", fake_emit, raising=True)

    csv_path = export_dir / "journal.csv"
    spec = _build_spec(csv_path)
    cli_flags = CLIFlags(
        export=True,
        export_source="cli",
        webhook_url="https://example.invalid/hook",
        webhook_url_source="cli",
        webhook_enabled=True,
        webhook_enabled_source="cli",
    )

    controller = ControlStrategy(spec, cli_flags=cli_flags)
    controller.handle_event({"type": COMEOUT}, current_bets={})
    controller.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    controller.finalize_run()
    controller.generate_report(report_path=export_dir / "report.json")

    report_path = export_dir / "report.json"
    manifest_path = export_dir / "manifest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return report, manifest, calls


def test_run_id_and_manifest_path_present():
    report, manifest, _ = _execute_run()
    assert report["run_id"] == manifest["run_id"]
    assert report["manifest_path"].endswith("export/manifest.json")


def test_engine_and_artifacts_blocks():
    report, _manifest, _ = _execute_run()
    eng = report["metadata"]["engine"]
    arts = report["metadata"]["artifacts"]
    assert eng["name"] == "CrapsSim-Control"
    assert isinstance(eng["python"], str) and len(eng["python"]) >= 3
    assert set(["journal", "report", "manifest"]).issubset(arts.keys())


def test_run_flags_provenance():
    report, _manifest, _ = _execute_run()
    rf = report["metadata"]["run_flags"]
    for key, value in list(rf.items()):
        if key.endswith("_source"):
            assert value in {"cli", "spec", "default"}


def test_webhook_payload_includes_run_id(monkeypatch):
    report, manifest, calls = _execute_run(monkeypatch)
    assert calls, "no events captured; ensure test harness triggers a run"
    for _, payload in calls:
        assert "run_id" in payload
    assert report["run_id"] == manifest["run_id"]
