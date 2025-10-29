# tests/test_csv_summary.py

import csv
import tempfile
from pathlib import Path

from crapssim_control.csv_summary import summarize_journal, write_summary_csv
from tests import skip_csv_preamble


def _write_journal(path: Path, rows):
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
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_summarize_journal_group_by_run_id_and_metrics():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "journal.csv"

        # Build a tiny but representative journal (one row per action)
        rows = [
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
            # Two rolls — no regression yet
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
            # Third roll — regression clears
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
        _write_journal(jpath, rows)

        summaries = summarize_journal(journal_path=jpath, group_by_run_id=True)
        assert isinstance(summaries, list) and len(summaries) == 1

        s = summaries[0]
        # Core grouping & counts
        assert s["run_id"] == "run-001"
        assert s["rows_total"] == len(rows)
        assert s["actions_total"] == len(rows)

        # Action type counts
        assert s["sets"] == 3
        assert s["presses"] == 1
        assert s["reduces"] == 1
        assert s["clears"] == 2
        assert s["switch_mode"] == 0

        # Distincts and event counts
        assert s["unique_bets"] >= 3  # pass_line, place_6, place_8
        assert s["modes_used"] == 1
        assert s["points_seen"] == 1  # only point 6 present
        assert s["roll_events"] == 3  # 3 roll rows

        # Regression marker was picked up
        assert s["regress_events"] == 2

        # Amount sums (numeric only)
        assert s["sum_amount_set"] == 25.0  # 5 + 10 + 10
        assert s["sum_amount_press"] == 6.0
        assert s["sum_amount_reduce"] == 2.0

        # Timestamps
        assert s["first_timestamp"] == "2025-10-09T10:00:00"
        assert s["last_timestamp"] == "2025-10-09T10:00:15"

        # Path populated
        assert s["path"].endswith("journal.csv")

        # Now write the summary to a CSV and validate basic shape
        out_summary = Path(td) / "summary.csv"
        write_summary_csv(summaries, out_summary, append=False)
        assert out_summary.exists()

        with out_summary.open("r", encoding="utf-8", newline="") as f:
            skip_csv_preamble(f)
            reader = csv.DictReader(f)
            out_rows = list(reader)
            assert len(out_rows) == 1
            out = out_rows[0]
            # Spot-check a couple of fields survived the write
            assert out.get("run_id") == "run-001"
            assert int(out.get("rows_total", "0")) == len(rows)
            assert out.get("first_timestamp") == "2025-10-09T10:00:00"
            assert out.get("last_timestamp") == "2025-10-09T10:00:15"


def test_summarize_without_run_id_groups_by_file_when_flag_false():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "journal_no_run_id.csv"
        rows = [
            {
                "timestamp": "2025-10-09T10:00:00",
                "run_id": "",  # intentionally blank
                "event_type": "roll",
                "mode": "Main",
                "point": "0",
                "rolls_since_point": "0",
                "on_comeout": "True",
                "source": "template",
                "id": "template:Main",
                "action": "set",
                "bet_type": "pass_line",
                "amount": "5",
            }
        ]
        _write_journal(jpath, rows)

        # Group by file (explicit) -> expect one summary row keyed by file:*
        summaries = summarize_journal(journal_path=jpath, group_by_run_id=False)
        assert len(summaries) == 1
        assert summaries[0]["run_id"].startswith("file:")
        assert summaries[0]["rows_total"] == 1
