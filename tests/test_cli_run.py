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


def test_cli_run_engine_missing(monkeypatch):
    # Force CrapsSim import to fail inside the subprocess by masking the package
    # (Putting None in sys.modules causes import to raise ModuleNotFoundError)
    spec = _good_minimal_spec()
    path = _write_temp_spec(spec)

    # We can't monkeypatch the child process directly, so rely on the CLI's own
    # try/except around the crapsim import to surface a friendly message.
    # Just run it and assert the error output + non-zero code.
    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "run", path, "--rolls", "3"],
        capture_output=True,
        text=True,
    )
    # When crapsim isn't installed, CLI prints a stable error and returns 2
    assert res.returncode == 2
    assert "engine not available" in res.stderr.lower()
    assert "pip install crapssim" in res.stderr.lower()


@pytest.mark.skipif(pytest.importorskip("crapssim", reason="CrapsSim not installed") is None, reason="Skipped: CrapsSim not installed")
def test_cli_run_smoke_when_engine_present():
    spec = _good_minimal_spec()
    path = _write_temp_spec(spec)
    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "run", path, "--rolls", "5", "-v"],
        capture_output=True,
        text=True,
    )
    # Should succeed and print a RESULT line to stdout
    assert res.returncode == 0
    assert "result:" in res.stdout.lower()