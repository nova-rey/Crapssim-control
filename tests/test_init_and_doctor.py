import json
import subprocess
import sys
from pathlib import Path


def test_init_and_doctor(tmp_path: Path):
    target = tmp_path / "proj"
    # init
    r = subprocess.run([sys.executable, "-m", "crapssim_control", "init", str(target)], check=False)
    assert r.returncode == 0
    spec = json.loads((target / "spec.json").read_text())
    assert "schema_version" in spec and "profiles" in spec
    # doctor ok
    r2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "crapssim_control",
            "doctor",
            "--spec",
            str(target / "spec.json"),
        ],
        check=False,
    )
    assert r2.returncode == 0
