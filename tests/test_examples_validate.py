# tests/test_examples_validate.py
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import pytest


EXAMPLE_SPEC = Path(__file__).parent.parent / "examples" / "quickstart_spec.json"


@pytest.mark.parametrize("cli_flag", [[], ["--guardrails"]])
def test_quickstart_spec_validates(cli_flag):
    """Ensure the quickstart example spec validates cleanly via CLI."""
    assert EXAMPLE_SPEC.exists(), f"Missing example spec: {EXAMPLE_SPEC}"

    # Run CLI validate as subprocess to simulate real user workflow
    cmd = [sys.executable, "-m", "crapssim_control.cli", "validate", str(EXAMPLE_SPEC)] + cli_flag
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Debug trace if it fails
    if proc.returncode != 0:
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)

    # It should print "OK:" and exit 0
    assert proc.returncode == 0, f"Validation failed: {proc.stderr}"
    assert "OK:" in proc.stdout
    assert "quickstart_spec.json" in proc.stdout