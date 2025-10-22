import pytest

from crapssim_control import dsl_helpers


def test_generate_rule_valid():
    text = dsl_helpers.generate_rule("press_on_hit", num=6)
    assert "WHEN" in text and "THEN" in text


def test_generate_rule_invalid_template():
    with pytest.raises(KeyError):
        dsl_helpers.generate_rule("unknown")


def test_validate_ruleset_inline_valid():
    text = "WHEN bankroll < 1000 THEN regress()"
    res = dsl_helpers.validate_ruleset(text)
    assert res["valid"] and res["count"] == 1


def test_validate_ruleset_bad_syntax():
    bad = "WHEN bankroll < THEN regress()"
    res = dsl_helpers.validate_ruleset(bad)
    assert not res["valid"] and res["errors"]


def test_cli_list_and_new(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["csc", "dsl", "list"])
    assert dsl_helpers.cli_entry(["dsl", "list"]) == 0
    monkeypatch.setattr("sys.argv", ["csc", "dsl", "new", "press_on_hit", "num=8"])
    assert dsl_helpers.cli_entry(["dsl", "new", "press_on_hit", "num=8"]) == 0
