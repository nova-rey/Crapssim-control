from crapssim_control.rules_engine.actions import ACTIONS, is_legal_timing


def test_switch_profile_executes_stub():
    res = ACTIONS["switch_profile"].execute({}, {"target": "Recovery"})
    assert res["applied"] == "switch_profile"
    assert res["target"] == "Recovery"


def test_illegal_timing_blocks_resolution():
    legal, reason = is_legal_timing({"resolving": True}, {"verb": "regress"})
    assert not legal
    assert reason == "during_resolution"


def test_legal_timing_passes():
    legal, reason = is_legal_timing({"resolving": False, "point_on": False}, {"verb": "switch_profile"})
    assert legal and reason == "ok"


def test_all_actions_return_trace():
    for verb, act in ACTIONS.items():
        result = act.execute({}, {"dummy": True})
        assert result["applied"] == verb
