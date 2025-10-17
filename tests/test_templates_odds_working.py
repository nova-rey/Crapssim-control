from crapssim_control.templates_legacy import render_template

def test_template_supports_odds_and_working():
    tpl = {
        "pass": {"amount": "units", "odds": "units*2", "working": True},
        "place": {
            "6": {"amount": "units", "working": False},
            "8": "units*2"
        }
    }
    names = {"units": 10}
    out = render_template(tpl, names, bubble=False, table_level=10)
    # pass with odds & working
    pk = [t for t in out if t[0] == "pass"][0]
    assert pk[2] >= 10
    assert pk[3].get("odds") == 20
    assert pk[3].get("working") is True
    # place-6 with working false
    p6 = [t for t in out if t[0] == "place" and t[1] == 6][0]
    assert p6[3].get("working") is False