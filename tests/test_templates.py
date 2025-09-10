from crapssim_control.templates import render_template

def test_render_template_regular_table():
    tpl = {"pass":"units", "place":{"6":"units*2","8":"units*2","5":"units"}}
    out = render_template(tpl, {"units": 11}, bubble=False, table_level=10)
    # Flat bets round to table-min steps (10): 11 -> 20
    assert ("pass", None, 20) in out
    # Place 6/8 use $6 steps: 22 -> 24
    assert ("place", 6, 24) in out
    assert ("place", 8, 24) in out
    # Place 5 uses $5 steps with table min: 11 -> 15
    assert ("place", 5, 15) in out

def test_render_template_bubble_table():
    # On bubble: $1 increments BUT still respect table min as floor
    tpl = {"pass":"3", "place":{"6":"3"}}
    out = render_template(tpl, {}, bubble=True, table_level=5)
    # pass: max(amount, table_min) then step=1 => stays at 5
    assert ("pass", None, 5) in out
    # place 6: step=1 but min=5, so 3 -> 5
    assert ("place", 6, 5) in out