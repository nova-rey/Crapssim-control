import csv
import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path, meta_path: Path | None = None, report_path: Path | None = None, auto_report: bool = False):
    spec = {
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
                "run_id": "T-P5C3",
                "seed": 777,
            },
            # P5C2 meta.json writer (already shipped in prior checkpoint)
            "meta": {
                "enabled": meta_path is not None,
                **({"path": str(meta_path)} if meta_path else {}),
            },
            # P5C3 report config
            "report": {
                "enabled": report_path is not None,
                **({"path": str(report_path)} if report_path else {}),
                "auto": bool(auto_report),
            },
        },
        "rules": [],
    }
    return spec


def test_generate_report_manual_with_meta_and_csv(tmp_path):
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"
    report_path = tmp_path / "report.json"

    c = ControlStrategy(_spec(csv_path, meta_path=meta_path, report_path=report_path, auto_report=False))

    # Drive: comeout (no actions), then point_established (template diff → actions)
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1

    # finalize to ensure meta/summary are flushed
    c.finalize_run()

    # Manual generation API: controller.generate_report()
    assert hasattr(c, "generate_report"), "Controller must expose generate_report(...) for P5C3"
    result = c.generate_report()  # report path taken from spec.run.report.path
    assert isinstance(result, dict)

    # File exists and is valid JSON
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))

    # Minimal integrity checks: identity merged from meta/csv config
    ident = data.get("identity", {})
    assert ident.get("run_id") == "T-P5C3"
    assert ident.get("seed") == 777

    # Summary reflects in-RAM stats / CSV aggregation
    summary = data.get("summary", {})
    assert summary.get("events_total") >= 2
    assert summary.get("actions_total") >= 1

    # Memory (if any) and source references present
    assert "memory" in data
    src = data.get("source_files", {})
    assert src.get("csv") == str(csv_path)
    assert src.get("meta") == str(meta_path)


def test_finalize_run_auto_report_without_meta_fallback(tmp_path):
    csv_path = tmp_path / "journal.csv"
    report_path = tmp_path / "report.json"

    c = ControlStrategy(_spec(csv_path, meta_path=None, report_path=report_path, auto_report=True))

    # Drive a tiny run
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1

    # Auto-report should be triggered by finalize_run when enabled
    c.finalize_run()

    # Report produced even without meta.json (fallback path)
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))

    # Identity should still have run_id/seed (from CSV config) in fallback mode
    ident = data.get("identity", {})
    assert ident.get("run_id") == "T-P5C3"
    assert ident.get("seed") == 777

    # Summary sanity
    summary = data.get("summary", {})
    assert summary.get("events_total") >= 2
    assert summary.get("actions_total") >= 1

    # Source references: meta may be absent, csv must be present
    src = data.get("source_files", {})
    assert src.get("csv") == str(csv_path)
    # meta not required here