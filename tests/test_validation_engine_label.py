import json
import sys
import types
from pathlib import Path

import pytest

from crapssim_control.controller import ControlStrategy
from crapssim_control.cli import run as cli_run
from crapssim_control.spec_validation import VALIDATION_ENGINE_VERSION


def _minimal_spec() -> dict:
    return {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]},
        ],
    }


def _write_spec_file(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_validation_engine_constant():
    assert VALIDATION_ENGINE_VERSION == "v1"


def test_report_includes_validation_engine(tmp_path):
    spec = _minimal_spec()
    controller = ControlStrategy(spec)
    report = controller.generate_report(tmp_path / "report.json")
    metadata = report.get("metadata", {})
    assert metadata.get("validation_engine") == VALIDATION_ENGINE_VERSION


@pytest.fixture()
def stub_engine_adapter(monkeypatch):
    module = types.ModuleType("crapssim_control.engine_adapter")

    class _StubTable:
        def __init__(self):
            self.players = []

        def play(self, rolls: int) -> None:  # pragma: no cover - trivial
            self._rolls = rolls

    class _StubAttachResult:
        def __init__(self):
            self.table = _StubTable()
            self.meta = {}

    class EngineAdapter:  # pragma: no cover - simple stub
        def attach(self, spec):
            return _StubAttachResult()

    module.EngineAdapter = EngineAdapter
    monkeypatch.setitem(sys.modules, "crapssim_control.engine_adapter", module)
    return module


def test_cli_run_prints_validation_engine(tmp_path, capsys, stub_engine_adapter):
    spec_path = _write_spec_file(tmp_path, _minimal_spec())
    args = types.SimpleNamespace(
        spec=str(spec_path),
        rolls=5,
        seed=None,
        export=None,
        demo_fallbacks=False,
        strict=False,
        no_embed_analytics=False,
        rng_audit=False,
    )

    exit_code = cli_run(args)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"validation_engine: {VALIDATION_ENGINE_VERSION}" in captured.out
