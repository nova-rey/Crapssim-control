# tests/test_controller_csv_integration.py

import csv
import os
import tempfile
from pathlib import Path

from crapssim_control.controller import ControlStrategy


def _read_csv_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames, rows


def test_controller_writes_csv_rows_per_event_when_enabled():
    # Temporary output file for the journal
    with tempfile.TemporaryDirectory() as td:
        out_csv = Path(td) / "actions.csv"

        # Minimal spec enabling CSV journaling
        spec = {
            "variables": {"units": 5},
            "table": {"level": 5},  # make amounts easy/valid after legalization
            "modes": {
                "Main": {
                    "template": {
                        "pass": "units",                     # pass line 5
                        "place": {"6": "units*2", "8": "units*2"},  # 10 each (legalizer may round)
                    }
                }
            },
            "rules": [],  # no rule actions for this test
            "run": {
                "demo_fallbacks": True,
                "csv": {
                    "enabled": True,
                    "path": str(out_csv),
                    "append": True,
                    "run_id": "t-ci",
                    "seed": 42,
                }
            },
        }

        ctrl = ControlStrategy(spec)

        # 1) Establish a point -> expect template diff actions (set pass_line, place_6, place_8)
        a_point = ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
        assert isinstance(a_point, list) and len(a_point) >= 2  # at least place_6/8; pass_line may be present too

        # 2) Two rolls (no regression yet)
        a_roll1 = ctrl.handle_event({"type": "roll"}, current_bets={})
        a_roll2 = ctrl.handle_event({"type": "roll"}, current_bets={})

        # 3) Third roll -> regression (clear place_6, clear place_8)
        a_roll3 = ctrl.handle_event({"type": "roll"}, current_bets={})
        # Ensure regression produced the clears we expect (envelope fields exist)
        assert any(a.get("action") == "clear" and a.get("bet_type") == "place_6" for a in a_roll3)
        assert any(a.get("action") == "clear" and a.get("bet_type") == "place_8" for a in a_roll3)

        # Collect expected total rows written (we only write when actions exist)
        expected_rows = len(a_point) + len(a_roll1) + len(a_roll2) + len(a_roll3)

        # CSV must exist now; read it back
        assert out_csv.exists(), "CSV journal file was not created"
        headers, rows = _read_csv_rows(out_csv)

        # Basic header check — must include a stable subset of fields
        # (csv_journal may include more like timestamp/run_id/seed/notes/extra)
        required_cols = {
            "event_type",
            "mode",
            "point",
            "rolls_since_point",
            "on_comeout",
            "source",
            "id",
            "action",
            "bet_type",
            "amount",
        }
        assert headers is not None and required_cols.issubset(set(headers)), f"Missing columns in CSV: {required_cols - set(headers)}"

        # Row count matches total emitted actions across events
        assert len(rows) == expected_rows

        # Spot-check first event row: should be from point_established and source=template
        first = rows[0]
        assert first.get("event_type") == "point_established"
        assert first.get("source") == "template"
        assert first.get("id", "").startswith("template:")
        assert first.get("action") in {"set", "clear"}  # typically "set" from template diff

        # Spot-check regression rows include notes/id as stamped in controller
        # (id should be "template:regress_roll3" for regression clears)
        any_regress = any(r.get("id") == "template:regress_roll3" and r.get("action") == "clear" for r in rows)
        assert any_regress, "Expected regression clear rows with id=template:regress_roll3"