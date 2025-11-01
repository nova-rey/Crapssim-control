import json
import os
import sys
import subprocess
from pathlib import Path

from crapssim_control.commands.run_cmd import _emit_per_run_artifacts


def test_per_run_summary_is_written_even_without_export(tmp_path: Path) -> None:
    spec = {
        "schema_version": "1.0",
        "table": {"min_bet": 5, "odds": "3-4-5x"},
        "profiles": {"default": {"bets": [{"type": "pass_line", "amount": 5}]}},
        "modes": {"Default": {"template": {}}},
        "rules": [],
        "behavior": {"schema_version": "1.0", "rules": []},
        "run": {"csv": {"embed_analytics": True}},
    }

    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")

    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(project_root), existing]))

    result = subprocess.run(
        [sys.executable, "-m", "csc", "run", "--spec", "spec.json", "--seed", "4242", "--explain"],
        cwd=tmp_path,
        check=False,
        text=True,
        env=env,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr

    runs = [p for p in (tmp_path / "artifacts").iterdir() if p.is_dir()]
    assert runs

    summary_path = runs[0] / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert isinstance(summary, dict)


def test_emit_per_run_artifacts_writes_summary_for_truthy_empty_mapping(tmp_path: Path) -> None:
    class TruthyMapping(dict):
        def __bool__(self) -> bool:
            return True

    run_dir = tmp_path / "run"
    manifest = {"ok": True}

    _emit_per_run_artifacts(run_dir, manifest, summary=TruthyMapping())

    summary_path = run_dir / "summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data == {}
