from crapssim_control.external.command_channel import CommandQueue


def test_timing_reject_logged(tmp_path):
    # simulate command with illegal timing
    q = CommandQueue()
    cmd = {
        "run_id": "r1",
        "action": "switch_profile",
        "args": {},
        "source": "nr",
        "correlation_id": "c99",
    }
    accepted, reason = q.enqueue(cmd)
    assert accepted is True
    assert reason == "accepted"
    # Fake current_state disallow timing
    current_state = {"resolving": True, "point_on": True, "roll_in_hand": 1}
    from crapssim_control.rules_engine.actions import is_legal_timing

    legal, reason = is_legal_timing(current_state, {"verb": "switch_profile"})
    assert not legal
    assert reason
