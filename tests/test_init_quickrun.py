import csv
import os
import subprocess
import sys
from pathlib import Path


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


def _assert_artifacts(run_dir: Path) -> None:
    decisions_path = run_dir / "decisions.csv"
    summary_path = run_dir / "summary.json"
    manifest_path = run_dir / "manifest.json"
    journal_path = run_dir / "journal.csv"

    assert decisions_path.exists()
    with decisions_path.open(newline="", encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    assert rows

    assert summary_path.exists()
    assert manifest_path.exists()
    assert journal_path.exists()


def test_init_doctor_and_quick_run(tmp_path):
    result_init = _run_cli(tmp_path, "init", str(tmp_path))
    assert result_init.returncode == 0, result_init.stderr

    result_doctor = _run_cli(tmp_path, "doctor", "--spec", "spec.json")
    assert result_doctor.returncode == 0, result_doctor.stderr

    result_run = _run_cli(
        tmp_path,
        "run",
        "--spec",
        "spec.json",
        "--seed",
        "4242",
        "--explain",
    )
    assert result_run.returncode == 0, result_run.stderr

    artifacts_root = tmp_path / "artifacts"
    run_dirs = [p for p in artifacts_root.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    _assert_artifacts(run_dirs[0])
