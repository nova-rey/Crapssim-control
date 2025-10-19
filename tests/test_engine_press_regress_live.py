import math
from typing import Dict

import pytest

from crapssim_control.engine_adapter import VanillaAdapter


def test_press_regress_live_engine_snapshot_normalized():
    pytest.importorskip("crapssim", reason="CrapsSim not installed")

    adapter = VanillaAdapter()
    spec = {
        "run": {
            "adapter": {"enabled": True, "impl": "vanilla", "live_engine": True},
            "seed": 42,
        }
    }
    adapter.start_session(spec)
    if not getattr(adapter, "live_engine", False) or getattr(adapter, "_engine_adapter", None) is None:
        pytest.skip("CrapsSim adapter unavailable in environment")

    def _sum_bets(snapshot: Dict[str, float]) -> float:
        return sum(float(v) for v in snapshot.values())

    initial_snapshot = adapter.snapshot_state()
    total_before = _sum_bets(initial_snapshot.get("bets", {}))
    bankroll_before = float(initial_snapshot.get("bankroll", 0.0))

    effect_press = adapter.apply_action(
        "press",
        {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
    )
    snapshot_after_press = adapter.snapshot_state()
    total_after_press = _sum_bets(snapshot_after_press.get("bets", {}))
    bankroll_after_press = float(snapshot_after_press.get("bankroll", 0.0))

    assert effect_press["schema"] == "1.0"
    assert effect_press["verb"] == "press"
    assert total_after_press >= total_before
    assert bankroll_after_press <= bankroll_before

    effect_regress = adapter.apply_action("regress", {"target": {"selector": ["6"]}})
    snapshot_after_regress = adapter.snapshot_state()
    total_after_regress = _sum_bets(snapshot_after_regress.get("bets", {}))
    bankroll_after_regress = float(snapshot_after_regress.get("bankroll", 0.0))

    assert effect_regress["schema"] == "1.0"
    assert effect_regress["verb"] == "regress"
    assert total_after_regress <= total_after_press
    assert bankroll_after_regress >= bankroll_after_press

    rng_seed = snapshot_after_regress.get("rng_seed")
    assert rng_seed in {42, adapter.seed}
    assert not math.isnan(float(rng_seed))
