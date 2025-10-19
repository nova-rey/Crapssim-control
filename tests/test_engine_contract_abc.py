from crapssim_control.engine_adapter import EngineAdapter, NullAdapter


def test_null_adapter_implements_all_methods():
    adapter = NullAdapter()
    adapter.start_session({})
    result_roll = adapter.step_roll(dice=(3, 4))
    result_action = adapter.apply_action("press", {"target": {"bet": "6"}, "amount": {"value": 5}})
    snap = adapter.snapshot_state()

    assert isinstance(result_roll, dict)
    assert isinstance(result_action, dict)
    assert isinstance(snap, dict)
    assert "bankroll" in snap


def test_engine_adapter_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        EngineAdapter()
