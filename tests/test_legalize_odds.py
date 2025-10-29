from crapssim_control.legalize_legacy import legalize_odds


def test_legalize_odds_345x_nonbubble():
    # Base flat = 10 under common 3-4-5x
    # 6/8: max 5x => 50, step 5 => 50
    assert legalize_odds(6, 100, 10, bubble=False, policy="3-4-5x") == 50
    # 5/9: max 4x => 40, step 2 => 40
    assert legalize_odds(5, 100, 10, bubble=False, policy="3-4-5x") == 40
    # 4/10: max 3x => 30, step 1 => 30
    assert legalize_odds(4, 100, 10, bubble=False, policy="3-4-5x") == 30


def test_legalize_odds_uniform_2x():
    # Uniform 2x -- cap = 20 on all points, step enforced by point
    assert legalize_odds(6, 27, 10, bubble=False, policy="2x") == 20  # step 5 forces 20
    assert legalize_odds(5, 27, 10, bubble=False, policy="2x") == 20  # step 2 forces 20
    assert legalize_odds(4, 27, 10, bubble=False, policy="2x") == 20  # step 1 keeps 20


def test_legalize_odds_bubble_10x():
    # Bubble: step = $1 always
    assert legalize_odds(6, 97, 10, bubble=True, policy="10x") == 97  # cap = 100
    assert legalize_odds(5, 123, 10, bubble=True, policy=10) == 100


def test_legalize_odds_no_point_is_zero():
    assert legalize_odds(None, 50, 10, bubble=False, policy="3-4-5x") == 0
