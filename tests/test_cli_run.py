import json
import sys
import subprocess
import tempfile
from pathlib import Path
import importlib
import inspect
import pytest


def _write_temp_spec(spec: dict) -> str:
    fd = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    Path(fd.name).write_text(json.dumps(spec), encoding="utf-8")
    return fd.name


def _good_minimal_spec():
    # Minimal, valid shape for both validate and run
    return {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]}
        ],
    }


def _engine_available() -> bool:
    """Return True when the core CrapsSim primitives and adapter are importable."""

    def _has_attr(mod_name: str, attr: str) -> bool:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            return False
        return hasattr(mod, attr)

    try:
        tbl = importlib.import_module("crapssim.table")
    except Exception:
        return False

    try:
        from crapssim_control.engine_adapter import EngineAdapter  # noqa: WPS433
    except Exception:
        return False

    if inspect.isabstract(EngineAdapter):
        return False

    has_player = hasattr(tbl, "Player") or _has_attr("crapssim.player", "Player")
    has_dice = hasattr(tbl, "Dice") or _has_attr("crapssim.dice", "Dice")

    return hasattr(tbl, "Table") and has_player and has_dice


def test_cli_run_engine_missing():
    # When crapsim isn't available (or is incomplete), CLI should print a friendly
    # error and exit 2.
    if _engine_available():
        pytest.skip("Engine present; this case is covered by the smoke test below.")

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


@pytest.mark.skipif(not _engine_available(), reason="CrapsSim (table/player/dice) not fully available")
def test_cli_run_smoke_when_engine_present():
    spec = _good_minimal_spec()
    path = _write_temp_spec(spec)
    # Global flags must precede the subcommand
    res = subprocess.run(
        [sys.executable, "-m", "crapssim_control", "-v", "run", path, "--rolls", "5"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "result:" in res.stdout.lower()