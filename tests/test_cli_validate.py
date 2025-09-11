# tests/test_cli_validate.py
import subprocess
import sys
import tempfile
import json
import os

def _write_temp_spec(obj) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(obj, f)
    f.flush()
    name = f.name
    f.close()
    return name

def test_cli_validate_ok():
    spec = {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]}
        ]
    }
    path = _write_temp_spec(spec)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "crapssim_control", "validate", path],
            capture_output=True, text=True
        )
        assert res.returncode == 0, res.stderr
        assert "OK:" in res.stdout
    finally:
        os.remove(path)

def test_cli_validate_errors():
    # invalid: missing 'modes'
    spec = {
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10},
        "rules": []
    }
    path = _write_temp_spec(spec)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "crapssim_control", "validate", path],
            capture_output=True, text=True
        )
        assert res.returncode != 0
        assert "failed validation" in res.stderr.lower()
        # should list at least one error
        assert "modes section is required" in res.stderr
    finally:
        os.remove(path)