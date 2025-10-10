import csv
import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path, meta_path: Path):
    return {
        "table": {},
        "variables": {"units": 10},
        # Use a place bet so an action is produced on point_established
        "modes": {"Main": {"template": {"place_6": 12}}},
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "T200",
                "seed": 42,
            },
            "memory": {
                "enabled": True,
                "meta_path": str(meta_path),
            },
        },
        "rules": [],
    }


def test_meta_json_written_when_enabled_and_path_provided(tmp_path):
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"

    spec = _spec(csv_path, meta_path)
    c = ControlStrategy(spec)

    # Drive a couple of events and record some memory
    assert c.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1
    c.memory["foo"] = "bar"

    # Finalize → should write both a summary row and a meta.json file
    c.finalize_run()

    # meta.json exists and contains identity/stats/memory
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload.get("identity", {}).get("run_id") == "T200"
    assert payload.get("identity", {}).get("seed") == 42
    assert payload.get("stats", {}).get("events_total") >= 2
    assert payload.get("memory", {}).get("foo") == "bar"