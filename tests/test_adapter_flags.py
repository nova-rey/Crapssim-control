from crapssim_control.engine_adapter import NullAdapter, VanillaAdapter
from crapssim_control.controller import ControlStrategy


def test_flag_selects_correct_adapter():
    cfg = {"run": {"adapter": {"enabled": False}}}
    c = ControlStrategy(cfg)
    assert isinstance(c.adapter, NullAdapter)

    cfg = {"run": {"adapter": {"enabled": True, "impl": "vanilla"}}}
    c2 = ControlStrategy(cfg)
    assert isinstance(c2.adapter, VanillaAdapter)
