from crapssim_control.external.command_channel import CommandQueue


def test_enqueue_and_duplicate():
    q = CommandQueue()
    ok, reason = q.enqueue({"run_id": "r1", "action": "switch_profile", "args": {}, "source": "nr", "correlation_id": 123})
    assert ok and reason == "accepted"
    ok2, reason2 = q.enqueue({"run_id": "r1", "action": "switch_profile", "args": {}, "source": "nr", "correlation_id": 123})
    assert not ok2 and reason2 == "duplicate_correlation_id"


def test_unknown_action_rejected():
    q = CommandQueue()
    ok, reason = q.enqueue({"run_id": "r1", "action": "explode", "args": {}, "source": "nr", "correlation_id": "x"})
    assert not ok and reason == "unknown_action"
