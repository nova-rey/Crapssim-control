import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_run_produces_required_artifacts(tmp_path):
    spec = {
        "schema_version": "1.0",
        "table": {"min_bet": 5, "odds": "3-4-5x"},
        "profiles": {"default": {"bets": [{"type": "pass_line", "amount": 5}]}},
        "modes": {"Default": {"template": {}}},
        "rules": [],
        "behavior": {"schema_version": "1.0", "rules": []},
        "run": {"csv": {"embed_analytics": True}},
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    env = {**os.environ}
    project_root = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(project_root)
        if not existing
        else os.pathsep.join([str(project_root), existing])
    )

    result = subprocess.run(
        [sys.executable, "-m", "csc", "run", "--spec", str(spec_path), "--seed", "4242"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    artifacts_dir = tmp_path / "artifacts"
    run_dirs = [p for p in artifacts_dir.iterdir() if p.is_dir()]
    assert run_dirs, "no run directories created"
    run_dir = run_dirs[0]

    expected = ["summary.json", "manifest.json", "journal.csv", "decisions.csv"]
    for name in expected:
        path = run_dir / name
        assert path.exists(), f"{name} missing"
        if name.endswith(".json"):
            with path.open(encoding="utf-8") as handle:
                json.load(handle)
        elif name.endswith(".csv"):
            with path.open(newline="", encoding="utf-8") as handle:
                list(csv.reader(handle))
