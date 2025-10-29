# tests/test_cli_journal.py
from __future__ import annotations

import csv
from pathlib import Path
import tempfile

from crapssim_control.cli import main as cli_main
from tests import skip_csv_preamble


def _write_journal(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure consistent field order for readability; DictWriter will add any extras
    fieldnames = [
        "timestamp",
        "run_id",
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
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _fixture_rows():
    # Mirrors the scenario used in csv_summary tests:
    # - 3 template 'set' rows on point_established
    # - 2 rule rows on roll (press, reduce)
    # - 2 template clears on 3rd roll (same timestamp → count as 1 roll tick)
    return [
        # Point established — template diffs
        {
            "timestamp": "2025-10-09T10:00:00",
            "run_id": "run-001",
            "event_type": "point_established",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "0",
            "on_comeout": "False",
            "source": "template",
            "id": "template:Main",
            "action": "set",
            "bet_type": "pass_line",
            "amount": "5",
        },
        {
            "timestamp": "2025-10-09T10:00:00",
            "run_id": "run-001",
            "event_type": "point_established",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "0",
            "on_comeout": "False",
            "source": "template",
            "id": "template:Main",
            "action": "set",
            "bet_type": "place_6",
            "amount": "10",
        },
        {
            "timestamp": "2025-10-09T10:00:00",
            "run_id": "run-001",
            "event_type": "point_established",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "0",
            "on_comeout": "False",
            "source": "template",
            "id": "template:Main",
            "action": "set",
            "bet_type": "place_8",
            "amount": "10",
        },
        # Two rolls — no regression yet (rule actions)
        {
            "timestamp": "2025-10-09T10:00:05",
            "run_id": "run-001",
            "event_type": "roll",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "1",
            "on_comeout": "False",
            "source": "rule",
            "id": "rule:auto_press_6",
            "action": "press",
            "bet_type": "place_6",
            "amount": "6",
        },
        {
            "timestamp": "2025-10-09T10:00:10",
            "run_id": "run-001",
            "event_type": "roll",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "2",
            "on_comeout": "False",
            "source": "rule",
            "id": "rule:auto_reduce_8",
            "action": "reduce",
            "bet_type": "place_8",
            "amount": "2",
        },
        # Third roll — regression clears (same timestamp for both)
        {
            "timestamp": "2025-10-09T10:00:15",
            "run_id": "run-001",
            "event_type": "roll",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "3",
            "on_comeout": "False",
            "source": "template",
            "id": "template:regress_roll3",
            "action": "clear",
            "bet_type": "place_6",
            "amount": "",
        },
        {
            "timestamp": "2025-10-09T10:00:15",
            "run_id": "run-001",
            "event_type": "roll",
            "mode": "Main",
            "point": "6",
            "rolls_since_point": "3",
            "on_comeout": "False",
            "source": "template",
            "id": "template:regress_roll3",
            "action": "clear",
            "bet_type": "place_8",
            "amount": "",
        },
    ]


def test_cli_journal_summarize_prints_table(capsys):
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "journal.csv"
        _write_journal(jpath, _fixture_rows())

        # Invoke the CLI: print to stdout (TSV-like)
        rc = cli_main(["journal", "summarize", str(jpath)])
        assert rc == 0

        out = capsys.readouterr().out.strip()
        # Expect header + one data line
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) >= 2

        header = lines[0].split("\t")
        data = lines[1].split("\t")

        # Minimal sanity checks on columns present
        assert "run_id_or_file" in header[0]
        assert "rows_total" in header
        assert "sets" in header
        assert "clears" in header
        assert "presses" in header
        assert "reduces" in header
        assert "roll_events" in header

        # Validate a few expected numbers from our fixture
        # rows/actions = 7 (we wrote 7 rows)
        assert "7" in data
        # We know from fixture: sets=3, clears=2, presses=1, reduces=1, roll_events=3
        # Loosely assert by scanning the data row to avoid depending on exact order
        for expect in ("sets", "presses", "reduces", "clears"):
            assert expect in header
        assert any(cell == "3" for cell in data)  # sets
        assert any(cell == "2" for cell in data)  # clears
        assert any(cell == "1" for cell in data)  # presses/reduces counts appear as 1
        # roll_events=3 should be present
        assert "3" in data


def test_cli_journal_summarize_writes_summary_csv(tmp_path: Path):
    jpath = tmp_path / "journal.csv"
    out_summary = tmp_path / "summary.csv"
    _write_journal(jpath, _fixture_rows())

    # Write summary CSV via CLI
    rc = cli_main(["journal", "summarize", str(jpath), "--out", str(out_summary)])
    assert rc == 0
    assert out_summary.exists()

    # Read back and validate a few fields
    with out_summary.open("r", encoding="utf-8", newline="") as f:
        skip_csv_preamble(f)
        r = list(csv.DictReader(f))
    assert len(r) == 1
    row = r[0]

    # Basic counts from fixture
    assert row.get("rows_total") == "7"
    assert row.get("actions_total") == "7"
    assert row.get("sets") == "3"
    assert row.get("clears") == "2"
    assert row.get("presses") == "1"
    assert row.get("reduces") == "1"

    # roll_events = 3 distinct timestamps across roll rows
    assert row.get("roll_events") == "3"

    # Presence of timestamps and path
    assert row.get("first_timestamp")
    assert row.get("last_timestamp")
    assert row.get("path")
