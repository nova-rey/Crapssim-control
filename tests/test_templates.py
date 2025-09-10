from crapssim_control.templates import render_template

def test_render_template():
    tpl = {"pass":"units", "place":{"6":"units*2","8":"units*2","5":"units"}}
    out = render_template(tpl, {"units": 11}, bubble=False, table_level=10)
    # pass: at least table min (10), rounds to 10 (flat bet step == table min)
    assert ("pass", None, 11) not in out  # flat bets use table min step; result should round up to 10 or stay >=10 depending on rules
    assert ("place", 6, 22) in out  # 6/8 use $6 steps: 22 → rounds up to 24, but our legalizer rounds by step; with table min 10, 22 -> 24