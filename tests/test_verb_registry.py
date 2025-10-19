import pytest

from crapssim_control.engine_adapter import PolicyRegistry, VerbRegistry


def test_unknown_verb_raises():
    with pytest.raises(KeyError):
        VerbRegistry.get("teleport")


def test_unknown_policy_raises():
    with pytest.raises(KeyError):
        PolicyRegistry.get("quantum_surge_v9")
