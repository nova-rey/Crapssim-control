import csv
import json
from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED

def _spec(csv_path):
    return {
        "table": {},
        "variables": {"units": 10},
        "modes": {
            "Main": {"template": {"pass_line": 10}},
        },
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "RUN-P5C1",
                "seed": 123,
            }
        },
        "rules": [],  # keep simple; no switches/rules needed for this test
    }

def test_finalize_run_emits_summary_row_and_stats(tmp_path):
    csv_path = tmp_path / "journal.csv"
    spec = _spec(csv_path)
    c = ControlStrategy(spec)

    # 1) COMEOUT (no actions expected, but counts as an event)
    acts0 = c.handle_event({"type": COMEOUT}, current_bets={})
    assert acts0 == []

    # 2) POINT_ESTABLISHED (template should set pass_line once)
    acts1 = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts1) >= 1
    assert any(a["action"] == "set" and a.get("bet_type") == "pass_line" for a in acts1)

    # Set some in-RAM memory before finalizing to ensure it's surfaced in summary
    c.memory["foo"] = "bar"

    # 3) Finalize the run → should append a single summary row
    c.finalize_run()

    # Read CSV back
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    # Total rows = rows from actions (acts1 only) + 1 summary row
    assert len(rows) == len(acts1) + 1

    # Summary is the last row
    summary = rows[-1]
    assert summary["event_type"] == "summary"
    assert summary["id"] == "summary:run"
    assert summary["action"] == "switch_mode"  # benign envelope used for summary row
    assert summary["notes"] == "end_of_run"

    # 'extra' should be JSON containing {summary: true, stats: {...}, memory: {...}}
    extra = summary.get("extra", "")
    assert extra  # non-empty
    data = json.loads(extra)
    assert data.get("summary") is True
    # Stats: 2 events handled; actions_total equals len(acts1)
    stats = data.get("stats") or {}
    assert stats.get("events_total") == 2
    assert stats.get("actions_total") == len(acts1)
    by_ev = stats.get("by_event_type") or {}
    assert by_ev.get("comeout", 0) == 1
    assert by_ev.get("point_established", 0) == 1

    # Memory snapshot present
    mem = data.get("memory") or {}
    assert mem.get("foo") == "bar"


def test_finalize_run_no_csv_enabled_is_noop(tmp_path):
    # Same spec but CSV disabled
    spec = {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass_line": 10}}},
        "run": {"csv": {"enabled": False}},
        "rules": [],
    }
    c = ControlStrategy(spec)
    c.handle_event({"type": COMEOUT}, current_bets={})
    c.handle_event({"type": POINT_ESTABLISHED, "point": 5}, current_bets={})

    # Should not raise and should not create any file
    c.finalize_run()
    # No CSV path to check; just ensure no exceptions and controller stats look sane
    snap = c.state_snapshot()
    st = snap.get("stats") or {}
    assert st.get("events_total") == 2
    assert st.get("actions_total") >= 1  # at least the template "set" on point