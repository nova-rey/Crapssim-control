from crapssim_control.engine_adapter import VanillaAdapter


def test_press_and_collect_deterministic():
    v = VanillaAdapter()
    result = v.apply_action("press_and_collect", {})
    assert result["bankroll_delta"] == -12.0
    snap = v.snapshot_state()
    assert snap["bets"]["6"] == 6.0
    assert snap["bets"]["8"] == 6.0


def test_regress_halves_bets_and_restores_bankroll():
    v = VanillaAdapter()
    v.bets = {"6": 12.0, "8": 12.0}
    v.bankroll = 1000.0
    result = v.apply_action("regress", {})
    assert result["verb"] == "regress"
    assert v.bets["6"] == 6.0
    assert v.bankroll > 1000.0


def test_switch_profile_records_name():
    v = VanillaAdapter()
    result = v.apply_action("switch_profile", {"profile": "aggressive"})
    assert result["details"]["profile"] == "aggressive"
