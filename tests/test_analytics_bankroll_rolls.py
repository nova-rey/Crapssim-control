import csv
from pathlib import Path

import pytest

from crapssim_control.controller import ControlStrategy
from tests import skip_csv_preamble


def _spec(embed_analytics=True, *, csv_path: Path | None = None):
    run_cfg: dict[str, object] = {
        "bankroll": 1000,
        "csv": {"embed_analytics": embed_analytics},
    }
    if csv_path is not None:
        run_cfg["csv"].update(
            {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "ANALYTICS-TEST",
                "seed": 42,
            }
        )
    spec = {
        "variables": {"units": 5},
        "modes": {
            "Main": {
                "template": {
                    "pass": "units",
                    "place": {"6": "units", "8": "units"},
                }
            }
        },
        "rules": [],
    }
    if run_cfg:
        spec["run"] = run_cfg
    return spec


def test_roll_counters_reset_each_hand():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    tracker = ctrl._tracker
    assert tracker is not None

    events = [
        {"type": "comeout", "roll": 7, "bankroll_before": 1000, "bankroll_after": 1010},
        {"type": "point_established", "point": 6, "roll": 6, "bankroll_before": 1010, "bankroll_after": 1010},
        {"type": "seven_out", "roll": 7, "bankroll_before": 1010, "bankroll_after": 995},
        {"type": "comeout", "roll": 8, "bankroll_before": 995, "bankroll_after": 995},
    ]

    for ev in events:
        ctrl.handle_event(ev, current_bets={})

    assert tracker.hand_id == 2
    assert tracker.roll_in_hand == 1
    snap = tracker.get_roll_snapshot()
    assert snap["hand_id"] == 2
    assert snap["roll_in_hand"] == 1


def test_bankroll_continuity():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    tracker = ctrl._tracker
    assert tracker is not None

    sequence = [
        ("comeout", 1000.0, 1000.0),
        ("point_established", 1000.0, 980.0),
        ("roll", 980.0, 995.0),
        ("seven_out", 995.0, 960.0),
    ]

    previous_after = tracker.bankroll
    for ev_type, before, after in sequence:
        ctrl.handle_event(
            {
                "type": ev_type,
                "roll": 6 if ev_type != "seven_out" else 7,
                "bankroll_before": before,
                "bankroll_after": after,
                "point": 6 if ev_type != "comeout" else None,
            },
            current_bets={},
        )
        assert tracker.bankroll == pytest.approx(after)
        assert previous_after == pytest.approx(before)
        delta_expected = after - before
        assert tracker.bankroll - previous_after == pytest.approx(delta_expected)
        previous_after = tracker.bankroll


def test_drawdown_tracking():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    tracker = ctrl._tracker
    assert tracker is not None

    events = [
        {"type": "comeout", "roll": 7, "bankroll_before": 1000, "bankroll_after": 1000},
        {"type": "roll", "roll": 8, "bankroll_before": 1000, "bankroll_after": 1020},
        {"type": "roll", "roll": 5, "bankroll_before": 1020, "bankroll_after": 980},
        {"type": "roll", "roll": 9, "bankroll_before": 980, "bankroll_after": 990},
        {"type": "seven_out", "roll": 7, "bankroll_before": 990, "bankroll_after": 950},
    ]

    for ev in events:
        ctrl.handle_event(ev, current_bets={})
        snap = tracker.get_roll_snapshot()
        assert snap["drawdown_after"] >= 0

    summary = tracker.get_summary_snapshot()
    assert summary["max_drawdown"] == pytest.approx(70.0)


def test_flag_off_no_schema_diff(tmp_path):
    csv_path = tmp_path / "journal.csv"
    ctrl = ControlStrategy(_spec(embed_analytics=False, csv_path=csv_path))

    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
    ctrl.finalize_run()

    baseline_header = Path("baselines/phase2/journal.csv").read_text(encoding="utf-8").splitlines()[0]
    with csv_path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            produced_header = stripped
            break
        else:
            produced_header = ""
    assert produced_header == baseline_header


def test_flag_on_additive_schema(tmp_path):
    csv_path = tmp_path / "journal.csv"
    ctrl = ControlStrategy(_spec(embed_analytics=True, csv_path=csv_path))

    ctrl.handle_event(
        {
            "type": "comeout",
            "roll": 7,
            "bankroll_before": 1000,
            "bankroll_after": 1000,
        },
        current_bets={},
    )
    ctrl.handle_event(
        {
            "type": "point_established",
            "point": 6,
            "roll": 6,
            "bankroll_before": 1000,
            "bankroll_after": 990,
        },
        current_bets={},
    )
    ctrl.finalize_run()

    with csv_path.open(newline="", encoding="utf-8") as f:
        skip_csv_preamble(f)
        reader = csv.DictReader(f)
        rows = list(reader)

    assert "hand_id" in reader.fieldnames
    assert "roll_in_hand" in reader.fieldnames
    assert "bankroll_after" in reader.fieldnames
    assert "drawdown_after" in reader.fieldnames

    first_row = rows[0]
    assert int(first_row["hand_id"]) == 1
    assert int(first_row["roll_in_hand"]) >= 1
    assert float(first_row["bankroll_after"]) == pytest.approx(990.0)
    assert float(first_row["drawdown_after"]) == pytest.approx(10.0)
