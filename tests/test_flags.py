from crapssim_control.controller import ControlStrategy
from crapssim_control.config import DEMO_FALLBACKS_DEFAULT


def _spec(run: dict | None = None):
    spec = {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {}}},
        "rules": [],
    }
    if run is not None:
        spec["run"] = run
    return spec


def test_demo_fallbacks_default_off():
    ctrl = ControlStrategy(_spec())
    assert ctrl._flags["demo_fallbacks"] is DEMO_FALLBACKS_DEFAULT
    # Explicitly require the default to be False to protect the regression guard.
    assert DEMO_FALLBACKS_DEFAULT is False
    report = ctrl.generate_report()
    assert report.get("metadata", {}).get("demo_fallbacks_default") is DEMO_FALLBACKS_DEFAULT


def test_demo_fallbacks_explicit_true():
    ctrl = ControlStrategy(_spec({"demo_fallbacks": True}))
    assert ctrl._flags["demo_fallbacks"] is True


def test_demo_fallbacks_disable_auto_place_and_regress():
    ctrl = ControlStrategy(_spec())

    pe_actions = ctrl.handle_event({"type": "point_established", "point": 6}, {})
    assert pe_actions == []

    # Advance three rolls; no auto-regress actions should appear.
    for _ in range(3):
        actions = ctrl.handle_event({"type": "roll"}, {})
        assert actions == []


def test_demo_fallbacks_enabled_reinstates_behaviors():
    ctrl = ControlStrategy(_spec({"demo_fallbacks": True}))

    pe_actions = ctrl.handle_event({"type": "point_established", "point": 6}, {})
    assert any(a.get("id") == "template:fallback_place6" for a in pe_actions)

    # Third roll triggers the auto-regress clears.
    ctrl.handle_event({"type": "roll"}, {})
    ctrl.handle_event({"type": "roll"}, {})
    roll_actions = ctrl.handle_event({"type": "roll"}, {})
    assert {a.get("action") for a in roll_actions} == {"clear"}
    assert {a.get("bet_type") for a in roll_actions} == {"place_6", "place_8"}
