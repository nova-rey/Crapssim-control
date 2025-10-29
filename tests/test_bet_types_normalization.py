# tests/test_bet_types_normalization.py
from crapssim_control.bet_types import normalize_bet_type


def test_place_number_aliases():
    assert normalize_bet_type("Place 6", {"number": 6}) == "place_6"
    assert normalize_bet_type("PL6", {"number": 6}) == "place_6"
    assert normalize_bet_type("place_8", {"number": 8}) == "place_8"
    # Lone number should become place_n
    assert normalize_bet_type("6", {}) == "place_6"


def test_line_and_come_families():
    assert normalize_bet_type("Pass", {}) == "pass_line"
    assert normalize_bet_type("pass line", {}) == "pass_line"
    assert normalize_bet_type("Don't Pass", {}) == "dont_pass"
    assert normalize_bet_type("dp", {}) == "dont_pass"
    assert normalize_bet_type("come", {}) == "come"
    assert normalize_bet_type("don't come", {}) == "dont_come"
    assert normalize_bet_type("dc", {}) == "dont_come"


def test_odds_context_and_numbers():
    assert normalize_bet_type("odds 5 come", {}) == "odds_5_come"
    assert normalize_bet_type("odds 6 line", {}) == "odds_6_line"
    assert normalize_bet_type("come odds 5", {}) == "odds_5_come"
    # If no number present, leave generic
    assert normalize_bet_type("odds", {}) == "odds"


def test_field_and_hardways():
    assert normalize_bet_type("field", {}) == "field"
    assert normalize_bet_type("hard 8", {}) == "hard_8"
    assert normalize_bet_type("hardways", {"number": 6}) == "hard_6"
