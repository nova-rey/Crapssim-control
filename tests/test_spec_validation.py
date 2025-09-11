# tests/test_spec_validation.py
from crapssim_control.spec import validate_spec

def _valid_spec():
    return {
        "meta": {"version": 0, "name": "Test"},
        "table": {"bubble": False, "level": 10, "odds_policy": "3-4-5x"},
        "variables": {"units": 10, "mode": "Main"},
        "modes": {
            "Main": {
                "template": {
                    "pass": "units",
                    "place": {"6": "units*2", "8": "units*2"},
                }
            }
        },
        "rules": [
            {"on": {"event": "comeout"}, "do": ["apply_template('Main')"]},
            {"on": {"event": "roll"}, "if": "units >= 10", "do": ["units += 5"]},
            {"on": {"event": "bet_resolved", "bet": "pass", "result": "lose"}, "do": ["units += 10"]},
        ],
    }

def test_valid_spec_passes():
    ok, errors = validate_spec(_valid_spec())
    assert ok, f"Expected valid spec, got errors: {errors}"

def test_invalid_event_name():
    spec = _valid_spec()
    spec["rules"][0]["on"]["event"] = "not_an_event"
    ok, errors = validate_spec(spec)
    assert not ok
    assert any("on.event" in e for e in errors)

def test_modes_requires_template():
    spec = _valid_spec()
    spec["modes"]["Main"].pop("template")
    ok, errors = validate_spec(spec)
    assert not ok
    assert any("template is required" in e for e in errors)

def test_template_place_requires_dict():
    spec = _valid_spec()
    spec["modes"]["Main"]["template"]["place"] = 123
    ok, errors = validate_spec(spec)
    assert not ok
    assert any("must be an object mapping numbers to expressions" in e for e in errors)

def test_table_level_must_be_int():
    spec = _valid_spec()
    spec["table"]["level"] = "ten"
    ok, errors = validate_spec(spec)
    assert not ok
    assert any("table.level must be integer" in e for e in errors)

def test_rules_do_must_be_list_of_strings():
    spec = _valid_spec()
    spec["rules"][0]["do"] = ["ok", 123]
    ok, errors = validate_spec(spec)
    assert not ok
    assert any("do must be a list of strings" in e for e in errors)