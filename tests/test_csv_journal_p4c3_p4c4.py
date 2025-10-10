# tests/test_csv_journal_p4c3_p4c4.py
from __future__ import annotations

import csv
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED

def test_csv_journal_seq_and_extra(tmp_path):
    csv_path = tmp_path / "journal.csv"

    spec = {
        "table": {},
        "variables": {"units": 10},
        "modes": {
            "Main": {"template": {"pass_line": 10}},
            "Aggressive": {"template": {"pass_line": 10, "place_6": 12}},
        },
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "T100",
                "seed": 42,
            }
        },
        "rules": [
            {
                "name": "switch_now_and_tweak",
                "on": {"event": "point_established"},
                "when": "point == 6",
                "do": ["switch_mode Aggressive", "set place_6 18"],
            }
        ],
    }

    c = ControlStrategy(spec)

    # comeout: no actions → still ensure header created lazily on first write
    c.handle_event({"type": COMEOUT}, current_bets={})

    # point established → should produce: switch, template(Main→Aggressive), then rule set
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert acts  # should have some actions

    # Read the CSV back
    assert csv_path.exists()
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    assert len(rows) == len(acts)

    # Check a couple of fields on the first row
    r0 = rows[0]
    # core columns present
    for col in ["ts","run_id","seed","event_type","mode","source","id","action","bet_type","amount","notes","extra"]:
        assert col in r0

    # event type recorded
    assert r0["event_type"] == "point_established"
    # immediate switch means the mode column should reflect "Aggressive" in this same event
    assert r0["mode"] == "Aggressive"

    # 'extra' should contain JSON with at least a "seq" and "event_point" key for rows
    # We won't parse fully, just spot-check substrings to avoid strict formatting coupling
    assert '"seq":' in r0["extra"] or "'seq':" in r0["extra"]
    assert '"event_point": 6' in r0["extra"] or "'event_point': 6" in r0["extra"]