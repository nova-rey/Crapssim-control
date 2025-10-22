import pytest

from crapssim_control.dsl_parser import DSLParseError, parse_file, parse_sentence


def test_parse_basic_sentence():
    sentence = "WHEN bankroll < 500 AND point_on THEN regress()"
    rule = parse_sentence(sentence)
    assert rule["when"] == "bankroll < 500 AND point_on"
    assert rule["then"]["verb"] == "regress"


def test_parse_with_args():
    sentence = "WHEN point_on THEN place_bet(number=6, amount=12)"
    rule = parse_sentence(sentence)
    args = rule["then"]["args"]
    assert args["number"] == "6"
    assert args["amount"] == "12"


def test_invalid_missing_then():
    with pytest.raises(DSLParseError):
        parse_sentence("WHEN bankroll < 500")


def test_multiple_rules():
    text = """
    WHEN bankroll < 500 THEN regress()
    WHEN point_on THEN place_bet(number=8, amount=12)
    """
    rules = parse_file(text)
    assert len(rules) == 2
