import json
import sys
import subprocess
import tempfile
from pathlib import Path
import pytest


def _write_temp_spec(spec: dict) -> str:
    fd = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    Path(fd.name).write_text(json.dumps(spec), encoding="utf-8")
    return fd.name


def _good_minimal_spec():
    # Matches shape used in validate tests; enough for CLI run to parse & validate
    return {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]}
        ],
    }


def test_cli_run_engine_missing():
    # When crapsim isn't available, CLI should print a friendly error and exit 2.
    spec = _good_minimal_spec()
    path = _write_temp_spec(spec)

    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "run", path, "--rolls", "3"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert "engine not available" in res.stderr.lower()
    assert "pip install crapssim" in res.stderr.lower()


@pytest.mark.skipif(pytest.importorskip("crapssim", reason="CrapsSim not installed") is None, reason="Skipped: CrapsSim not installed")
def test_cli_run_smoke_when_engine_present():
    spec = _good_minimal_spec()
    path = _write_temp_spec(spec)
    # IMPORTANT: global flags like -v must come before the subcommand
    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "-v", "run", path, "--rolls", "5"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "result:" in res.stdout.lower()