from copy import deepcopy
from pathlib import Path

from crapssim_control.controller import ControlStrategy


def _base_spec(embed_analytics=True, *, csv_enabled=False, csv_path=None, report_path=None):
    run_cfg = {"csv": {"embed_analytics": embed_analytics}}
    if csv_enabled:
        if csv_path is None:
            raise ValueError("csv_path is required when csv_enabled=True")
        run_cfg["csv"].update(
            {
                "enabled": True,
                "path": str(csv_path),
                "append": False,
                "run_id": "TEST-RUN",
                "seed": 123,
            }
        )
    if report_path is not None:
        run_cfg.setdefault("report", {})["path"] = str(report_path)
        run_cfg["report"]["auto"] = False

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


def test_tracker_hooks_fire_when_enabled():
    spec = _base_spec(embed_analytics=True)
    ctrl = ControlStrategy(spec)

    assert ctrl._tracker is not None

    ctrl.handle_event({"type": "comeout"}, current_bets={})
    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
    ctrl.handle_event({"type": "roll"}, current_bets={})
    ctrl.handle_event({"type": "seven_out"}, current_bets={})
    ctrl.finalize_run()

    tracker = ctrl._tracker
    assert tracker.hand_id == 1
    assert tracker.roll_in_hand >= 1
    roll_snapshot = tracker.get_roll_snapshot()
    assert roll_snapshot["hand_id"] == 1
    assert roll_snapshot["roll_in_hand"] == tracker.roll_in_hand
    assert roll_snapshot["drawdown_after"] >= 0
    summary = tracker.get_summary_snapshot()
    assert summary["bankroll_peak"] >= summary["bankroll_low"]
    assert summary["max_drawdown"] >= 0


def test_tracker_not_initialized_when_disabled():
    spec = _base_spec(embed_analytics=False)
    ctrl = ControlStrategy(spec)

    assert ctrl._tracker is None

    # Running through lifecycle should not raise even without a tracker
    ctrl.handle_event({"type": "comeout"}, current_bets={})
    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
    ctrl.handle_event({"type": "roll"}, current_bets={})
    ctrl.handle_event({"type": "seven_out"}, current_bets={})
    ctrl.finalize_run()


def test_embed_flag_controls_csv_schema(tmp_path):
    csv_path_false = tmp_path / "without_analytics.csv"
    csv_path_true = tmp_path / "with_analytics.csv"

    spec_false = _base_spec(embed_analytics=False, csv_enabled=True, csv_path=csv_path_false)
    spec_true = _base_spec(embed_analytics=True, csv_enabled=True, csv_path=csv_path_true)

    ctrl_false = ControlStrategy(spec_false)
    ctrl_true = ControlStrategy(spec_true)

    for ctrl in (ctrl_false, ctrl_true):
        ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
        ctrl.finalize_run()

    header_expected = (
        "ts,run_id,seed,event_type,point,rolls_since_point,on_comeout,"
        "mode,units,bankroll,source,id,action,bet_type,amount,notes,extra"
    )
    header_with_analytics = header_expected + ",hand_id,roll_in_hand,bankroll_after,drawdown_after"

    def _header(path: Path) -> str:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return ""

    assert _header(csv_path_false) == header_expected
    assert _header(csv_path_true) == header_with_analytics

    report_false = ctrl_false.generate_report()
    report_true = ctrl_true.generate_report()

    def sanitize(report):
        sanitized = deepcopy(report)
        sanitized["metadata"]["run_flags"]["values"]["embed_analytics"] = None
        sanitized["metadata"]["run_flags"]["sources"]["embed_analytics"] = None
        sanitized["metadata"]["engine"] = {}
        sanitized["metadata"]["artifacts"] = {
            "journal": "SANITIZED",
            "report": "SANITIZED",
            "manifest": "SANITIZED",
        }
        sanitized["run_id"] = "SANITIZED"
        sanitized["manifest_path"] = "SANITIZED"
        sanitized["source_files"]["csv"] = "SANITIZED"
        sanitized["csv"]["path"] = "SANITIZED"
        summary = sanitized.get("summary", {})
        for key in (
            "total_hands",
            "total_rolls",
            "points_made",
            "pso_count",
            "bankroll_peak",
            "bankroll_low",
            "max_drawdown",
        ):
            summary.pop(key, None)
        return sanitized

    assert sanitize(report_false) == sanitize(report_true)
