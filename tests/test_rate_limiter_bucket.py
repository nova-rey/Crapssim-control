from crapssim_control.external.command_channel import CommandQueue


def test_rate_limiter_bucket():
    q = CommandQueue(
        {
            "queue_max_depth": 10,
            "per_source_quota": 10,
            "rate": {"tokens": 3, "refill_seconds": 1000.0},
        }
    )

    base = {
        "run_id": "run",
        "action": "switch_profile",
        "args": {"target": "A"},
        "source": "src",
    }

    results = [q.enqueue({**base, "correlation_id": f"cid-{idx}"}) for idx in range(4)]

    accepts = [res for res in results if res[0]]
    rejects = [res for res in results if not res[0]]

    assert len(accepts) == 3
    assert rejects == [(False, "rate_limited")]
