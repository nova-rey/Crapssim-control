from crapssim_control.journal import normalize_effect_summary, dumps_effect_summary_line
import json


def test_normalize_infers_and_preserves_keys():
    raw = {"bets": {"6": "+6"}, "bankroll_delta": -6.0, "schema": "1.0"}
    norm = normalize_effect_summary(raw)
    assert norm["schema"] == "1.0"
    assert "verb" in norm and isinstance(norm["verb"], str)


def test_dumps_includes_verb_and_stable_order():
    eff = {"verb": "place_bet", "bets": {"8": "+12"}, "bankroll_delta": -12.0}
    line = dumps_effect_summary_line(eff)
    obj = json.loads(line)
    assert obj["verb"] == "place_bet"
    assert obj["bets"]["8"] == "+12"
    assert "schema" in obj and obj["schema"] == "1.0"
