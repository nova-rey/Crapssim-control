import csv
import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path):
    return {
        "table": {},
        "variables": {"units": 10},
        # Ensure an action occurs on point_established
        "modes": {"Main": {"template": {"place_6": 12}}},
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "T123",
                "seed": 7,
            }
        },
        "rules": [],
    }


def test_summary_row_extra_includes_run_identity(tmp_path):
    csv_path = tmp_path / "journal.csv"
    spec = _spec(csv_path)
    c = ControlStrategy(spec)

    # COMEOUT → no actions
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []

    # POINT_ESTABLISHED → template diff produces at least one action
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1

    # Add something to memory so it’s visible in summary extra as well
    c.memory["tag"] = "ok"

    # Finalize → summary row appended
    c.finalize_run()

    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    assert len(rows) == len(acts) + 1

    summary = rows[-1]
    assert summary["event_type"] == "summary"
    assert summary["id"] == "summary:run"
    assert summary["action"] == "switch_mode"
    assert summary["notes"] == "end_of_run"

    # Extra json should include identity with run_id/seed (plus stats/memory)
    extra = json.loads(summary["extra"])
    ident = extra.get("identity", {})
    assert ident.get("run_id") == "T123"
    assert ident.get("seed") == 7
    assert extra.get("stats", {}).get("events_total") >= 2
    assert extra.get("memory", {}).get("tag") == "ok"