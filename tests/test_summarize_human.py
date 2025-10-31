import json
import subprocess
import sys
from pathlib import Path


def _fake_artifacts(tmp_path: Path) -> Path:
    a = tmp_path / "artifacts" / "run_0001"
    a.mkdir(parents=True)
    (a / "summary.json").write_text(
        json.dumps(
            {
                "stats": {"pso_count": 0, "max_drawdown": 0},
                "bankroll": {"peak": 1000, "trough": 900},
            }
        )
    )
    (a / "manifest.json").write_text(json.dumps({"run": {"flags": {"explain": True}}}))
    (a / "decisions.csv").write_text(
        "roll,window,rule_id,when_expr,evaluated_true,applied,reason,bankroll,point_on,hand_id,roll_in_hand\n"
    )
    return a


def test_summarize_human_creates_report(tmp_path: Path):
    a = _fake_artifacts(tmp_path)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "crapssim_control",
            "summarize",
            "--artifacts",
            str(a),
            "--human",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    report = a / "report.md"
    assert report.exists()
    assert report.read_text().strip()
