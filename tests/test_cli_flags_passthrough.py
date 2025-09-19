from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

def _write_temp_spec(spec) -> str:
    fd = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
    Path(fd.name).write_text(json.dumps(spec), encoding="utf-8")
    return fd.name

def _good_spec():
    return {
        "meta": {"version": 0, "name": "FlagsSmoke"},
        "table": {"bubble": False, "level": 10},
        "variables": {"mode": "Main"},
        "modes": {"Main": {"template": {"pass": 10}}},
        "rules": [{"on": {"event": "comeout"}, "do": ["apply_template('Main')"]}],
    }

def test_cli_validate_accepts_flags_and_stays_ok():
    spec = _good_spec()
    p = _write_temp_spec(spec)
    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "validate", p, "--hot-table", "--guardrails"],
        capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "OK:" in res.stdout