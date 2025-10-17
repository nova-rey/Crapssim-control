import inspect
import numpy as np


def fixed_run_compat(table, n_rolls, **kwargs):
    sig = inspect.signature(type(table).fixed_run)
    param_names = set(sig.parameters.keys())
    if "rng" in param_names and "seed" in kwargs:
        rng = np.random.default_rng(kwargs.pop("seed"))
        kwargs.setdefault("rng", rng)
    if "seed" in param_names and "rng" in kwargs and "seed" not in kwargs:
        kwargs.pop("rng", None)
    call_kwargs = {name: kwargs[name] for name in list(kwargs.keys()) if name in param_names}
    return table.fixed_run(n_rolls, **call_kwargs)


class TableSeed:
    def fixed_run(self, n_rolls, seed=None):
        return ("seed", n_rolls, seed)


class TableRng:
    def fixed_run(self, n_rolls, rng=None):
        return ("rng", n_rolls, isinstance(rng, np.random.Generator))


class TableNoKw:
    def fixed_run(self, n_rolls):
        return ("plain", n_rolls)


def test_adapter_seed_to_rng():
    t = TableRng()
    kind, n, ok = fixed_run_compat(t, 10, seed=123)
    assert kind == "rng" and n == 10 and ok is True


def test_adapter_rng_to_seed_drop():
    t = TableSeed()
    kind, n, seed_val = fixed_run_compat(t, 12, rng=np.random.default_rng(1))
    assert kind == "seed" and n == 12 and (seed_val is None or isinstance(seed_val, (int, type(None))))


def test_adapter_seed_passthrough():
    t = TableSeed()
    kind, n, seed_val = fixed_run_compat(t, 8, seed=42)
    assert kind == "seed" and n == 8 and seed_val == 42


def test_adapter_drops_unknown_kwargs():
    t = TableNoKw()
    kind, n = fixed_run_compat(t, 5, seed=99, rng=np.random.default_rng(0), runout=True)
    assert kind == "plain" and n == 5
