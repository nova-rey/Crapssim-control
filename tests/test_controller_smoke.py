from crapssim_control import ControlStrategy


def test_controller_import_and_init():
    spec = {
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [],
    }
    cs = ControlStrategy(spec)
    assert hasattr(cs, "update_bets")
    assert hasattr(cs, "after_roll")
