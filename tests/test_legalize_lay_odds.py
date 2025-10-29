from crapssim_control.legalize_legacy import legalize_lay_odds


def test_lay_odds_345x_nonbubble():
    # base flat = 10; win-cap = multiple * flat
    # 4/10: multiple 3 → win-cap=30; lay-cap = 60; step 2 → floor
    assert legalize_lay_odds(4, 100, 10, bubble=False, policy="3-4-5x") == 60
    # 5/9: multiple 4 → win-cap=40; lay-cap = floor(40*3/2)=60; step 3 → 60
    assert legalize_lay_odds(5, 100, 10, bubble=False, policy="3-4-5x") == 60
    # 6/8: multiple 5 → win-cap=50; lay-cap = floor(50*6/5)=60; step 6 → 60
    assert legalize_lay_odds(6, 100, 10, bubble=False, policy="3-4-5x") == 60


def test_lay_odds_uniform_2x_nonbubble():
    # multiple = 2 → win-cap=20
    # 4/10: lay-cap=40; step 2 → 40
    assert legalize_lay_odds(4, 41, 10, bubble=False, policy="2x") == 40
    # 5/9: lay-cap=floor(20*3/2)=30; step 3 → 30
    assert legalize_lay_odds(5, 31, 10, bubble=False, policy="2x") == 30
    # 6/8: lay-cap=floor(20*6/5)=24; step 6 → 24
    assert legalize_lay_odds(6, 29, 10, bubble=False, policy="2x") == 24


def test_lay_odds_bubble_10x():
    # Bubble: $1 steps
    # multiple=10 → win-cap=100
    # 5/9: lay-cap=floor(100*3/2)=150 → min(desired, cap)
    assert legalize_lay_odds(5, 123, 10, bubble=True, policy="10x") == 123


def test_lay_no_point_is_zero():
    assert legalize_lay_odds(None, 50, 10, bubble=False, policy="3-4-5x") == 0
