# tests/test_csv_roundtrip_example.py
from __future__ import annotations
import csv
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

from crapssim_control.csv_journal import CSVJournal
from crapssim_control.csv_summary import summarize_journal, write_summary_csv
from tests import skip_csv_preamble


def _read_csv_rows(path: Path):
    with path.open(encoding="utf-8") as f:
        skip_csv_preamble(f)
        return list(csv.DictReader(f))


def test_journal_to_summary_and_cli_roundtrip(tmp_path: Path):
    """
    Integration-style test:
    1. Write a small journal using CSVJournal.
    2. Summarize via summarize_journal() + write_summary_csv().
    3. Run CLI journal summarize to validate identical header.
    """
    # --- Step 1: create journal ---
    journal_path = tmp_path / "journal.csv"
    j = CSVJournal(journal_path, run_id="quickstart", seed=1234)

    snapshot = {
        "event_type": "point_established",
        "point": 6,
        "rolls_since_point": 0,
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
            "bet_type": "pass_line",
            "amount": 5,
            "notes": "base bet",
        },
        {
            "source": "template",
            "id": "template:Main",
            "action": "set",
            "bet_type": "place_6",
            "amount": 10,
            "notes": "place bet",
        },
    ]

    n = j.write_actions(actions, snapshot=snapshot)
    assert n == 2
    rows = _read_csv_rows(journal_path)
    assert len(rows) == 2
    assert rows[0]["run_id"] == "quickstart"
    assert rows[0]["seed"] == "1234"
    assert rows[0]["action"] == "set"

    # --- Step 2: summarize programmatically ---
    summaries = summarize_journal(journal_path)
    assert len(summaries) == 1
    s0 = summaries[0]
    assert s0["run_id"] == "quickstart"
    assert s0["sets"] == 2
    assert s0["clears"] == 0
    assert s0["rows_total"] == 2
    assert "path" in s0

    # Write a summary.csv to verify I/O
    summary_path = tmp_path / "summary.csv"
    write_summary_csv(summaries, summary_path)
    out_rows = _read_csv_rows(summary_path)
    assert len(out_rows) == 1
    assert out_rows[0]["run_id"] == "quickstart"

    # --- Step 3: CLI journal summarize ---
    cmd = [
        sys.executable,
        "-m",
        "crapssim_control.cli",
        "journal",
        "summarize",
        str(journal_path),
        "--out",
        str(tmp_path / "summary_cli.csv"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("STDOUT:", proc.stdout)
        print("STDERR:", proc.stderr)
    assert proc.returncode == 0
    assert "quickstart" in proc.stdout
    assert "rows_total" in proc.stdout