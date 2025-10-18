from crapssim_control.external.command_channel import CommandQueue


def test_enqueue_ok_and_duplicate():
    q = CommandQueue()
    cmd = {
        "run_id": "r1",
        "action": "switch_profile",
        "args": {"name": "Recovery"},
        "source": "node-red@flow",
        "correlation_id": "c1",
    }
    ok, reason = q.enqueue(cmd)
    assert ok and reason == "accepted"
    ok2, reason2 = q.enqueue(cmd)
    assert not ok2 and reason2 == "duplicate_correlation_id"


def test_drain_clears_queue():
    q = CommandQueue()
    q.enqueue({
        "run_id": "r1",
        "action": "regress",
        "args": {},
        "source": "nr",
        "correlation_id": "c2",
    })
    items = q.drain()
    assert len(items) == 1
    assert len(q.drain()) == 0
