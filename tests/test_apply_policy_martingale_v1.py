from crapssim_control.engine_adapter import VanillaAdapter


def test_martingale_policy_levels_and_deltas():
    adapter = VanillaAdapter()

    effect1 = adapter.apply_action(
        "apply_policy",
        {"policy": {"name": "martingale_v1", "args": {"step_key": "6", "delta": 6, "max_level": 3}}},
    )
    assert effect1["policy"] == "martingale_v1"
    assert effect1["bets"].get("6") == "+6"
    snap1 = adapter.snapshot_state()
    assert snap1["bets"]["6"] == 6.0
    assert snap1["levels"]["6"] == 1

    effect2 = adapter.apply_action(
        "apply_policy",
        {"policy": {"name": "martingale_v1", "args": {"step_key": "6", "delta": 6, "max_level": 3}}},
    )
    assert effect2["bets"]["6"] == "+12"
    snap2 = adapter.snapshot_state()
    assert snap2["bets"]["6"] == 18.0
    assert snap2["levels"]["6"] == 2

    effect3 = adapter.apply_action(
        "apply_policy",
        {"policy": {"name": "martingale_v1", "args": {"step_key": "6", "delta": 6, "max_level": 3}}},
    )
    assert effect3["bets"]["6"] == "+18"
    snap3 = adapter.snapshot_state()
    assert snap3["bets"]["6"] == 36.0
    assert snap3["levels"]["6"] == 3

    effect4 = adapter.apply_action(
        "apply_policy",
        {"policy": {"name": "martingale_v1", "args": {"step_key": "6", "delta": 6, "max_level": 3}}},
    )
    snap4 = adapter.snapshot_state()
    assert snap4["levels"]["6"] == 0
    assert "6" not in effect4.get("bets", {}) or effect4["bets"]["6"] in {"+0", "-0"}
