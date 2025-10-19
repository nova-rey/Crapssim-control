import pytest
from crapssim_control.engine_adapter import validate_effect_summary


def test_effect_validator_happy_path():
    eff = {"schema": "1.0", "verb": "press", "bets": {"6": "+6"}, "bankroll_delta": -6.0}
    validate_effect_summary(eff, "1.0")


def test_effect_validator_rejects_bad_delta():
    eff = {"schema": "1.0", "verb": "press", "bets": {"6": "6"}, "bankroll_delta": -6.0}
    with pytest.raises(ValueError):
        validate_effect_summary(eff, "1.0")


def test_effect_validator_missing_fields():
    with pytest.raises(ValueError):
        validate_effect_summary({"schema": "1.0"}, "1.0")
