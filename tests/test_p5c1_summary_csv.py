import csv
import json
from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED
from tests import skip_csv_preamble


def _spec(csv_path):
    return {
        "table": {},
        "variables": {"units": 10},
        "modes": {
            # The template content is irrelevant to these tests now.
            "Main": {"template": {}},
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
        # Guarantee at least one action at point_established via a simple rule.
        "rules": [
            {
                "name": "kick_action_for_stats",
                "on": {"event": "point_established"},
                "do": ["set place_6 12"],
            }
        ],
    }


def test_finalize_run_emits_summary_row_and_stats(tmp_path):
    csv_path = tmp_path / "journal.csv"
    spec = _spec(csv_path)
    c = ControlStrategy(spec)

    # 1) COMEOUT (no actions expected)
    acts0 = c.handle_event({"type": COMEOUT}, current_bets={})
    assert acts0 == []

    # 2) POINT_ESTABLISHED → rule should create a 'set place_6'
    acts1 = c.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts1) >= 1
    assert any(a["action"] == "set" and a.get("bet_type") == "place_6" for a in acts1)

    # Put something in RAM memory to verify it appears in the summary
    c.memory["foo"] = "bar"

    # 3) Finalize → summary row appended
    c.finalize_run()

    with open(csv_path, newline="", encoding="utf-8") as fh:
        skip_csv_preamble(fh)
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(acts1) + 1

    summary = rows[-1]
    assert summary["event_type"] == "summary"
    assert summary["id"] == "summary:run"
    # benign envelope for summary row (contract choice from controller.finalize_run)
    assert summary["action"] == "switch_mode"
    assert summary["notes"] == "end_of_run"

    extra = summary.get("extra", "")
    assert extra
    data = json.loads(extra)
    assert data.get("summary") is True

    stats = data.get("stats") or {}
    assert stats.get("events_total") == 2
    assert stats.get("actions_total") == len(acts1)
    by_ev = stats.get("by_event_type") or {}
    assert by_ev.get("comeout", 0) == 1
    assert by_ev.get("point_established", 0) == 1

    mem = data.get("memory") or {}
    assert mem.get("foo") == "bar"


def test_finalize_run_no_csv_enabled_is_noop(tmp_path):
    spec = {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {}}},
        "run": {"csv": {"enabled": False}},
        # Same simple rule to guarantee an action on point_established.
        "rules": [
            {
                "name": "kick_action_for_stats",
                "on": {"event": "point_established"},
                "do": ["set place_6 12"],
            }
        ],
    }
    c = ControlStrategy(spec)
    c.handle_event({"type": COMEOUT}, current_bets={})
    acts = c.handle_event({"type": POINT_ESTABLISHED, "point": 5}, current_bets={})
    assert any(a["action"] == "set" and a.get("bet_type") == "place_6" for a in acts)

    c.finalize_run()  # should be a no-op for CSV
    snap = c.state_snapshot()
    st = snap.get("stats") or {}
    assert st.get("events_total") == 2
    assert st.get("actions_total", 0) >= 1
