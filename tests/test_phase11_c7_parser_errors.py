import pytest

from crapssim_control.dsl_parser import DSLParseError, parse_sentence


def test_missing_then_reports_location():
    with pytest.raises(DSLParseError) as excinfo:
        parse_sentence("WHEN bankroll < 1000 regress()")
    msg = str(excinfo.value)
    assert "Missing THEN" in msg
    assert "line" in msg and "col" in msg
    assert "^" in msg


def test_malformed_then_reports_snippet():
    with pytest.raises(DSLParseError) as excinfo:
        parse_sentence("WHEN point_on THEN place_bet 6,12")
    msg = str(excinfo.value)
    assert "Malformed THEN clause" in msg
    assert "place_bet" in msg
