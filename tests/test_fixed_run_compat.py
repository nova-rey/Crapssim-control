import numpy as np

from run_demo import fixed_run_compat  # import from the demo for integration parity


class TableSeedSigOnly:
    def fixed_run(self, n_rolls, seed=None):
        return ("seed", n_rolls, seed)


class TableRngSigOnly:
    def fixed_run(self, n_rolls, rng=None):
        return ("rng", n_rolls, isinstance(rng, np.random.Generator))


class TableDicePairsRequired:
    def fixed_run(self, n_rolls, dice_outcomes):
        # Expect list of (d1,d2)
        assert isinstance(dice_outcomes, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in dice_outcomes)
        return ("pairs", n_rolls, len(dice_outcomes))


class TableDiceTotalsRequired:
    def fixed_run(self, n_rolls, dice_outcomes):
        # Expect list of totals (ints)
        assert isinstance(dice_outcomes, list)
        assert all(isinstance(x, int) for x in dice_outcomes)
        return ("totals", n_rolls, len(dice_outcomes))


def test_seed_passthrough_for_seed_sig():
    t = TableSeedSigOnly()
    kind, n, seed_val = fixed_run_compat(t, 7, seed=123)
    assert kind == "seed" and n == 7 and seed_val == 123


def test_seed_to_rng_for_rng_sig():
    t = TableRngSigOnly()
    kind, n, ok = fixed_run_compat(t, 9, seed=321)
    assert kind == "rng" and n == 9 and ok is True


def test_required_pairs_generation():
    t = TableDicePairsRequired()
    kind, n, count = fixed_run_compat(t, 10, seed=1)
    assert kind == "pairs" and n == 10 and count == 10


def test_required_totals_generation():
    t = TableDiceTotalsRequired()
    kind, n, count = fixed_run_compat(t, 12, seed=1)
    assert kind == "totals" and n == 12 and count == 12
