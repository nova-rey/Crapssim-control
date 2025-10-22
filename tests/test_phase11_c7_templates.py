from crapssim_control import dsl_helpers as H


def test_new_templates_expand_and_validate():
    rule = H.generate_rule("set_come_odds_on_travel", num=6, amt=30)
    assert "WHEN" in rule and "THEN" in rule
    assert "odds.come.6 == 0" in rule

    rule2 = H.generate_rule("pull_dc_between_rolls", num=8)
    assert "cancel_bet" in rule2
