from crapssim_control.templates_legacy import render_template


def _triples(intents):
    out = []
    for it in intents:
        if len(it) == 3:
            k, n, a = it
        else:
            k, n, a, _ = it
        out.append((k, n, a))
    return out


def test_render_template_regular_table():
    tpl = {"pass": "units", "place": {"6": "units*2", "8": "units*2", "5": "units"}}
    out = render_template(tpl, {"units": 11}, bubble=False, table_level=10)
    triples = _triples(out)
    # Flat bets round to table-min steps (10): 11 -> 20
    assert ("pass", None, 20) in triples
    # Place 6/8 use $6 steps: 22 -> 24
    assert ("place", 6, 24) in triples
    assert ("place", 8, 24) in triples
    # Place 5 uses $5 steps with table min: 11 -> 15
    assert ("place", 5, 15) in triples


def test_render_template_bubble_table():
    # On bubble: $1 increments BUT still respect table min as floor
    tpl = {"pass": "3", "place": {"6": "3"}}
    out = render_template(tpl, {}, bubble=True, table_level=5)
    triples = _triples(out)
    # pass: max(amount, table_min) then step=1 => 5
    assert ("pass", None, 5) in triples
    # place 6: step=1 but min=5, so 3 -> 5
    assert ("place", 6, 5) in triples
