# tests/test_p5c2_summary_extra_enrichment.py
import csv
import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path):
    return {
        "table": {},
        "variables": {"units": 10},
        # Use template that applies after point is set
        "modes": {"Main": {"template": {"place_6": 12}}},
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "T777",
                "seed": 42,
            },
            # memory block included but the meta JSON is a P5C2 optional; we don't require it here
            "memory": {"enabled": True},
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

    # Add a trivial memory entry to ensure it reflects in summary extra
    c.memory["from_test"] = True

    # Finalize → last row is summary
    c.finalize_run()

    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    assert len(rows) == len(acts) + 1

    last = rows[-1]
    assert last["event_type"] == "summary"
    assert last["id"] == "summary:run"
    assert last["action"] == "switch_mode"
    assert last["notes"] == "end_of_run"

    # Parse and validate enriched extra JSON
    extra_json = json.loads(last["extra"])
    assert extra_json.get("summary") is True
    assert isinstance(extra_json.get("stats"), dict)
    assert isinstance(extra_json.get("memory"), dict)

    # NEW in P5C2: run identity baked into extra
    assert extra_json.get("run_id") == "T777"
    assert str(extra_json.get("seed")) == "42"