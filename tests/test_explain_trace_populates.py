import csv
import json
import os
import subprocess
import sys
from pathlib import Path


SPEC = {
    "schema_version": "1.0",
    "table": {"min_bet": 5, "odds": "3-4-5x"},
    "profiles": {
        "default": {
            "bets": [
                {"type": "pass_line", "amount": 5},
            ]
        }
    },
    "modes": {"Default": {"template": {}}},
    "rules": [],
    "behavior": {"schema_version": "1.0", "rules": []},
    "run": {"strict": False, "demo_fallbacks": False, "csv": {"embed_analytics": True}},
}


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(project_root), existing]))
    cmd = [sys.executable, "-m", "csc", *args]
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_explain_populates_decisions_and_artifacts(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")

    result = _run_cli(
        tmp_path,
        "run",
        "--spec",
        "spec.json",
        "--seed",
        "4242",
        "--explain",
    )
    assert result.returncode == 0, result.stderr

    artifacts_root = tmp_path / "artifacts"
    run_dirs = [p for p in artifacts_root.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    decisions_path = run_dir / "decisions.csv"
    assert decisions_path.exists()
    with decisions_path.open(newline="", encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    assert rows, "decisions.csv should contain at least one data row"

    summary_path = run_dir / "summary.json"
    manifest_path = run_dir / "manifest.json"
    journal_path = run_dir / "journal.csv"
    assert summary_path.exists()
    assert manifest_path.exists()
    assert journal_path.exists()
