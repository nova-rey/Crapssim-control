from crapssim_control.external.command_channel import CommandQueue


def test_limits_per_source_quota():
    q = CommandQueue(
        {
            "queue_max_depth": 10,
            "per_source_quota": 1,
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
    assert ok1 and reason1 == "accepted"

    ok2, reason2 = q.enqueue({**base, "correlation_id": "cid-2"})
    assert not ok2 and reason2 == "per_source_quota"

    # Different source should still be allowed
    ok3, reason3 = q.enqueue({**base, "source": "other", "correlation_id": "cid-3"})
    assert ok3 and reason3 == "accepted"
