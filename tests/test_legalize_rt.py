from crapssim_control.legalize import legalize_amount, cap_odds_amount

def test_place_increments_nonbubble():
    cfg = {"bubble": False}
    # place 6/8 in $6s
    assert legalize_amount("place_6", 14, cfg)[0] == 12
    assert legalize_amount("place_8", 12, cfg)[0] == 12
    # place 5/9 in $5s
    assert legalize_amount("place_5", 14, cfg)[0] == 10
    assert legalize_amount("place_9", 15, cfg)[0] == 15
    # place 4/10 default to $5 increments
    assert legalize_amount("place_4", 19, cfg)[0] == 15
    assert legalize_amount("place_10", 20, cfg)[0] == 20

def test_place_increments_bubble():
    cfg = {"bubble": True}
    assert legalize_amount("place_6", 14, cfg)[0] == 14
    assert legalize_amount("place_5", 14, cfg)[0] == 14

def test_line_minimums():
    cfg = {"level": 15}
    assert legalize_amount("pass_line", 10, cfg)[0] == 15
    assert legalize_amount("dont_pass", 22.7, cfg)[0] == 22  # min applied on pass; dp just $1 increments here

def test_odds_capped():
    # base pass $10, 3x max -> cap 30
    cfg = {"max_odds_multiple": 3.0}
    legal, flags = legalize_amount("odds_6_pass", 50, cfg, point=6, base_line_bet=10)
    assert legal == 30 and flags["clamped"]
    # $1 rounding
    legal, _ = legalize_amount("odds_6_pass", 29.7, cfg, point=6, base_line_bet=10)
    assert legal == 29

def test_cap_odds_amount_helper():
    assert cap_odds_amount(10, 44, 3.0) == 30
    assert cap_odds_amount(25, 74.9, 3.0) == 74