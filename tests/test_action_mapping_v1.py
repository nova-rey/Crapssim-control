from crapssim_control.engine_adapter import VanillaAdapter


def test_press_increments_target_bet():
    adapter = VanillaAdapter()
    effect = adapter.apply_action(
        "press",
        {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
    )
    assert effect["verb"] == "press"
    assert effect["bets"]["6"] == "+6"
    snap = adapter.snapshot_state()
    assert snap["bets"]["6"] == 6.0
    assert snap["bankroll"] == adapter.bankroll == 994.0


def test_regress_halves_selected_bets():
    adapter = VanillaAdapter()
    adapter.bets.update({"6": 12.0, "8": 18.0})
    effect = adapter.apply_action("regress", {"target": {"selector": ["6", "8"]}})
    assert effect["verb"] == "regress"
    assert adapter.bets["6"] == 6.0
    assert adapter.bets["8"] == 9.0
    assert adapter.bankroll == 1000.0 + 6.0 + 9.0


def test_switch_profile_effect_summary():
    adapter = VanillaAdapter()
    effect = adapter.apply_action("switch_profile", {"details": {"profile": "aggressive"}})
    assert effect["verb"] == "switch_profile"
    assert effect["target"]["profile"] == "aggressive"
