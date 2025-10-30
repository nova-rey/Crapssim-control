import pytest
from crapssim_control.behavior import parse_rules, DSLSpecError


def test_parse_good_rules():
    spec = {
        "behavior": {
            "schema_version": "1.0",
            "rules": [
                {"id": "r1", "when": "drawdown > 0.15", "then": "regress(bet=place_6, units=1)"}
            ],
        }
    }
    rules = parse_rules(spec)
    assert rules and rules[0].id == "r1"


def test_parse_bad_var():
    spec = {
        "behavior": {
            "schema_version": "1.0",
            "rules": [{"id": "r1", "when": "unknown > 0", "then": "regress(bet=place_6)"}],
        }
    }
    with pytest.raises(DSLSpecError):
        parse_rules(spec)


def test_parse_unknown_verb():
    spec = {
        "behavior": {
            "schema_version": "1.0",
            "rules": [{"id": "r1", "when": "profit > 0", "then": "moonwalk()"}],
        }
    }
    with pytest.raises(DSLSpecError):
        parse_rules(spec)
