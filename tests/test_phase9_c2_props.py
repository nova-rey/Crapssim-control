import pytest

crapssim = pytest.importorskip("crapssim")


def _live_adapter():
    from crapssim_control.engine_adapter import VanillaAdapter

    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": True}}})
    return adapter


def test_any7_and_anycraps_resolution(tmp_path):
    a = _live_adapter()
    eff1 = a.apply_action("any7_bet", {"amount": {"mode": "dollars", "value": 5}})
    eff2 = a.apply_action("anycraps_bet", {"amount": {"mode": "dollars", "value": 5}})
    assert eff1.get("one_roll") is True
    assert eff2.get("one_roll") is True
    r = a.step_roll(dice=(3, 4))
    snap = a.snapshot_state()
    props = snap.get("props", {})
    assert props == {} or all(float(v) == 0.0 for v in props.values())


def test_hop_single_roll_lifecycle():
    a = _live_adapter()
    eff = a.apply_action(
        "hop_bet",
        {"d1": 2, "d2": 3, "amount": {"mode": "dollars", "value": 5}},
    )
    assert eff.get("one_roll") is True
    a.step_roll(dice=(3, 2))
    snap = a.snapshot_state()
    assert "hop_2-3" not in snap.get("props", {})


def test_ce_behavior_fixed_outcomes():
    a = _live_adapter()
    eff = a.apply_action("ce_bet", {"amount": {"mode": "dollars", "value": 5}})
    assert eff.get("one_roll") is True
    a.step_roll(dice=(5, 6))
    snap = a.snapshot_state()
    props = snap.get("props", {})
    assert props == {} or all(float(v) == 0.0 for v in props.values())
