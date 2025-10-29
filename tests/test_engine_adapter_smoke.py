# tests/test_engine_adapter_smoke.py
from crapssim_control.engine_adapter import EngineAdapter, NullAdapter
from crapssim_control.controller import ControlStrategy


def test_controller_defaults_to_null_adapter():
    spec = {
        "meta": {"version": 0, "name": "Adapter Smoke"},
        "table": {"bubble": True, "level": 5},
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"field": "units"}}},
        "rules": [{"on": {"event": "comeout"}, "do": ["apply_template('Main')"]}],
    }

    ctrl = ControlStrategy(spec)

    assert isinstance(ctrl.adapter, NullAdapter)
    ctrl.adapter.start_session({"table": spec["table"]})
    roll = ctrl.adapter.step_roll(dice=(2, 3))
    action_result = ctrl.adapter.apply_action("set", {"bet": "field"})
    snap = ctrl.adapter.snapshot_state()

    assert roll["result"] == "noop"
    assert action_result["result"] == "noop"
    assert isinstance(snap, dict) and snap["bankroll"] == 0.0


def test_engine_adapter_class_is_not_concrete():
    import inspect

    assert inspect.isabstract(EngineAdapter)
