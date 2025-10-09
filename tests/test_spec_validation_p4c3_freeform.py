import pytest
from crapssim_control.spec_validation import validate_spec

def _good_spec():
    return {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]},
            {"on": {"event": "roll"}, "do": ["units 10"]},  # legacy free-form starter allowed
        ],
    }

def test_freeform_calls_and_units_allowed():
    errs = validate_spec(_good_spec())
    assert errs == []

def test_unknown_verb_is_flagged():
    spec = _good_spec()
    spec["rules"][1]["do"] = ["explode place_6 10"]  # looks like verb + args
    errs = validate_spec(spec)
    assert any("unknown action 'explode'" in e for e in errs)