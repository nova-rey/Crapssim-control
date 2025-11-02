from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from crapssim_control.http_app import create_app


def _make_min_spec(tmp: Path) -> Path:
    spec = {
        "schema_version": "1.0",
        "table": {"min_bet": 5, "odds": "3-4-5x"},
        "profiles": {"default": {"bets": [{"type": "pass_line", "amount": 5}]}},
        "modes": {"Default": {"template": {}}},
        "rules": [],
        "behavior": {"schema_version": "1.0", "rules": []},
        "run": {"strict": False, "demo_fallbacks": False, "csv": {"embed_analytics": True}},
    }
    path = tmp / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_ui_lists_and_shows_run(tmp_path: Path):
    app = create_app(mount_ui=True)
    client = TestClient(app)
    artifacts_root = tmp_path / "artifacts"
    app.state.CSC_ARTIFACTS_DIR = str(artifacts_root)

    spec = _make_min_spec(tmp_path)
    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = os.pathsep.join(
        [str(project_root), env.get("PYTHONPATH", "")]
        if env.get("PYTHONPATH")
        else [str(project_root)]
    )
    result = subprocess.run(  # noqa: S603,S607 - intentional CLI invocation
        [
            sys.executable,
            "-m",
            "csc",
            "run",
            "--spec",
            str(spec),
            "--seed",
            "4242",
            "--explain",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    time.sleep(0.2)

    res = client.get("/ui")
    assert res.status_code == 200

    runs = [p for p in artifacts_root.iterdir() if p.is_dir()]
    assert runs
    run_id = runs[0].name

    detail = client.get(f"/ui/runs/{run_id}")
    assert detail.status_code == 200

    summ = client.post(f"/ui/runs/{run_id}/summarize", allow_redirects=False)
    assert summ.status_code in (302, 303)
