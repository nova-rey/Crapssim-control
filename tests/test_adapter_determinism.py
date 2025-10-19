from crapssim_control.engine_adapter import VanillaAdapter


def test_deterministic_snapshots_same_seed():
    a1 = VanillaAdapter()
    a2 = VanillaAdapter()
    seed = 42
    a1.set_seed(seed)
    a2.set_seed(seed)
    s1 = a1.snapshot_state()
    s2 = a2.snapshot_state()
    assert s1["rng_seed"] == s2["rng_seed"] == seed
    assert s1 == s2
