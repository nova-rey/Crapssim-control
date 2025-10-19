import warnings

from crapssim_control.engine_adapter import VanillaAdapter


def test_martingale_alias_emits_deprecation_once():
    adapter = VanillaAdapter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default", DeprecationWarning)
        adapter.apply_action("martingale", {"step_key": "6", "delta": 6, "max_level": 2})
        adapter.apply_action("martingale", {"step_key": "6", "delta": 6, "max_level": 2})
        msgs = [str(item.message) for item in caught if issubclass(item.category, DeprecationWarning)]
    assert any("deprecated" in message for message in msgs)
    assert len([message for message in msgs if "deprecated" in message]) == 1
