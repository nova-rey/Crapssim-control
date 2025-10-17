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
