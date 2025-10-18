from crapssim_control.controller import ControlStrategy


def _spec(embed_analytics=True):
    run_cfg: dict[str, object] = {
        "bankroll": 1000,
        "csv": {"embed_analytics": embed_analytics},
    }
    return {
        "run": run_cfg,
        "variables": {"units": 10},
        "modes": {"Main": {"template": {}}},
        "rules": [],
    }


def _run_session(ctrl: ControlStrategy, events):
    for ev in events:
        ctrl.handle_event(ev, current_bets={})
    ctrl.finalize_run()
    return ctrl.generate_report()


def test_summary_contains_expected_keys():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    events = [
        {"type": "comeout", "roll": 7, "bankroll_before": 1000, "bankroll_after": 1010},
        {"type": "point_established", "point": 6, "roll": 6, "bankroll_before": 1010, "bankroll_after": 1000},
        {"type": "roll", "roll": 8, "point": 6, "bankroll_before": 1000, "bankroll_after": 1020},
        {"type": "seven_out", "roll": 7, "point": 6, "bankroll_before": 1020, "bankroll_after": 980},
    ]

    report = _run_session(ctrl, events)

    summary = report.get("summary", {})
    for key in (
        "total_hands",
        "total_rolls",
        "points_made",
        "pso_count",
        "bankroll_peak",
        "bankroll_low",
        "max_drawdown",
    ):
        assert key in summary
    assert report.get("summary_schema_version") == "1.2"


def test_bankroll_peak_low_consistency():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    events = [
        {"type": "comeout", "roll": 7, "bankroll_before": 1000, "bankroll_after": 1000},
        {"type": "point_established", "point": 6, "roll": 6, "bankroll_before": 1000, "bankroll_after": 980},
        {"type": "roll", "roll": 9, "point": 6, "bankroll_before": 980, "bankroll_after": 1010},
        {"type": "roll", "roll": 5, "point": 6, "bankroll_before": 1010, "bankroll_after": 995},
        {"type": "seven_out", "roll": 7, "point": 6, "bankroll_before": 995, "bankroll_after": 950},
    ]

    report = _run_session(ctrl, events)
    tracker = ctrl._tracker
    assert tracker is not None

    summary = report.get("summary", {})
    assert summary["bankroll_low"] <= summary["bankroll_peak"]
    assert summary["max_drawdown"] >= 0

    expected_drawdown = summary["bankroll_peak"] - tracker.bankroll
    assert summary["max_drawdown"] <= expected_drawdown + 1e-6


def test_counts_reasonable():
    ctrl = ControlStrategy(_spec(embed_analytics=True))
    events = [
        {"type": "comeout", "roll": 7, "bankroll_before": 1000, "bankroll_after": 1000},
        {"type": "point_established", "point": 5, "roll": 5, "bankroll_before": 1000, "bankroll_after": 990},
        {"type": "roll", "roll": 9, "point": 5, "bankroll_before": 990, "bankroll_after": 1010},
        {"type": "seven_out", "roll": 7, "point": 5, "bankroll_before": 1010, "bankroll_after": 980},
    ]

    report = _run_session(ctrl, events)
    summary = report.get("summary", {})

    assert summary["total_hands"] >= 1
    assert summary["total_rolls"] >= summary["total_hands"]


def test_summary_flag_off_schema_version():
    ctrl = ControlStrategy(_spec(embed_analytics=False))
    ctrl.finalize_run()
    report = ctrl.generate_report()

    assert report.get("summary_schema_version") == "1.2"
    summary = report.get("summary")
    assert isinstance(summary, dict)
    # analytics fields may be missing or zero when tracker disabled
    assert summary.get("events_total") == 0
