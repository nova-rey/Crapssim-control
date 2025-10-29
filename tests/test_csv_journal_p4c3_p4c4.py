# tests/test_csv_journal_p4c3_p4c4.py
from __future__ import annotations

import csv
import json
from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED
from tests import skip_csv_preamble


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

    # comeout: no actions → header will be created on first write later
    c.handle_event({"type": COMEOUT}, current_bets={})

    # point established → should produce: switch, template(Main→Aggressive), then rule set
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert acts  # should have some actions

    # Read the CSV back
    assert csv_path.exists()
    with open(csv_path, newline="", encoding="utf-8") as f:
        skip_csv_preamble(f)
        rows = list(csv.DictReader(f))

    assert len(rows) == len(acts)

    # Check a couple of fields on the first row
    r0 = rows[0]
    # core columns present
    for col in [
        "ts",
        "run_id",
        "seed",
        "event_type",
        "mode",
        "source",
        "id",
        "action",
        "bet_type",
        "amount",
        "notes",
        "extra",
    ]:
        assert col in r0

    # event type recorded
    assert r0["event_type"] == "point_established"
    # immediate switch means the mode column should reflect "Aggressive" in this same event
    assert r0["mode"] == "Aggressive"

    # 'extra' should be JSON with at least a "seq" and "event_point" key for rows
    extra_raw = r0.get("extra", "")
    try:
        extra = json.loads(extra_raw) if extra_raw else {}
    except Exception:
        # fall back to substring checks if non-JSON content ever appears
        assert '"seq":' in extra_raw or "'seq':" in extra_raw
        assert '"event_point":' in extra_raw or "'event_point':" in extra_raw
    else:
        # JSON path: check explicit keys
        assert isinstance(extra, dict)
        assert "seq" in extra
        assert extra.get("event_point") == 6
