# tests/test_p5c2_meta_json.py
import json
from pathlib import Path
import csv

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path, meta_path: Path | None, enabled: bool = True):
    run_block = {
        "csv": {
            "enabled": True,
            "path": str(csv_path),
            "append": False,
            "run_id": "T123",
            "seed": 999,
        },
        "memory": {
            "enabled": enabled,
        },
    }
    if meta_path is not None:
        run_block["memory"]["meta_path"] = str(meta_path)

    return {
        "table": {},
        "variables": {"units": 10},
        # Use a template that only applies on point, so we get at least one action.
        "modes": {"Main": {"template": {"place_6": 12}}},
        "run": run_block,
        "rules": [],
    }


def test_meta_json_written_when_enabled_and_path_provided(tmp_path):
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"

    spec