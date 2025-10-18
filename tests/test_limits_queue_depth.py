from crapssim_control.external.command_channel import CommandQueue


def test_limits_queue_depth():
    q = CommandQueue(
        {
            "queue_max_depth": 2,
            "per_source_quota": 5,
            "rate": {"tokens": 10, "refill_seconds": 1000.0},
        }
    )

    base = {
        "run_id": "run",
        "action": "switch_profile",
        "args": {"target": "A"},
        "source": "src",
    }

    ok1, reason1 = q.enqueue({**base, "correlation_id": "cid-1"})
    ok2, reason2 = q.enqueue({**base, "correlation_id": "cid-2"})
    assert ok1 and reason1 == "accepted"
    assert ok2 and reason2 == "accepted"

    ok3, reason3 = q.enqueue({**base, "correlation_id": "cid-3"})
    assert not ok3 and reason3 == "queue_full"
