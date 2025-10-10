import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path, report_path: Path, run_id="T-P5C3", seed=777, auto=True):
    return {
        "table": {},
        "variables": {"units": 10},
        "modes": {
            # ensure a template diff at point_established
            "Main": {"template": {"place_6": 12}},
        },
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": run_id,
                "seed": seed,
            },
            # No meta.json on purpose (fallback path)
            "report": {
                "enabled": True,
                "path": str(report_path),
                "auto": bool(auto),
            },
        },
        "rules": [],
    }


def test_finalize_run_auto_report_without_meta_fallback(tmp_path):
    csv_path = tmp_path / "journal.csv"
    report_path = tmp_path / "report.json"

    c = ControlStrategy(_spec(csv_path, report_path, auto=True))

    # Drive a tiny run: comeout (no actions), then point_established (template diff → actions)
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1

    # Auto-report should be triggered by finalize_run when enabled
    c.finalize_run()

    # Report produced even without meta.json (fallback mode)
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))

    # Identity should still reflect CSV config
    ident = data.get("identity", {})
    assert ident.get("run_id") == "T-P5C3"
    assert ident.get("seed") == 777

    # Summary sanity
    summary = data.get("summary", {})
    assert summary.get("events_total") >= 2
    assert summary.get("actions_total") >= 1

    # Source references: csv present; meta may be absent
    src = data.get("source_files", {})
    assert src.get("csv") == str(csv_path)