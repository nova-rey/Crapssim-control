from crapssim_control.legalize import legalize_amount

def test_legalize_basic():
    # Place-6/8 should round to multiples of $6
    assert legalize_amount(6, 11, bubble=False, table_level=5) == 12
    # Place-5 should round to multiples of $5
    assert legalize_amount(5, 7, bubble=False, table_level=5) == 10
    # Bubble craps allows $1 increments
    assert legalize_amount(6, 3, bubble=True, table_level=5) == 5  # still respects table min