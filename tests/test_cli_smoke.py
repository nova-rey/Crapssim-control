# tests/test_cli_smoke.py
import subprocess
import sys
import os
import tempfile
import json
import importlib

import pytest


def _engine_available() -> bool:
    try:
        importlib.import_module("craps")  # the CrapsSim engine (pip install crapssim)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _engine_available(), reason="crapssim engine not installed in CI")
def test_cli_runs_and_exits_zero():
    # Minimal strategy spec
    spec = {
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [],
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        f.flush()
        tmpname = f.name

    try:
        # Run CLI: python -m crapssim_control run <json>
        result = subprocess.run(
            [sys.executable, "-m", "crapssim_control", "run", tmpname, "--shooters", "2"],
            capture_output=True,
            text=True,
        )

        # It should exit cleanly
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        # Should mention a bankroll summary in stdout
        assert "Bankroll" in result.stdout
    finally:
        os.remove(tmpname)
