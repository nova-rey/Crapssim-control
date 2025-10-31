import os
import subprocess
import sys
from pathlib import Path


def test_csc_module_alias_invokes_cli(tmp_path):
    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(project_root), existing]))
    result = subprocess.run(
        [sys.executable, "-m", "csc", "--help"],
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "run" in result.stdout
    assert "--explain" in result.stdout
