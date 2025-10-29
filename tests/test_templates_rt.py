from crapssim_control.templates import render_template, diff_bets


def test_render_and_diff_simple_mode_nonbubble():
    state = {"units": 5, "bubble": False, "point": 0, "on_comeout": True}
    event = {"on_comeout": True}
    cfg = {"level": 10, "bubble": False}

    template = {
        "pass": "units*2",  # 10
        "place": {
            "6": "units*2",
            "8": "units*2",
            "5": "units",
        },  # 6/8=10->legal 6/6? actually 10 -> 6*?  -> 12 after legalizer; 5->5
        "field": "units",
    }

    desired = render_template(template, state, event, cfg)
    # legalized:
    # pass_line: 10 (>= level 10)
    # place_6: raw 10 -> 6-increment -> 6? Wait we round DOWN -> 6
    # place_8: raw 10 -> 6-increment -> 6
    # place_5: raw 5  -> 5-increment -> 5
    assert desired["pass_line"]["amount"] == 10
    assert desired["place_6"]["amount"] == 6
    assert desired["place_8"]["amount"] == 6
    assert desired["place_5"]["amount"] == 5
    assert desired["field"]["amount"] == 5

    current = {"pass_line": {"amount": 10}, "place_6": {"amount": 12}}
    actions = diff_bets(current, desired)
    # should clear place_6 (12) then set to 6 (we use deterministic: clear then set)
    assert {"action": "clear", "bet_type": "place_6"} in actions
    assert {"action": "set", "bet_type": "place_6", "amount": 6} in actions


def test_odds_when_point_on():
    state = {"units": 5, "bubble": False, "point": 6, "on_comeout": False}
    event = {"point": 6, "on_comeout": False}
    cfg = {"level": 10, "max_odds_multiple": 3.0}

    template = {"pass": 10, "odds": {"pass": "units*3"}}  # 15 raw, cap = 30, so 15 is fine

    desired = render_template(template, state, event, cfg)
    assert desired["pass_line"]["amount"] == 10
    assert desired["odds_6_pass"]["amount"] == 15


def test_working_flag_on_comeout():
    state = {"units": 5, "point": 0, "on_comeout": True}
    event = {"on_comeout": True}
    cfg = {}

    template = {
        "pass": 10,
        "odds": {"pass": 10},  # won't be materialized because no point yet
        "working_on_comeout": True,
    }

    desired = render_template(template, state, event, cfg)
    # no odds yet, but if there were they'd carry the flag
    assert "odds_6_pass" not in desired


def test_diff_idempotence_and_ordering():
    current = {"place_6": {"amount": 12}, "field": {"amount": 5}}
    desired = {"place_6": {"amount": 12}, "pass_line": {"amount": 10}}

    actions = diff_bets(current, desired)
    # clear 'field', set 'pass_line'; no change for place_6
    assert actions[0]["action"] == "clear" and actions[0]["bet_type"] == "field"
    assert any(
        a
        for a in actions
        if a["action"] == "set" and a["bet_type"] == "pass_line" and a["amount"] == 10
    )
    # running diff again produces the same plan (idempotent)
    assert diff_bets(desired, desired) == []
