import pytest

SEQ = [(3, 4), (2, 2), (6, 1), (5, 3), (6, 2), (4, 2), (3, 3), (6, 6), (5, 2), (2, 3)]

RULES = """
WHEN NOT point_on THEN line_bet(side=pass, amount=10)
WHEN point_on AND bets.6 == 0 THEN place_bet(number=6, amount=12)
WHEN point_on AND bets.8 == 0 THEN place_bet(number=8, amount=12)
"""


def run(adapter, seq, trace=False, explain=False):
    adapter.start_session({"run": {"journal": {"explain": explain}}})
    adapter.load_ruleset(RULES)
    if hasattr(adapter, "enable_dsl_trace"):
        adapter.enable_dsl_trace(trace)
    for dice in seq:
        adapter.step_roll(dice=dice)
    return adapter.snapshot_state()


def test_parity_with_and_without_tracing():
    from crapssim_control.engine_adapter import VanillaAdapter

    adapter_plain = VanillaAdapter()
    state_plain = run(adapter_plain, SEQ, trace=False, explain=False)

    adapter_verbose = VanillaAdapter()
    state_verbose = run(adapter_verbose, SEQ, trace=True, explain=True)

    assert state_plain.get("bankroll") == state_verbose.get("bankroll")
    assert state_plain.get("point_on") == state_verbose.get("point_on")
    assert state_plain.get("point_value") == state_verbose.get("point_value")
