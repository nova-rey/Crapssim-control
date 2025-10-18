# tests/test_csv_writer.py
import csv
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from crapssim_control.csv_journal import CSVJournal
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION
from tests import skip_csv_preamble


def _read_all(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        skip_csv_preamble(f)
        reader = csv.DictReader(f)
        return list(reader)


def test_header_written_and_rows_appended_once():
    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "journal.csv")
        j = CSVJournal(out, append=True, run_id="run-123", seed=42)

        # First write
        snap = {
            "event_type": "roll",
            "point": 6,
            "rolls_since_point": 2,
            "on_comeout": False,
            "mode": "Main",
            "units": 5,
            "bankroll": 1000,
        }
        actions = [
            {
                "source": "template",
                "id": "template:Main",
                "action": "set",
                "bet_type": "place_6",
                "amount": 12,
                "notes": "from template",
            },
            {
                "source": "rule",
                "id": "rule:press_after_hit",
                "action": "press",
                "bet_type": "place_8",
                "amount": 6,
                "notes": "",
            },
        ]

        n1 = j.write_actions(actions, snapshot=snap)
        assert n1 == 2
        assert os.path.exists(out)

        rows1 = _read_all(out)
        # header should exist; two rows written
        assert len(rows1) == 2

        # Validate a few key fields on first row
        r0 = rows1[0]
        assert r0["run_id"] == "run-123"
        assert r0["seed"] == "42"
        assert r0["event_type"] == "roll"
        assert r0["point"] == "6"
        assert r0["rolls_since_point"] == "2"
        assert r0["on_comeout"] in ("False", "false")  # csv writes bool via str()
        assert r0["mode"] == "Main"
        assert r0["units"] == "5.0"
        assert r0["bankroll"] == "1000.0"
        assert r0["source"] == "template"
        assert r0["id"] == "template:Main"
        assert r0["action"] == "set"
        assert r0["bet_type"] == "place_6"
        assert r0["amount"] == "12.0"
        assert r0["notes"] == "from template"

        # Second write (append): no duplicate header, total rows = 4
        actions2 = [
            {
                "source": "template",
                "id": "template:Main",
                "action": "clear",
                "bet_type": "place_6",
                "amount": None,
                "notes": "regress",
            },
            {
                "source": "rule",
                "id": "rule:#1",
                "action": "switch_mode",
                "bet_type": None,
                "amount": None,
                "notes": "Recovery",
            },
        ]
        n2 = j.write_actions(actions2, snapshot={"event_type": "roll"})
        assert n2 == 2

        rows2 = _read_all(out)
        assert len(rows2) == 4
        # Ensure header wasn't duplicated by checking first line of file explicitly
        with open(out, encoding="utf-8") as f:
            first_line = f.readline().strip()
            second_line = f.readline().strip()
        assert first_line == f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}"
        # Columns are stable and should include these keys in order
        assert second_line.startswith("ts,run_id,seed,event_type,point,rolls_since_point,on_comeout,mode,units,bankroll,source,id,action,bet_type,amount,notes,extra")


def test_blank_amount_when_none_and_missing_snapshot_is_ok():
    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "journal.csv")
        j = CSVJournal(out)

        actions = [
            {
                "source": "template",
                "id": "template:Main",
                "action": "clear",
                "bet_type": "field",
                "amount": None,
                "notes": "",
            }
        ]

        n = j.write_actions(actions, snapshot={})  # minimal snapshot
        assert n == 1

        rows = _read_all(out)
        assert len(rows) == 1
        r = rows[0]

        # Amount should be blank string when None
        assert r["amount"] == ""
        # Missing snapshot values should serialize to blanks
        assert r["point"] == ""
        assert r["rolls_since_point"] == ""
        assert r["on_comeout"] in ("", "False", "false")  # permissive
        assert r["mode"] == ""


def test_no_actions_still_ensures_header():
    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "journal.csv")
        j = CSVJournal(out)

        # No actions → should still create file with header
        n = j.write_actions([], snapshot={"event_type": "comeout"})
        assert n == 0
        assert os.path.exists(out)

        # File has header but no rows
        rows = _read_all(out)
        assert rows == []


def test_extra_field_serialization_and_json_like_values():
    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "journal.csv")
        j = CSVJournal(out)

        snap = {
            "event_type": "roll",
            "extra": {"dice": [3, 3], "shooter": "A"},
        }
        actions = [
            {
                "source": "rule",
                "id": "rule:mode_switch",
                "action": "switch_mode",
                "bet_type": None,
                "amount": None,
                "notes": "Recovery",
            }
        ]

        j.write_actions(actions, snapshot=snap)
        rows = _read_all(out)
        assert len(rows) == 1
        r = rows[0]
        # extra should be a JSON string
        assert r["extra"] == '{"dice":[3,3],"shooter":"A"}'
        assert r["notes"] == "Recovery"