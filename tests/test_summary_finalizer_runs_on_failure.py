import json
import os
import subprocess
import sys
from pathlib import Path


def test_finalizer_writes_summary_even_if_export_missing(tmp_path: Path) -> None:
    spec = {
        "schema_version": "1.0",
        "table": {"min_bet": 5, "odds": "3-4-5x"},
        "profiles": {"default": {"bets": [{"type": "pass_line", "amount": 5}]}},
        "behavior": {"schema_version": "1.0", "rules": []},
        "run": {"csv": {"embed_analytics": True}},
    }
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")

    env = os.environ.copy()
    env.pop("CSC_DEBUG", None)
    project_root = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(project_root), existing]))

    result = subprocess.run(
        [sys.executable, "-m", "csc", "run", "--spec", "spec.json", "--seed", "4242", "--explain"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env=env,
    )

    artifacts_dir = tmp_path / "artifacts"
    runs = [p for p in artifacts_dir.iterdir() if p.is_dir()] if artifacts_dir.exists() else []
    assert runs, result.stderr + result.stdout

    run_path = runs[0]
    assert (run_path / "summary.json").exists()
    assert (run_path / "manifest.json").exists()
