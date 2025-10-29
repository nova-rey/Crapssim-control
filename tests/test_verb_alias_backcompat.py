from crapssim_control.engine_adapter import VanillaAdapter


def test_legacy_martingale_alias_routes_to_policy():
    adapter = VanillaAdapter()
    effect = adapter.apply_action("martingale", {"step_key": "dc", "delta": 1, "max_level": 2})
    assert effect["policy"] == "martingale_v1"

    follow_up = adapter.apply_action(
        "apply_policy",
        {
            "policy": {
                "name": "martingale_v1",
                "args": {"step_key": "dc", "delta": 1, "max_level": 2},
            }
        },
    )
    assert "level_update" in follow_up
