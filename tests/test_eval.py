from crapssim_control.eval import safe_eval

def test_eval_basic():
    assert safe_eval("1+2*3", {}) == 7
    assert safe_eval("max(6, 8)", {}) == 8
    assert safe_eval("floor(7.9)", {}) == 7

def test_eval_names():
    assert safe_eval("units*2", {"units": 5}) == 10