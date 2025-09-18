# tests/test_spec_validation.py
import pytest

from crapssim_control.spec_validation import validate_spec, assert_valid_spec, is_valid_spec, SpecValidationError


def _good_spec():
    return {
        "meta": {"name": "Unit Test Strat", "version": 1},
        "table": {"bubble": False, "level": 10, "odds_policy": "3-4-5x"},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {
            "Main": {
                "template": {
                    "pass": "units",
                    "place_6": 6,
                    "place_8": {"amount": "6"}  # nested amount allowed
                }
            }
        },
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]},
            {"on": {"event": "bet_resolved", "bet": "pass", "result": "lose"}, "do": ["units += 10", "apply_template('Main')"]},
            {"on": {"event": "bet_resolved", "bet": "pass", "result": "win"}, "do": ["units = 10", "apply_template('Main')"]},
        ],
    }


def test_valid_spec_passes():
    spec = _good_spec()
    errs = validate_spec(spec)
    assert errs == []
    assert is_valid_spec(spec) is True
    # assert_valid_spec should not raise
    assert_valid_spec(spec)


def test_missing_required_sections():
    spec = {"variables": {"units": 10}}
    errs = validate_spec(spec)
    assert "Missing required section: 'modes'" in errs
    assert "Missing required section: 'rules'" in errs


def test_modes_must_have_template():
    spec = _good_spec()
    del spec["modes"]["Main"]["template"]
    errs = validate_spec(spec)
    assert any("modes['Main'] is missing required key 'template'" in e for e in errs)


def test_template_values_type():
    spec = _good_spec()
    spec["modes"]["Main"]["template"]["place_6"] = {"amount": 6}
    assert validate_spec(spec) == []  # allowed

    spec["modes"]["Main"]["template"]["place_8"] = {"foo": 1}
    errs = validate_spec(spec)
    assert any("must be a number/string or an object with 'amount'" in e for e in errs)


def test_rules_shape_and_types():
    spec = _good_spec()
    spec["rules"][0]["on"]["event"] = 123
    errs = validate_spec(spec)
    assert any("on.event must be a string" in e for e in errs)

    spec = _good_spec()
    spec["rules"][0]["do"] = [42]
    errs = validate_spec(spec)
    assert any("do[0] must be a string" in e for e in errs)


def test_assert_valid_spec_raises():
    with pytest.raises(SpecValidationError) as ctx:
        assert_valid_spec({"modes": {}, "rules": []})
    # must include at least one mode error present
    assert any("define at least one mode" in e for e in ctx.value.errors)