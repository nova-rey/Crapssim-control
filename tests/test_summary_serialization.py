import json
from argparse import Namespace
from datetime import datetime

from crapssim_control.cli import _finalize_run_artifacts


class _CustomObject:
    def __str__(self) -> str:  # pragma: no cover - trivial string conversion
        return "custom-object"


def test_finalize_run_artifacts_serializes_non_json_values(tmp_path):
    run_dir = tmp_path / "artifacts"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text("{}", encoding="utf-8")

    summary_payload = {
        "run_id": "run123",
        "spec": str(spec_path),
        "rolls": 5,
        "result": "ok",
        "path_value": tmp_path / "nested",
        "sequence": [tmp_path / "other", _CustomObject()],
        "nested": {
            "path": tmp_path / "inner",
            "timestamp": datetime(2024, 1, 1, 12, 30, 0),
        },
    }

    _finalize_run_artifacts(
        run_dir,
        "run123",
        spec_path,
        Namespace(),
        explain_mode=False,
        explain_source="cli",
        summary=summary_payload,
        decisions_writer=None,
    )

    summary_path = run_dir / "summary.json"
    assert summary_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["path_value"] == str(tmp_path / "nested")
    assert summary["sequence"][0] == str(tmp_path / "other")
    assert summary["sequence"][1] == "custom-object"
    assert summary["nested"]["path"] == str(tmp_path / "inner")
    assert summary["nested"]["timestamp"].startswith("2024-01-01T12:30:00")
