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

def test_template_supports_come_and_dont_come():
    tpl = {
        "come": {"amount": "units", "working": True},
        "dont_come": "units"
    }
    names = {"units": 10}
    out = render_template(tpl, names, bubble=False, table_level=10)
    triples = _triples(out)
    # Both should at least hit table min -> 10
    assert ("come", None, 10) in triples
    assert ("dont_come", None, 10) in triples