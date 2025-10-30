import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from crapssim_control.cli_flags import CLIFlags
from crapssim_control.controller import ControlStrategy


def _dsl_spec(tmp_path: Path, enable_trace: bool = False) -> dict:
    report_path = tmp_path / "report.json"
    return {
        "meta": {"version": 0, "name": "ExplainSpec"},
        "table": {},
        "variables": {"units": 10, "mode": "Base"},
        "modes": {"Base": {"template": {}}},
        "rules": [],
        "behavior": {
            "schema_version": "1.0",
            "rules": [
                {
                    "id": "press_missing_bet",
                    "when": "bankroll >= 0",
                    "then": "press(bet=place_6, units=1)",
                }
            ],
        },
        "run": {
            "dsl": True,
            "dsl_once_per_window": True,
            "dsl_verbose_journal": False,
            "journal": {"dsl_trace": enable_trace},
            "report": {"path": str(report_path), "auto": False},
        },
    }


def test_run_explain_writes_decisions_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec = _dsl_spec(tmp_path, enable_trace=False)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    flags = CLIFlags()
    flags.explain = True
    flags.explain_source = "cli"

    controller = ControlStrategy(
        deepcopy(spec),
        spec_path=str(spec_path),
        cli_flags=flags,
        explain=True,
    )

    controller.handle_event({"type": "comeout"}, current_bets={})
    controller.finalize_run()
    controller.generate_report(
        report_path=str(tmp_path / "report.json"),
        spec_path=str(spec_path),
        cli_flags=flags,
    )

    decisions_path = Path("artifacts") / controller.run_id / "decisions.csv"
    assert decisions_path.exists(), "decisions.csv should be written when explain is enabled"

    with decisions_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "decisions.csv should contain at least one decision row"
    assert rows[0]["reason"].strip() != "", "decision rows should include a reason"

    manifest_path = Path("export/manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("run", {}).get("flags", {}).get("explain") is True
    assert manifest["run"]["flags"].get("human_summary") is False


def test_run_without_explain_has_no_decisions_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec = _dsl_spec(tmp_path, enable_trace=False)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    controller = ControlStrategy(deepcopy(spec), spec_path=str(spec_path))
    controller.handle_event({"type": "comeout"}, current_bets={})
    controller.finalize_run()
    controller.generate_report(
        report_path=str(tmp_path / "report.json"),
        spec_path=str(spec_path),
    )

    decisions_path = Path("artifacts") / controller.run_id / "decisions.csv"
    assert not decisions_path.exists(), "decisions.csv should not exist without explain"

    manifest_path = Path("export/manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("run", {}).get("flags", {}).get("explain") is False
